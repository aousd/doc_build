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

import os
import re

import yaml
from pandocfilters import Link, Space, Str, stringify, toJSONFilter

from shared_filter_utils import get_metadata_str

# ---------------------------------------------------------------------------
# Module-level lazy state
# ---------------------------------------------------------------------------

# anchor_id -> (number_str, heading_level, is_annex)
# e.g. "paths" -> ("7", 1, False), "element-ordering" -> ("7.2", 2, False)
_anchor_info = None

# section_key -> root anchor string (only for numbered sections)
# e.g. "path_grammar" -> "paths"
_root_anchors = None

# anchor_id -> section_key it belongs to
# used to detect when a fragment anchor lives in a different section than
# the link's file target (deduplication artefact), triggering a fallback
# to the section root anchor.
_anchor_section = None

# raw YAML dict (exceptions map)
_clause_map = None

# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

_HEADING_RE = re.compile(r'^(#{1,6})\s+(.*?)\s*$')
_ATTR_BLOCK_RE = re.compile(r'\s*\{([^}]*)\}\s*$')
_ID_IN_ATTRS_RE = re.compile(r'#([\w-]+)')
_CITATION_RE = re.compile(r'^\[(\d+)\](.*)', re.DOTALL)


def _pandoc_slug(heading_text):
    """Approximate Pandoc's auto-identifier algorithm for raw heading text.

    Input: heading text content (after stripping leading # markers) as it
    appears in the raw Markdown file.  May contain inline markup.

    Algorithm:
      1. Strip inline markup delimiters, keeping text content.
      2. Lowercase.
      3. Letters and digits pass through; spaces become hyphens; underscores
         and periods pass through; everything else is dropped.
      4. Collapse consecutive hyphens.
      5. Remove leading non-letter characters.
      6. Strip trailing hyphens.
    """
    text = heading_text

    # Strip backtick code spans — keep inner text
    text = re.sub(r'`([^`]*)`', r'\1', text)
    text = text.replace('`', '')

    # Strip strong/emphasis — keep content
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    text = re.sub(r'__([^_]+)__', r'\1', text)
    text = re.sub(r'_([^_]+)_', r'\1', text)

    # Strip links — keep link text
    text = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', text)

    # Build identifier char by char (Pandoc rules)
    chars = []
    for ch in text.lower():
        if ch.isalpha() or ch.isdigit():
            chars.append(ch)
        elif ch in (' ', '\t'):
            chars.append('-')
        elif ch in ('_', '.'):
            chars.append(ch)
        # else: drop (punctuation, backslash, angle brackets, parens, etc.)

    slug = ''.join(chars)
    slug = re.sub(r'-+', '-', slug)       # collapse consecutive hyphens
    slug = re.sub(r'^[^a-z]*', '', slug)  # remove leading non-letters
    slug = slug.rstrip('-')
    return slug or 'section'


def _derive_section_key(url_path):
    """Extract the section key from a relative URL path (before any #fragment).

    Returns the folder name (for README.md-based sections) or the lowercased
    file stem (for flat .md files), or None if the path is unrecognisable.

    Examples:
      ../path_grammar/README.md  -> path_grammar
      ../foundational_data_types/README.md#anchor -> foundational_data_types
      Foreword.md                -> foreword
      glossary/README.md         -> glossary
    """
    path = url_path.split('#')[0].replace('\\', '/')
    parts = [p for p in path.split('/') if p not in ('..', '.', '')]
    if not parts:
        return None
    last = parts[-1]
    if last.lower() == 'readme.md':
        return parts[-2].lower() if len(parts) >= 2 else None
    if last.lower().endswith('.md'):
        return last[:-3].lower()
    return None


def _iso_reference_text(number_str, level, is_annex):
    """Format an ISO cross-reference citation string.

    Top-level numbered clause  -> "Clause N"
    Top-level annex            -> "Annex A"
    Subclause (level >= 2)     -> bare number "N.M.P" or "A.1.2"
    """
    if level == 1:
        return f'Annex {number_str}' if is_annex else f'Clause {number_str}'
    return number_str


