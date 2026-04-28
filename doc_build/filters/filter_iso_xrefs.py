#!/usr/bin/env python3
"""Pandoc filter: ISO cross-references, URL display, bibliography citation format.

Three transformations applied to the Pandoc AST:

1. Internal relative links (e.g. [path grammar](../path_grammar/README.md))
   → ISO clause reference text as a clickable anchor link
   (e.g. [Clause 7](#paths), [7.3](#element-ordering)).

2. External hyperlinks where the link text differs from the URL
   → URL appended in parentheses for paper-copy readability
   (e.g. "RFC 3986 (https://datatracker.ietf.org/doc/html/rfc3986)").

3. Inline bibliography citations ([1], [2] …)
   → "Reference [1]", "Reference [2]" …

Must run BEFORE filter_resolve_sections.py in the filter pipeline so that
original relative paths are still available.

Clause numbering is driven by iso_clause_map.yaml (an exceptions list):
sections absent from the map are auto-numbered sequentially; sections listed
as null are left unnumbered; sections listed as {annex: "A"} become annexes.
The YAML path is passed via the ISO_CLAUSE_MAP pandoc metadata variable.
"""

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from urllib.parse import urlparse

try:
    import yaml
except ImportError:
    sys.exit("Please install the PyYAML package: pip install PyYAML")

from pandocfilters import Link, Space, Str, stringify, toJSONFilter

from shared_filter_utils import get_metadata_str

# ---------------------------------------------------------------------------
# Pure helpers (no instance state)
# ---------------------------------------------------------------------------

_CITATION_RE = re.compile(r'^\[(\d+)\](.*)', re.DOTALL)


def _derive_section_key(url_path):
    """Extract the section key from a relative URL path.

    Returns the folder name (for README.md-based sections) or the lowercased
    file stem (for flat .md files), or None if the path is unrecognisable.

    Uses PurePosixPath because link targets are always POSIX-style paths
    regardless of the host OS.  urlparse strips any #fragment before handing
    the path component to PurePosixPath.

    Examples:
      ../path_grammar/README.md           -> 'path_grammar'
      ../foundational_data_types/README.md#anchor -> 'foundational_data_types'
      Foreword.md                         -> 'foreword'
      glossary/README.md                  -> 'glossary'
    """
    path = PurePosixPath(urlparse(url_path).path)  # strip #fragment; keep path component only

    if path.suffix.lower() != '.md':               # ignore non-Markdown links (images, URLs…)
        return None

    if path.name.lower() == 'readme.md':           # folder-based section: key is the directory name
        parent = path.parent.name                  # e.g. '../path_grammar/README.md' -> 'path_grammar'
        return parent.lower() if parent not in ('', '.', '..') else None  # guard against bare README.md at root

    return path.stem.lower() or None               # flat file: key is the filename without extension


def _links_from_ast(node):
    """Yield Link URLs in document order from a Pandoc AST fragment.

    Recursively walks dicts and lists; stops descending into a Link node once
    its URL has been yielded (avoids double-counting if link text is itself a
    link, which is unusual but valid Markdown).
    """
    if isinstance(node, dict):
        if node.get('t') == 'Link':
            yield node['c'][2][0]
            return
        yield from _links_from_ast(node.get('c'))
    elif isinstance(node, list):
        for item in node:
            yield from _links_from_ast(item)


def _iso_reference_text(number_str, level, is_annex):
    """Format an ISO cross-reference citation string.

    Top-level numbered clause  -> "Clause N"
    Top-level annex            -> "Annex A"
    Subclause (level >= 2)     -> bare number "N.M.P" or "A.1.2"
    """
    if level == 1:
        return f'Annex {number_str}' if is_annex else f'Clause {number_str}'
    return number_str


@dataclass
class TopSection:
    """State for the level-1 heading currently being processed in _build_maps.

    Recreated each time a new level-1 heading is encountered; subcounters are
    mutated in-place as subclause headings accumulate beneath it.
    """
    key: str | None                             # section key from the source file path
    clause: str | None                          # clause number string, or None if unnumbered
    is_annex: bool = False                      # True when clause is an annex letter (A, B, …)
    subcounters: list = field(                  # per-level subclause counters; index 0 unused
        default_factory=lambda: [0] * 7
    )


# ---------------------------------------------------------------------------
# Filter class
# ---------------------------------------------------------------------------

