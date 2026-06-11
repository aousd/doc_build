#!/usr/bin/env python3
"""Lint and fix ISO heading sentence case in Markdown specification files.

ISO/IEC Directives, Part 2, 11.4: clause titles shall use sentence case
(only the first word and proper nouns capitalised).

Two modes:

Lint (default)
    Parse each ``.md`` file with Pandoc, walk the AST to find Header nodes
    that appear to be in title case, and report violations with file and
    line number.

Fix (``--fix``)
    For every file with violations, rewrite the heading line in-place so
    that non-first, non-proper-noun words are lowercased.

Proper-noun detection combines heuristics (camelCase, ALL_CAPS, mixed
alphanumeric) with an optional YAML allowlist of domain-specific terms.

Usage from the command line::

    python3 -m doc_build.iso_heading_case_lint specification/
    python3 -m doc_build.iso_heading_case_lint --fix specification/
    python3 -m doc_build.iso_heading_case_lint --proper-nouns custom.yaml spec/

Usage as a library::

    from doc_build.iso_heading_case_lint import check_spec, fix_file
    violations = check_spec(Path("specification/"))
    for v in violations:
        print(v.format())
    fix_file(Path("specification/some_file.md"), violations, extra_nouns)
"""

import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Set, Tuple

from filters.heading_case import (
    heading_needs_conversion,
    is_proper_noun,
    load_proper_nouns,
    sentence_case_inlines,
)

from doc_build.iso_lint_utils import (
    DEFAULT_WORKERS,
    collect_md_files,
    format_report as _format_report,
    get_sourcepos,
    run_parallel_check,
    stringify,
)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class Violation:
    """A heading that is not in ISO sentence case."""
    file: Path
    lineno: int
    level: int
    heading_text: str
    suggested_text: str
    non_sentence_words: List[str] = field(default_factory=list)

    def format(self, display_path: Optional[Path] = None) -> str:
        path = display_path if display_path is not None else self.file
        marker = '#' * self.level
        words_str = ', '.join(f'"{w}"' for w in self.non_sentence_words)
        lines = [
            f"{path}:{self.lineno}: "
            f"{marker} \"{self.heading_text}\"",
            f"  suggested: {marker} \"{self.suggested_text}\"",
        ]
        if self.non_sentence_words:
            lines.append(f"  title-cased words: {words_str}")
        return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Pandoc AST helpers
# ---------------------------------------------------------------------------

def _find_non_sentence_words(inlines: list, extra_nouns: Set[str]) -> List[str]:
    """Return words that are capitalised but not proper nouns (skipping the first word)."""
    words = []
    text = stringify(inlines)
    all_words = [w for w in re.split(r'\s+', text) if w]
    for word in all_words[1:]:
        stripped = word.strip(".,;:!?()[]{}\"'`")
        if not stripped or not stripped[0].isalpha():
            continue
        if stripped[0].isupper() and not is_proper_noun(word, extra_nouns):
            words.append(word)
    return words


# ---------------------------------------------------------------------------
# Core checker
# ---------------------------------------------------------------------------