# ---------------------------------------------------------------------------
# Map builder
# ---------------------------------------------------------------------------

def _build_maps(yaml_path, artifacts_root):
    """Build section-number maps by scanning combined_spec.md.

    Returns (anchor_info, root_anchors, anchor_section, clause_map).

    anchor_info     dict: anchor -> (number_str, level, is_annex)
    root_anchors    dict: section_key -> root anchor (numbered sections only)
    anchor_section  dict: anchor -> section_key it belongs to
    clause_map      dict: raw YAML exceptions

    On FileNotFoundError (test builds, partial environments) returns empty
    maps so all links pass through unchanged.
    """
    try:
        with open(yaml_path, encoding='utf-8') as fh:
            clause_map = yaml.safe_load(fh) or {}
    except FileNotFoundError:
        return {}, {}, {}, {}

    readme_path = os.path.join(artifacts_root, 'README.md')
    combined_path = os.path.join(artifacts_root, 'combined_spec.md')

    try:
        with open(readme_path, encoding='utf-8') as fh:
            readme_text = fh.read()
        section_order = [
            k for k in (
                _derive_section_key(m)
                for m in re.findall(r'\[.*?\]\(([^)]+)\)', readme_text)
            )
            if k is not None
        ]
    except FileNotFoundError:
        return {}, {}, {}, clause_map

    try:
        with open(combined_path, encoding='utf-8') as fh:
            lines = fh.readlines()
    except FileNotFoundError:
        return {}, {}, {}, clause_map

    anchor_info = {}    # anchor -> (number_str, level, is_annex)
    root_anchors = {}   # section_key -> root anchor
    anchor_section = {} # anchor -> section_key (for cross-section disambiguation)
    seen_anchors = {}   # base_anchor -> next deduplication suffix (integer, 1-based)

    current_clause = None
    current_is_annex = False
    current_section_key = None  # section_key of the section currently being scanned
    subcounters = [0] * 7       # index = heading level 1-6; [0] unused
    section_idx = 0
    auto_clause_counter = 0

    for line in lines:
        m = _HEADING_RE.match(line.rstrip('\n'))
        if not m:
            continue

        level = len(m.group(1))
        raw_text = m.group(2)

        # Extract explicit {#id} attribute if present
        attr_m = _ATTR_BLOCK_RE.search(raw_text)
        if attr_m:
            raw_text = raw_text[:attr_m.start()]
            id_m = _ID_IN_ATTRS_RE.search(attr_m.group(1))
            base_anchor = id_m.group(1) if id_m else _pandoc_slug(raw_text)
        else:
            base_anchor = _pandoc_slug(raw_text)

        # Global deduplication: mirrors Pandoc's behaviour
        # First occurrence: use base; second: base-1; third: base-2; …
        if base_anchor not in seen_anchors:
            seen_anchors[base_anchor] = 1
            anchor = base_anchor
        else:
            n = seen_anchors[base_anchor]
            anchor = f'{base_anchor}-{n}'
            seen_anchors[base_anchor] = n + 1

        if level == 1:
            # Determine which spec section this heading belongs to
            if section_idx < len(section_order):
                section_key = section_order[section_idx]
            else:
                section_key = None
            section_idx += 1
            current_section_key = section_key

            if section_key is not None and section_key in clause_map:
                val = clause_map[section_key]
                if val is None:
                    # Explicitly unnumbered (Foreword, Introduction, etc.)
                    current_clause = None
                    current_is_annex = False
                    # Not stored in root_anchors or anchor_info
                elif isinstance(val, dict) and 'annex' in val:
                    current_clause = str(val['annex'])
                    current_is_annex = True
                    subcounters = [0] * 7
                    root_anchors[section_key] = anchor
                    anchor_info[anchor] = (current_clause, 1, True)
                    anchor_section[anchor] = section_key
                else:
                    # Explicit clause number supplied in YAML (override)
                    current_clause = str(val)
                    current_is_annex = False
                    subcounters = [0] * 7
                    root_anchors[section_key] = anchor
                    anchor_info[anchor] = (current_clause, 1, False)
                    anchor_section[anchor] = section_key
            else:
                # Auto-number: next sequential clause
                auto_clause_counter += 1
                current_clause = str(auto_clause_counter)
                current_is_annex = False
                subcounters = [0] * 7
                if section_key is not None:
                    root_anchors[section_key] = anchor
                anchor_info[anchor] = (current_clause, 1, False)
                if section_key is not None:
                    anchor_section[anchor] = section_key

        else:  # level >= 2
            if current_clause is None:
                continue  # subheading of an unnumbered section — skip

            subcounters[level] += 1
            for d in range(level + 1, 7):
                subcounters[d] = 0

            parts = [current_clause] + [
                str(subcounters[i]) for i in range(2, level + 1)
            ]
            number_str = '.'.join(parts)
            anchor_info[anchor] = (number_str, level, current_is_annex)
            if current_section_key is not None:
                anchor_section[anchor] = current_section_key

    return anchor_info, root_anchors, anchor_section, clause_map


