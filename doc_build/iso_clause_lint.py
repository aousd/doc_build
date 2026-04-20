#!/usr/bin/env python3
"""ISO clause structure linter for Markdown specification files.

ISO/IEC Directives, Part 2 rule: if a clause contains subclauses, there shall
be no text between the clause heading and its first subclause.

This module checks source Markdown files (not the flattened combined spec) and
reports every heading that has body text immediately preceding its first direct
child heading.  It is intentionally standalone — no Pandoc dependency — so it
runs quickly on the raw files.

Usage as a library:
    from doc_build.iso_clause_lint import check_spec
    violations = check_spec(Path("specification/"))
    for v in violations: print(v.format())

Usage from the command line:
    python3 -m doc_build.iso_clause_lint specification/
"""

import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

# ---------------------------------------------------------------------------
# Parsing constants
# ---------------------------------------------------------------------------

# Matches ATX heading lines, capturing the hashes and the title text.
# Strips trailing Pandoc attribute blocks {#id .class}.
_HEADING_RE = re.compile(r'^(#{1,6})\s+(.+?)(?:\s+\{[^}]*\})?\s*$')

# Matches the opening/closing fence of a fenced code block (``` or ~~~).
_FENCE_RE = re.compile(r'^\s*(`{3,}|~{3,})')

# How many non-blank body lines to show as context in a report.
DEFAULT_CONTEXT_LINES = 5


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class Violation:
    """A single ISO clause-structure violation found in a Markdown file."""
    file: Path
    heading_lineno: int          # 1-based line number of the offending heading
    heading_level: int           # ATX heading level (1–6)
    heading_text: str            # heading text (stripped of attribute blocks)
    first_sub_lineno: int        # 1-based line number of the first subclause
    first_sub_level: int         # heading level of the first subclause
    first_sub_text: str          # first subclause text
    body_lines: List[Tuple[int, str]] = field(default_factory=list)
    # Non-blank lines between the heading and the first subclause.
    # Each entry is (1-based line number, raw line content).

    def format(self, context: int = DEFAULT_CONTEXT_LINES) -> str:
        """Return a human-readable description of the violation."""
        h_marker = '#' * self.heading_level
        sub_marker = '#' * self.first_sub_level
        shown = self.body_lines[:context]
        remainder = len(self.body_lines) - len(shown)

        lines = [
            f"{self.file}:{self.heading_lineno}: "
            f"{h_marker} \"{self.heading_text}\" "
            f"has text before its first subclause",
        ]
        for lineno, content in shown:
            lines.append(f"  │ {lineno:5d}: {content}")
        if remainder > 0:
            lines.append(f"  │  ... and {remainder} more non-blank line(s)")
        lines.append(
            f"  └─ first subclause: {sub_marker} \"{self.first_sub_text}\" "
            f"(line {self.first_sub_lineno})"
        )
        return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Core checker
# ---------------------------------------------------------------------------

def check_file(path: Path) -> List[Violation]:
    """Return all ISO clause violations in a single Markdown file.

    A violation occurs when a heading at level N is followed by non-blank
    body text before the first heading at level N+1 (its first direct child
    subclause).  Headings inside fenced code blocks are ignored.
    """
    try:
        text = path.read_text(encoding='utf-8')
    except OSError:
        return []

    raw_lines = text.splitlines()

    # ---- Pass 1: collect headings, skipping those inside code fences ----
    headings: List[Tuple[int, int, str]] = []  # (0-based line idx, level, text)
    fenced: List[bool] = []  # True for each line idx that is inside a fence
    in_fence = False
    fence_char: Optional[str] = None

    for idx, line in enumerate(raw_lines):
        fence_m = _FENCE_RE.match(line)
        if fence_m:
            marker = fence_m.group(1)[0]  # ` or ~
            if not in_fence:
                in_fence = True
                fence_char = marker
            elif marker == fence_char:
                in_fence = False
                fence_char = None
            fenced.append(True)  # fence delimiter lines are also excluded
            continue
        fenced.append(in_fence)
        if in_fence:
            continue
        heading_m = _HEADING_RE.match(line)
        if heading_m:
            headings.append((idx, len(heading_m.group(1)), heading_m.group(2)))

    # ---- Pass 2: for each heading, find first direct child and check content ----
    violations: List[Violation] = []

    for h_pos, (h_idx, h_level, h_text) in enumerate(headings):
        # Find the first heading at level h_level+1 before any heading at
        # level <= h_level (i.e., before we leave this clause's scope).
        first_child: Optional[Tuple[int, int, str]] = None
        for fc_idx, fc_level, fc_text in headings[h_pos + 1:]:
            if fc_level <= h_level:
                break                      # left scope without finding a child
            if fc_level == h_level + 1:
                first_child = (fc_idx, fc_level, fc_text)
                break
            # fc_level > h_level+1: deeper descendant — keep scanning

        if first_child is None:
            continue  # no direct child subclause → no violation possible

        fc_idx, fc_level, fc_text = first_child

        # Collect non-blank body lines between the heading and the first child,
        # excluding lines inside fenced code blocks.
        body_lines = [
            (h_idx + 1 + offset + 1, raw_lines[h_idx + 1 + offset])
            for offset, line in enumerate(raw_lines[h_idx + 1: fc_idx])
            if line.strip() and not fenced[h_idx + 1 + offset]
        ]

        if body_lines:
            violations.append(Violation(
                file=path,
                heading_lineno=h_idx + 1,
                heading_level=h_level,
                heading_text=h_text,
                first_sub_lineno=fc_idx + 1,
                first_sub_level=fc_level,
                first_sub_text=fc_text,
                body_lines=body_lines,
            ))

    return violations


