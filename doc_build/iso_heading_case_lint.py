#!/usr/bin/env python3
"""ISO heading sentence-case linter for Markdown specification files.

ISO/IEC Directives, Part 2, 11.4: clause titles shall use sentence case
(only the first word and proper nouns capitalised).  This module scans
source Markdown files and reports headings that appear to be in title case.

Proper-noun detection combines heuristics (camelCase, ALL_CAPS, mixed
alphanumeric) with an optional YAML allowlist of domain-specific terms.

Usage as a library:
    from doc_build.iso_heading_case_lint import check_spec
    violations = check_spec(Path("specification/"))
    for v in violations: print(v.format())

Usage from the command line:
    python3 -m doc_build.iso_heading_case_lint specification/
    python3 -m doc_build.iso_heading_case_lint --proper-nouns custom.yaml spec/
"""

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Set

_this_dir = os.path.dirname(os.path.abspath(__file__))
if _this_dir not in sys.path:
    sys.path.insert(0, _this_dir)
_filters_dir = os.path.join(_this_dir, 'filters')
if _filters_dir not in sys.path:
    sys.path.insert(0, _filters_dir)

from filters.pandocfilters import stringify

from heading_case import (
    heading_needs_conversion,
    is_proper_noun,
    load_proper_nouns,
    sentence_case_inlines,
)

DEFAULT_WORKERS = 8


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

    def format(self) -> str:
        marker = '#' * self.level
        words_str = ', '.join(f'"{w}"' for w in self.non_sentence_words)
        lines = [
            f"{self.file}:{self.lineno}: "
            f"{marker} \"{self.heading_text}\"",
            f"  suggested: {marker} \"{self.suggested_text}\"",
        ]
        if self.non_sentence_words:
            lines.append(f"  title-cased words: {words_str}")
        return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Pandoc AST helpers
# ---------------------------------------------------------------------------

def _get_sourcepos(attr: list) -> Optional[int]:
    for key, val in attr[2]:
        if key == "data-pos":
            pos = val.split("@")[-1]
            return int(pos.split(":")[0])
    return None


def _find_non_sentence_words(inlines: list, extra_nouns: Set[str]) -> List[str]:
    """Return words that are capitalised but not proper nouns (skipping the first word)."""
    import re
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
        lineno = _get_sourcepos(attr)

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

    md_files: List[Path] = []
    for dirpath, dirnames, filenames in os.walk(spec_root):
        dirnames.sort()
        for fname in sorted(filenames):
            if fname.endswith('.md'):
                md_files.append(Path(dirpath) / fname)

    all_violations: List[Violation] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(check_file, p, extra_nouns): p for p in md_files}
        for future in as_completed(futures):
            all_violations.extend(future.result())

    all_violations.sort(key=lambda v: (str(v.file), v.lineno))
    return all_violations


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------

def format_report(
    violations: List[Violation],
    spec_root: Optional[Path] = None,
) -> str:
    if not violations:
        return ''

    by_file: dict = {}
    for v in violations:
        rel = v.file.relative_to(spec_root) if spec_root else v.file
        by_file.setdefault(rel, []).append(v)

    sections: List[str] = []
    total = 0
    for rel_path, file_violations in by_file.items():
        block_lines = [str(rel_path)]
        for v in file_violations:
            display_v = Violation(
                file=rel_path,
                lineno=v.lineno,
                level=v.level,
                heading_text=v.heading_text,
                suggested_text=v.suggested_text,
                non_sentence_words=v.non_sentence_words,
            )
            block_lines.append(display_v.format())
            total += 1
        sections.append('\n'.join(block_lines))

    file_count = len(by_file)
    header = f'{total} heading case violation(s) in {file_count} file(s)\n'
    return header + '\n' + '\n\n'.join(sections)


# ---------------------------------------------------------------------------
# Command-line entry point
# ---------------------------------------------------------------------------

def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(
        description='Check Markdown headings for ISO sentence-case compliance.'
    )
    parser.add_argument(
        'path',
        nargs='?',
        default='.',
        help='Spec root directory to scan (default: current directory)',
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