# ---------------------------------------------------------------------------
# Lazy initialisation
# ---------------------------------------------------------------------------

def _ensure_initialized(metadata):
    global _anchor_info, _root_anchors, _anchor_section, _clause_map
    if _anchor_info is not None:
        return
    try:
        yaml_path = get_metadata_str(metadata, 'ISO_CLAUSE_MAP')
    except KeyError:
        # Metadata variable not set — disable filter (safe no-op)
        _anchor_info = {}
        _root_anchors = {}
        _anchor_section = {}
        _clause_map = {}
        return
    _anchor_info, _root_anchors, _anchor_section, _clause_map = _build_maps(
        yaml_path, os.getcwd()
    )


# ---------------------------------------------------------------------------
# Per-element handlers
# ---------------------------------------------------------------------------

def _handle_link(value):
    url = value[2][0]
    title = value[2][1]

    # ---- External URL ----
    if url.startswith(('http://', 'https://')):
        link_text = stringify(value[1])
        if link_text.strip() == url.strip():
            return None  # text already shows the URL — don't duplicate
        original = Link(value[0], value[1], value[2])
        return [original, Str(' ('), Str(url), Str(')')]

    # ---- Intra-document anchor or empty — leave alone ----
    if not url or url.startswith('#'):
        return None

    # ---- Internal relative link ----
    parts = url.split('#', 1)
    url_path = parts[0]
    fragment = parts[1] if len(parts) == 2 else None

    section_key = _derive_section_key(url_path)
    if section_key is None:
        return None

    # Root anchor must be known (section present in the combined build)
    root_anchor = _root_anchors.get(section_key)
    if root_anchor is None:
        # Section either not in this build or explicitly unnumbered
        return None

    if fragment:
        info = _anchor_info.get(fragment)
        if info is None:
            return None  # stale or unknown anchor — leave for resolve_sections
        # Guard against deduplication artefacts: if the anchor that happens to
        # have this name actually lives in a *different* section (e.g. a glossary
        # entry "composition" shadows the top-level "# Composition" heading which
        # was deduplicated to "composition-1"), fall back to the section root.
        if _anchor_section.get(fragment) != section_key:
            number_str, level, is_annex = _anchor_info[root_anchor]
            target = '#' + root_anchor
        else:
            number_str, level, is_annex = info
            target = '#' + fragment
    else:
        number_str, level, is_annex = _anchor_info[root_anchor]
        target = '#' + root_anchor

    iso_text = _iso_reference_text(number_str, level, is_annex)
    return Link(value[0], [Str(iso_text)], [target, title])


def _handle_str(value):
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


# ---------------------------------------------------------------------------
# Main filter entry point
# ---------------------------------------------------------------------------

def iso_xrefs(key, value, fmt, metadata):
    _ensure_initialized(metadata)
    if key == 'Link':
        return _handle_link(value)
    if key == 'Str':
        return _handle_str(value)
    return None


if __name__ == '__main__':
    toJSONFilter(iso_xrefs)