class IsoXrefFilter:
    """Stateful Pandoc filter for ISO cross-references.

    Clause-number maps are set as instance attributes on the first callback
    invocation (lazy initialisation), because the Pandoc metadata that carries
    the iso_clause_map.yaml path is not available until then.

    Usage:
        toJSONFilter(IsoXrefFilter())
    """

    def _build_maps(self, yaml_path, artifacts_root):
        """Build section-number maps by parsing combined_spec.md with Pandoc.

        Populates self._anchor_info, self._root_anchors, self._anchor_section,
        and self._clause_map directly.

        anchor_info     dict: anchor -> (number_str, level, is_annex)
        root_anchors    dict: section_key -> root anchor (numbered sections only)
        anchor_section  dict: anchor -> section_key it belongs to
        clause_map      dict: raw YAML exceptions

        Anchor IDs are taken directly from Pandoc's JSON AST — the first element
        of each Header node's Attr — so they are guaranteed to match the IDs
        Pandoc assigns in the rendered output, including deduplication.

        On FileNotFoundError or Pandoc failure (test builds, partial environments)
        all maps are set to empty so all links pass through unchanged.
        """
        # ---- Load the clause exceptions map ----
        # The YAML file is an exceptions list: sections absent from it are
        # auto-numbered sequentially; sections present are either suppressed
        # (null) or assigned a specific annex letter ({annex: "A"}).
        try:
            with open(yaml_path, encoding='utf-8') as fh:
                self._clause_map = yaml.safe_load(fh) or {}
        except FileNotFoundError:
            self._anchor_info = {}
            self._root_anchors = {}
            self._anchor_section = {}
            self._clause_map = {}
            return

        readme_path = os.path.join(artifacts_root, 'README.md')
        combined_path = os.path.join(artifacts_root, 'combined_spec.md')

        # ---- Determine the ordered list of spec sections ----
        # README.md contains one link per spec section in document order.
        # Parsing it with Pandoc and walking all Link nodes gives the sequence
        # of section keys (e.g. ['foreword', 'glossary', 'path_grammar', ...]).
        # This list is later used to associate each level-1 heading in
        # combined_spec.md with the section file it came from, which in turn
        # determines which clause-map entry (if any) applies to it.
        # Note: this relies on the assumption that each source file contributes
        # exactly one level-1 heading to the combined document.
        try:
            result = subprocess.run(
                ['pandoc', '-f', 'markdown', '-t', 'json', readme_path],
                capture_output=True, text=True, check=True,
            )
            readme_blocks = json.loads(result.stdout)['blocks']
            section_order = [
                k for k in (
                    _derive_section_key(url)
                    for url in _links_from_ast(readme_blocks)
                )
                if k is not None
            ]
        except (FileNotFoundError, subprocess.CalledProcessError):
            self._anchor_info = {}
            self._root_anchors = {}
            self._anchor_section = {}
            return

        # Build a lookup for sections that are null in the YAML but absent from
        # section_order — i.e., injected into combined_spec.md by the build script
        # (e.g. copyright notices) outside the README.md link flow.  Their anchors
        # are derived by Pandoc from the heading text: hyphens where the section key
        # has underscores, but otherwise the same words.  Storing the mapping as
        # anchor → section_key lets us detect them cheaply during the heading walk
        # without consuming a section_order slot.
        section_order_set = set(section_order)
        anchor_to_extra = {
            key.replace('_', '-'): key          # e.g. 'copyright_license_...' → 'copyright-license-...'
            for key, val in self._clause_map.items()
            if val is None and key not in section_order_set  # null YAML entry not reachable from README.md
        }

        # ---- Parse the combined spec ----
        # combined_spec.md is the flat concatenation of all source files produced
        # by flatten().  Pandoc parses it as a single document, which means anchor
        # IDs are deduplicated globally (e.g. two sections both titled "References"
        # get anchors "references" and "references-1").  Those final IDs are what
        # the rendered HTML/PDF uses, so we must read them from Pandoc rather than
        # computing them ourselves.
        try:
            result = subprocess.run(
                ['pandoc', '-f', 'markdown', '-t', 'json', combined_path],
                capture_output=True, text=True, check=True,
            )
        except (FileNotFoundError, subprocess.CalledProcessError):
            self._anchor_info = {}
            self._root_anchors = {}
            self._anchor_section = {}
            return

        blocks = json.loads(result.stdout)['blocks']

        self._anchor_info = {}    # anchor -> (number_str, level, is_annex)
        self._root_anchors = {}   # section_key -> root anchor
        self._anchor_section = {} # anchor -> section_key (for cross-section disambiguation)

        current_section: TopSection | None = None  # state for the active level-1 heading
        section_idx = 0             # position in section_order; advances on each level-1 heading
        auto_clause_counter = 0     # increments for each level-1 heading not listed in clause_map

        for block in blocks:
            if block['t'] != 'Header':
                continue

            level = block['c'][0]
            # Pandoc's Attr is [id, classes, kv-pairs]; the id field is the
            # auto-generated, globally-deduplicated anchor for this heading.
            anchor = block['c'][1][0]

            if level == 1:
                # ---- Level-1 heading: start of a new top-level section ----

                # Check first whether this heading was injected by the build script
                # outside the README.md link flow (e.g. copyright notices).  These
                # sections are in the YAML as null but have no entry in section_order,
                # so they must not consume a section_order slot.
                if anchor in anchor_to_extra:
                    current_section = TopSection(key=anchor_to_extra[anchor], clause=None)
                    continue  # do not advance section_idx

                # Map this heading to its source file by consuming the next entry
                # in section_order.  If section_order is exhausted (e.g. a partial
                # build with --only), section_key is None and the heading is treated
                # as auto-numbered with no clause-map lookup.
                section_key = section_order[section_idx] if section_idx < len(section_order) else None
                section_idx += 1

                if section_key is not None and section_key in self._clause_map:
                    val = self._clause_map[section_key]
                    if val is None:
                        # Explicitly suppressed (Foreword, Introduction, etc.).
                        # No entry is added to anchor_info or root_anchors, so
                        # links to this section are left for filter_resolve_sections.
                        current_section = TopSection(key=section_key, clause=None)
                    elif isinstance(val, dict) and 'annex' in val:
                        # Annex: numbered independently with a letter (A, B, …).
                        # Subclauses will be A.1, A.1.1, etc.
                        current_section = TopSection(key=section_key, clause=str(val['annex']), is_annex=True)
                        self._root_anchors[current_section.key] = anchor
                        self._anchor_info[anchor] = (current_section.clause, 1, current_section.is_annex)
                        self._anchor_section[anchor] = current_section.key
                    else:
                        # Explicit clause number override supplied directly in YAML.
                        current_section = TopSection(key=section_key, clause=str(val))
                        self._root_anchors[current_section.key] = anchor
                        self._anchor_info[anchor] = (current_section.clause, 1, current_section.is_annex)
                        self._anchor_section[anchor] = current_section.key
                else:
                    # Section absent from clause_map: assign the next sequential
                    # clause number.  The counter is shared across all auto-numbered
                    # sections so that explicitly-numbered sections (YAML overrides)
                    # do not consume a slot in the sequence.
                    auto_clause_counter += 1
                    current_section = TopSection(key=section_key, clause=str(auto_clause_counter))
                    if current_section.key is not None:
                        self._root_anchors[current_section.key] = anchor
                    self._anchor_info[anchor] = (current_section.clause, 1, current_section.is_annex)
                    if current_section.key is not None:
                        self._anchor_section[anchor] = current_section.key

            else:  # level >= 2
                # ---- Subclause heading ----

                if current_section is None or current_section.clause is None:
                    # Outside any numbered section — either before the first heading
                    # or inside an unnumbered section (null in clause_map); skip so
                    # these anchors are left for filter_resolve_sections.
                    continue

                # Increment the counter for this level and reset all deeper levels,
                # mirroring the standard hierarchical numbering convention:
                # e.g. entering a new level-3 heading resets level-4, 5, 6.
                current_section.subcounters[level] += 1
                for d in range(level + 1, 7):
                    current_section.subcounters[d] = 0

                # Build the dotted number string: clause + each active sublevel.
                # For a level-3 heading inside Clause 7: "7.2.1" where
                # subcounters[2] and subcounters[3] are the active level-2 and
                # level-3 counts.
                number_str = '.'.join(
                    [current_section.clause] + [str(current_section.subcounters[i]) for i in range(2, level + 1)]
                )
                self._anchor_info[anchor] = (number_str, level, current_section.is_annex)
                if current_section.key is not None:
                    self._anchor_section[anchor] = current_section.key

    def _initialize(self, metadata):
        """Populate the maps from iso_clause_map.yaml and combined_spec.md.

        Called once on the first AST node; subsequent calls are a no-op.
        If the ISO_CLAUSE_MAP metadata key is absent the filter is disabled
        and all nodes pass through unchanged.
        """
        if hasattr(self, '_anchor_info'):
            return
        try:
            yaml_path = get_metadata_str(metadata, 'ISO_CLAUSE_MAP')
        except KeyError:
            # Metadata variable not set — disable filter (safe no-op).
            self._anchor_info = {}
            self._root_anchors = {}
            self._anchor_section = {}
            self._clause_map = {}
            return
        self._build_maps(yaml_path, os.getcwd())

    def __call__(self, key, value, fmt, metadata):
        self._initialize(metadata)
        if key == 'Header':
            return self._handle_header(value)
        if key == 'Link':
            return self._handle_link(value)
        if key == 'Str':
            return self._handle_str(value)
        return None

    def _handle_header(self, value):
        """Add the 'unnumbered' class to headings that carry no ISO clause number.

        Pandoc's --number-sections counts every heading sequentially, including
        front/back matter (Foreword, Introduction, Closing, copyright notices).
        Marking those headings as 'unnumbered' makes Pandoc skip them in its
        counter, so the rendered section numbers match the ISO clause numbers
        assigned by this filter.

        A heading is considered unnumbered if its anchor is absent from
        _anchor_info, which only contains anchors of numbered clauses and their
        subclauses.

        Header value layout: [level, [id, classes, kv-pairs], inlines]
        """
        anchor = value[1][0]                    # Pandoc-assigned heading id
        if anchor in self._anchor_info:
            return None                         # numbered clause — leave Pandoc's counter running
        classes = value[1][1]
        if 'unnumbered' in classes:
            return None                         # already marked — nothing to do
        new_attr = [value[1][0], classes + ['unnumbered'], value[1][2]]
        return {'t': 'Header', 'c': [value[0], new_attr, value[2]]}

    def _handle_link(self, value):
        url = value[2][0]

        # External URL
        if url.startswith(('http://', 'https://')):
            link_text = stringify(value[1])
            if link_text.strip() == url.strip():
                return None  # text already shows the URL — don't duplicate
            original = Link(value[0], value[1], value[2])
            return [original, Str(' ('), Str(url), Str(')')]

        # Intra-document anchor or empty — leave alone
        if not url or url.startswith('#'):
            return None

        # Internal relative link
        parts = url.split('#', 1)
        url_path = parts[0]
        fragment = parts[1] if len(parts) == 2 else None

        section_key = _derive_section_key(url_path)
        if section_key is None:
            return None

        # Root anchor must be known (section present in the combined build)
        root_anchor = self._root_anchors.get(section_key)
        if root_anchor is None:
            # Section either not in this build or explicitly unnumbered
            return None

        if fragment:
            info = self._anchor_info.get(fragment)
            if info is None:
                return None  # stale or unknown anchor — leave for resolve_sections
            # Guard against deduplication artefacts: if the anchor that happens to
            # have this name actually lives in a *different* section (e.g. a glossary
            # entry "composition" shadows the top-level "# Composition" heading which
            # was deduplicated to "composition-1"), use the section root's number.
            if self._anchor_section.get(fragment) != section_key:
                number_str, level, is_annex = self._anchor_info[root_anchor]
            else:
                number_str, level, is_annex = info
        else:
            number_str, level, is_annex = self._anchor_info[root_anchor]

        iso_text = _iso_reference_text(number_str, level, is_annex)
        link_text = stringify(value[1])
        if iso_text in link_text:
            return None  # already annotated — don't duplicate
        original = Link(value[0], value[1], value[2])
        return [original, Str(f' ({iso_text})')]

    def _handle_str(self, value):
        """Expand inline bibliography citation [N] to 'Reference [N]'."""
        m = _CITATION_RE.match(value)
        if not m:
            return None
        num = m.group(1)
        trailing = m.group(2)
        result = [Str('Reference'), Space(), Str(f'[{num}]')]
        if trailing:
            result.append(Str(trailing))
        return result


if __name__ == '__main__':
    toJSONFilter(IsoXrefFilter())