def check_spec(spec_root: Path) -> List[Violation]:
    """Walk *spec_root* recursively and return all violations in .md files.

    Files are processed in a deterministic order (sorted by path) so that
    output is stable across runs.
    """
    all_violations: List[Violation] = []
    for dirpath, dirnames, filenames in os.walk(spec_root):
        dirnames.sort()
        for fname in sorted(filenames):
            if fname.endswith('.md'):
                all_violations.extend(check_file(Path(dirpath) / fname))
    return all_violations


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------

def format_report(
    violations: List[Violation],
    context: int = DEFAULT_CONTEXT_LINES,
    spec_root: Optional[Path] = None,
) -> str:
    """Format all violations into a human-readable report string.

    If *spec_root* is given, file paths are shown relative to it.
    Returns an empty string when there are no violations.
    """
    if not violations:
        return ''

    # Group by file for tidier output
    by_file: dict = {}
    for v in violations:
        rel = v.file.relative_to(spec_root) if spec_root else v.file
        by_file.setdefault(rel, []).append(v)

    sections: List[str] = []
    total = 0
    for rel_path, file_violations in by_file.items():
        block_lines = [f'{rel_path}']
        for v in file_violations:
            # Rebase the file path for display
            display_v = Violation(
                file=rel_path,
                heading_lineno=v.heading_lineno,
                heading_level=v.heading_level,
                heading_text=v.heading_text,
                first_sub_lineno=v.first_sub_lineno,
                first_sub_level=v.first_sub_level,
                first_sub_text=v.first_sub_text,
                body_lines=v.body_lines,
            )
            block_lines.append(display_v.format(context=context))
            total += 1
        sections.append('\n'.join(block_lines))

    file_count = len(by_file)
    header = (
        f'ISO clause structure violations: '
        f'{total} violation(s) in {file_count} file(s)\n'
        + '─' * 72
    )
    return header + '\n\n' + '\n\n'.join(sections)


# ---------------------------------------------------------------------------
# Command-line entry point
# ---------------------------------------------------------------------------

def main(argv=None):
    """Standalone entry point: python3 -m doc_build.iso_clause_lint <path>"""
    import argparse
    parser = argparse.ArgumentParser(
        description='Check Markdown files for ISO clause structure violations.'
    )
    parser.add_argument(
        'path',
        nargs='?',
        default='.',
        help='Spec root directory to scan (default: current directory)',
    )
    parser.add_argument(
        '--context',
        type=int,
        default=DEFAULT_CONTEXT_LINES,
        metavar='N',
        help=f'Number of body lines to show per violation (default: {DEFAULT_CONTEXT_LINES})',
    )
    args = parser.parse_args(argv)
    spec_root = Path(args.path).resolve()
    violations = check_spec(spec_root)
    report = format_report(violations, context=args.context, spec_root=spec_root)
    if report:
        print(report)
        sys.exit(1)
    else:
        print('No ISO clause structure violations found.')


if __name__ == '__main__':
    main()