def check_file(path: Path, extra_nouns: Set[str] = frozenset()) -> List[Violation]:
    """Return all heading sentence-case violations in a single Markdown file."""
    try:
        result = subprocess.run(
            ["pandoc", "-f", "commonmark_x+sourcepos", "-t", "json", str(path)],
            capture_output=True, text=True, check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return []

    doc = json.loads(result.stdout)
    violations: List[Violation] = []

    for block in doc["blocks"]:
        if block["t"] != "Header":
            continue

        level = block["c"][0]
        attr = block["c"][1]
        inlines = block["c"][2]
        lineno = get_sourcepos(attr)

        if not heading_needs_conversion(inlines, extra_nouns):
            continue

        heading_text = stringify(inlines).strip()
        converted = sentence_case_inlines(inlines, extra_nouns)
        suggested_text = stringify(converted).strip()
        non_sentence = _find_non_sentence_words(inlines, extra_nouns)

        violations.append(Violation(
            file=path,
            lineno=lineno or 0,
            level=level,
            heading_text=heading_text,
            suggested_text=suggested_text,
            non_sentence_words=non_sentence,
        ))

    return violations


def check_spec(
    spec_root: Path,
    workers: int = DEFAULT_WORKERS,
    proper_nouns_path: Optional[Path] = None,
) -> List[Violation]:
    """Walk *spec_root* recursively and return all violations in .md files."""
    extra_nouns = load_proper_nouns(proper_nouns_path)
    md_files = collect_md_files(spec_root)

    return run_parallel_check(
        md_files,
        check_fn=lambda p: check_file(p, extra_nouns),
        sort_key=lambda v: (str(v.file), v.lineno),
        workers=workers,
    )


# ---------------------------------------------------------------------------
# Source-level fix
# ---------------------------------------------------------------------------

# Regex matching an ATX heading line: "## Some Heading Text"
_ATX_HEADING_RE = re.compile(r'^(#{1,6}\s+)(.*?)(\s*)$')


def _sentence_case_text(text: str, extra_nouns: Set[str]) -> str:
    """Convert the text portion of a heading to sentence case.

    Preserves inline Markdown formatting (``*``, ``**``, ``_``, ``[``,
    etc.) by only modifying alphabetic word sequences.  Code spans
    (``` `` ```) and link URLs (``](…)``) are left untouched.
    """
    # Build a set of character positions that are inside code spans or
    # link URLs — these must not be modified.
    protected: Set[int] = set()
    for m in re.finditer(r'`+.+?`+', text):
        protected.update(range(m.start(), m.end()))
    for m in re.finditer(r'\]\([^)]*\)', text):
        protected.update(range(m.start(), m.end()))

    first_word_seen = False
    result = list(text)

    for m in re.finditer(r"[A-Za-z][A-Za-z0-9'_-]*", text):
        word_range = range(m.start(), m.end())
        # Skip words inside protected ranges (code spans, link URLs).
        if not protected.isdisjoint(word_range):
            first_word_seen = True
            continue

        word = m.group()

        # First alphabetic word in the heading is always preserved.
        if not first_word_seen:
            first_word_seen = True
            continue

        if is_proper_noun(word, extra_nouns):
            continue

        # Lowercase this word in-place.
        lowered = word.lower()
        for i, ch in enumerate(lowered):
            result[m.start() + i] = ch

    return ''.join(result)


def _sentence_case_heading_line(line: str, extra_nouns: Set[str]) -> str:
    """Convert an ATX heading source line to sentence case.

    Splits the line into ``# `` prefix, text, and trailing whitespace.
    Only the text portion is case-converted; the prefix and trailing
    whitespace are preserved verbatim.
    """
    m = _ATX_HEADING_RE.match(line)
    if not m:
        return line
    prefix, text, trailing = m.groups()
    converted = _sentence_case_text(text, extra_nouns)
    return prefix + converted + trailing


def fix_file(
    path: Path,
    violations: Optional[List[Violation]] = None,
    extra_nouns: Set[str] = frozenset(),
) -> int:
    """Edit *path* in-place, converting heading lines to sentence case.

    If *violations* is None, runs ``check_file()`` first.
    Returns the number of headings fixed.
    """
    if violations is None:
        violations = check_file(path, extra_nouns)
    file_violations = [v for v in violations if v.file == path]
    if not file_violations:
        return 0

    lines = path.read_text(encoding='utf-8').splitlines(keepends=True)
    violation_lines = {v.lineno for v in file_violations}
    fixed = 0

    for lineno in sorted(violation_lines):
        idx = lineno - 1
        if idx < 0 or idx >= len(lines):
            continue
        original = lines[idx].rstrip('\n')
        trailing = lines[idx][len(original):]
        converted = _sentence_case_heading_line(original, extra_nouns)
        if converted != original:
            lines[idx] = converted + trailing
            fixed += 1

    if fixed:
        path.write_text(''.join(lines), encoding='utf-8')

    return fixed


def fix_spec(
    spec_root: Path,
    workers: int = DEFAULT_WORKERS,
    proper_nouns_path: Optional[Path] = None,
) -> Tuple[int, int]:
    """Fix all violations under *spec_root*.  Returns (files_fixed, headings_fixed)."""
    extra_nouns = load_proper_nouns(proper_nouns_path)
    violations = check_spec(spec_root, workers=workers, proper_nouns_path=proper_nouns_path)
    if not violations:
        return 0, 0

    # Group by file.
    by_file: dict = {}
    for v in violations:
        by_file.setdefault(v.file, []).append(v)

    files_fixed = 0
    headings_fixed = 0
    for file_path, file_violations in by_file.items():
        n = fix_file(file_path, file_violations, extra_nouns)
        if n:
            files_fixed += 1
            headings_fixed += n

    return files_fixed, headings_fixed


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------

def format_report(
    violations: List[Violation],
    spec_root: Optional[Path] = None,
) -> str:
    return _format_report(violations, "heading case", spec_root=spec_root)


# ---------------------------------------------------------------------------
# Command-line entry point
# ---------------------------------------------------------------------------

def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(
        description='Check (and optionally fix) Markdown headings for ISO sentence-case compliance.'
    )
    parser.add_argument(
        'path',
        nargs='?',
        default='.',
        help='Spec root directory to scan (default: current directory)',
    )
    parser.add_argument(
        '--fix',
        action='store_true',
        help='Edit files in-place to convert title-case headings to sentence case.',
    )
    parser.add_argument(
        '--proper-nouns',
        type=Path,
        default=None,
        metavar='YAML',
        help='Path to a YAML file listing additional proper nouns',
    )
    parser.add_argument(
        '--workers',
        type=int,
        default=DEFAULT_WORKERS,
        metavar='N',
        help=f'Parallel Pandoc workers (default: {DEFAULT_WORKERS})',
    )
    args = parser.parse_args(argv)
    spec_root = Path(args.path).resolve()

    if args.fix:
        violations = check_spec(
            spec_root,
            workers=args.workers,
            proper_nouns_path=args.proper_nouns,
        )
        if not violations:
            print('No heading case violations found.')
            return
        report = format_report(violations, spec_root=spec_root)
        print(report)
        print()

        files_fixed, headings_fixed = fix_spec(
            spec_root,
            workers=args.workers,
            proper_nouns_path=args.proper_nouns,
        )
        print(f'Fixed {headings_fixed} heading(s) in {files_fixed} file(s).')
    else:
        violations = check_spec(
            spec_root,
            workers=args.workers,
            proper_nouns_path=args.proper_nouns,
        )
        report = format_report(violations, spec_root=spec_root)
        if report:
            print(report)
            sys.exit(1)
        else:
            print('No heading case violations found.')


if __name__ == '__main__':
    main()
