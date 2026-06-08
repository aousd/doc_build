"""Shared logic for ISO heading sentence-case enforcement.

ISO/IEC Directives, Part 2, 11.4: clause titles shall be in sentence case
(only the first word and proper nouns capitalised).

This module provides:
- Proper-noun detection via heuristics and an optional YAML allowlist.
- A function to convert heading inline elements to sentence case.
- A function to check whether a heading is already in sentence case.
"""

import os
import re
import sys
from pathlib import Path
from typing import List, Optional, Set

_this_dir = os.path.dirname(os.path.abspath(__file__))
if _this_dir not in sys.path:
    sys.path.insert(0, _this_dir)
_filters_dir = os.path.join(_this_dir, 'filters')
if _filters_dir not in sys.path:
    sys.path.insert(0, _filters_dir)

try:
    import yaml
except ImportError:
    yaml = None


# ---------------------------------------------------------------------------
# Proper-noun heuristics
# ---------------------------------------------------------------------------

# Words that look like identifiers: camelCase, PascalCase, or contain
# internal capitals (e.g. ObjectPath, iPhone, OpenUSD).
_MIXED_CASE_RE = re.compile(
    r'^[A-Z]?[a-z]+[A-Z]'   # camelCase or PascalCase with interior capital
    r'|^[A-Z][a-z]+[A-Z]'   # PascalCase like OpenUSD
)

# Fully uppercase with optional underscores/digits (USD, AOUSD, API, UTF-8).
_ALL_CAPS_RE = re.compile(r'^[A-Z][A-Z0-9_-]+$')

# Common technical acronyms that should always stay uppercase.
BUILTIN_ACRONYMS = frozenset({
    "API", "APIs", "ASCII", "AOUSD", "CPU", "CSS", "DPI", "GPU", "GFM",
    "HTML", "HTTP", "HTTPS", "ID", "IEEE", "IO", "ISO", "JSON", "LHS",
    "MIME", "OCR", "OS", "PDF", "PEG", "RAM", "RCS", "REST", "RFC",
    "RHS", "SDK", "SHA", "SQL", "SSH", "SSL", "SVG", "TCP", "TLS",
    "TSV", "UDP", "UI", "URI", "URL", "USD", "UTF", "UUID", "XML",
    "YAML",
})


def load_proper_nouns(yaml_path: Optional[Path] = None) -> Set[str]:
    """Load proper nouns from a YAML allowlist file.

    The YAML file is expected to have a top-level list under the key
    ``proper_nouns``.  Returns an empty set if the file does not exist
    or yaml is unavailable.
    """
    if yaml_path is None or yaml is None:
        return set()
    try:
        with open(yaml_path, encoding='utf-8') as fh:
            data = yaml.safe_load(fh) or {}
        return set(data.get('proper_nouns', []))
    except (FileNotFoundError, OSError):
        return set()


def is_proper_noun(word: str, extra_nouns: Set[str] = frozenset()) -> bool:
    """Determine whether *word* should retain its capitalisation.

    A word is considered a proper noun if any of these hold:
    - It is in *extra_nouns* (the YAML allowlist).
    - It is in the built-in acronym set.
    - It matches the mixed-case heuristic (camelCase / PascalCase).
    - It is fully uppercase with length >= 2.
    - It contains digits mixed with letters (e.g. "UTF-8", "H264").
    """
    stripped = word.strip(".,;:!?()[]{}\"'`")
    if not stripped:
        return False
    if stripped in extra_nouns:
        return True
    if stripped in BUILTIN_ACRONYMS:
        return True
    if _ALL_CAPS_RE.match(stripped) and len(stripped) >= 2:
        return True
    if _MIXED_CASE_RE.match(stripped):
        return True
    if re.search(r'[A-Za-z]', stripped) and re.search(r'\d', stripped):
        return True
    return False


# ---------------------------------------------------------------------------
# Sentence-case conversion for Pandoc inlines
# ---------------------------------------------------------------------------

def _lowercase_word(word: str) -> str:
    """Lowercase a word, preserving leading/trailing punctuation."""
    prefix = ''
    suffix = ''
    i = 0
    while i < len(word) and not word[i].isalnum():
        prefix += word[i]
        i += 1
    j = len(word)
    while j > i and not word[j - 1].isalnum():
        j -= 1
        suffix = word[j] + suffix
    core = word[i:j]
    return prefix + core.lower() + suffix


def _sentence_case_track(
    inlines: list,
    extra_nouns: Set[str],
    first_word_seen: bool,
) -> tuple:
    """Internal: convert inlines to sentence case, returning (new_inlines, first_word_seen)."""
    import copy
    result = copy.deepcopy(inlines)

    for node in result:
        if not isinstance(node, dict):
            continue
        t = node.get('t')
        if t == 'Str':
            text = node['c']
            words = text.split(' ')
            new_words = []
            for word in words:
                if not word:
                    new_words.append(word)
                    continue
                has_alpha = any(c.isalpha() for c in word)
                if not first_word_seen and has_alpha:
                    first_word_seen = True
                    new_words.append(word)
                elif is_proper_noun(word, extra_nouns):
                    new_words.append(word)
                elif has_alpha:
                    new_words.append(_lowercase_word(word))
                else:
                    new_words.append(word)
            node['c'] = ' '.join(new_words)
        elif t in ('Code', 'Math', 'RawInline'):
            first_word_seen = True
        elif t == 'Space':
            pass
        elif t == 'Span':
            # Span: node['c'] = [attr, inlines_list]
            children = node['c'][1]
            node['c'][1], first_word_seen = _sentence_case_track(
                children, extra_nouns, first_word_seen,
            )
        elif t in ('Emph', 'Strong', 'Strikeout', 'Superscript',
                    'Subscript', 'SmallCaps'):
            children = node['c'] if isinstance(node['c'], list) else [node['c']]
            node['c'], first_word_seen = _sentence_case_track(
                children, extra_nouns, first_word_seen,
            )
        elif t == 'Quoted':
            node['c'][1], first_word_seen = _sentence_case_track(
                node['c'][1], extra_nouns, first_word_seen,
            )

    return result, first_word_seen


def sentence_case_inlines(
    inlines: list,
    extra_nouns: Set[str] = frozenset(),
) -> list:
    """Convert a list of Pandoc inline elements to sentence case.

    Only ``Str`` nodes are modified; ``Code``, ``Math``, ``RawInline``
    and content inside ``Link``/``Image`` alt text are left unchanged.

    The first alphabetic word in the heading is always capitalised.
    Subsequent words are lowercased unless they are proper nouns.
    """
    result, _ = _sentence_case_track(inlines, extra_nouns, False)
    return result


# ---------------------------------------------------------------------------
# Violation detection
# ---------------------------------------------------------------------------

def _extract_words(inlines: list) -> List[str]:
    """Extract plain-text words from Pandoc inlines, skipping Code/Math."""
    from filters.pandocfilters import stringify
    text = stringify(inlines)
    return [w for w in re.split(r'\s+', text) if w]


def heading_needs_conversion(
    inlines: list,
    extra_nouns: Set[str] = frozenset(),
) -> bool:
    """Return True if the heading appears to be in title case.

    A heading is flagged if at least one non-first word is capitalised
    and is not a proper noun.  Single-word headings are never flagged.
    """
    words = _extract_words(inlines)
    if len(words) <= 1:
        return False

    for word in words[1:]:
        stripped = word.strip(".,;:!?()[]{}\"'`")
        if not stripped or not stripped[0].isalpha():
            continue
        if stripped[0].isupper() and not is_proper_noun(word, extra_nouns):
            return True

    return False
