#!/usr/bin/env python3
"""ISO clause structure linter for Markdown specification files.

ISO/IEC Directives, Part 2 rule: if a clause contains subclauses, there shall
be no text between the clause heading and its first subclause.

This module checks source Markdown files (not the flattened combined spec) and
reports every heading that has body text immediately preceding its first direct
child heading.  Pandoc is used as the Markdown parser so that all edge cases
(fenced and indented code blocks, setext headings, block quotes) are handled
correctly and consistently with the build pipeline.  Only top-level document
blocks are examined; content nested inside block quotes or lists is ignored.

Usage as a library:
    from doc_build.iso_clause_lint import check_spec
    violations = check_spec(Path("specification/"))
    for v in violations: print(v.format())

Usage from the command line:
    python3 -m doc_build.iso_clause_lint specification/
"""

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

# How many non-blank body lines to show as context in a report.
DEFAULT_CONTEXT_LINES = 5

# Maximum number of parallel Pandoc subprocesses used by check_spec().
DEFAULT_WORKERS = 8


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class Violation:
    """A single ISO clause-structure violation found in a Markdown file."""
    file: Path
    heading_lineno: int          # 1-based line number of the offending heading
    heading_level: int           # heading level (1–6)
    heading_text: str            # heading text as plain text (no markup)
    first_sub_lineno: int        # 1-based line number of the first subclause
    first_sub_level: int         # heading level of the first subclause
    first_sub_text: str          # first subclause text as plain text
    body_lines: List[Tuple[int, str]] = field(default_factory=list)
    # Non-blank source lines between the heading and the first subclause.
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
# Pandoc AST helpers
# ---------------------------------------------------------------------------

def _get_sourcepos(attr: list) -> Optional[int]:
    """Extract the start line number from a Pandoc sourcepos Attr.

    Attr layout: [id, [classes], [[key, value], ...]]

    When Pandoc reads from a file the data-pos value has the form
    "filepath@startrow:startcol-endrow:endcol"; when reading from stdin it
    omits the "filepath@" prefix.  Both forms are handled here.

    Returns the start row as a 1-based integer, or None if the attribute is
    absent.
    """
    for key, val in attr[2]:
        if key == "data-pos":
            # Strip optional "filepath@" prefix before the row:col range.
            pos = val.split("@")[-1]
            return int(pos.split(":")[0])
    return None


def _stringify(inlines: list) -> str:
    """Convert a list of Pandoc inline elements to plain text.

    Handles the inline types that appear in heading text; all others are
    silently omitted (RawInline, Math, Note, Cite).
    """
    parts: List[str] = []
    for el in inlines:
        t = el.get("t")
        if t == "Str":
            parts.append(el["c"])
        elif t in ("Space", "SoftBreak", "LineBreak"):
            parts.append(" ")
        elif t == "Code":
            # el["c"] = [Attr, code_string]
            parts.append(el["c"][1])
        elif t in ("Emph", "Strong", "Strikeout", "Underline",
                   "Superscript", "Subscript", "SmallCaps"):
            parts.append(_stringify(el["c"]))
        elif t == "Quoted":
            # el["c"] = [QuoteType, [Inline]]
            parts.append(_stringify(el["c"][1]))
        elif t in ("Link", "Image"):
            # el["c"] = [Attr, [Inline], Target]
            parts.append(_stringify(el["c"][1]))
        elif t == "Span":
            # el["c"] = [Attr, [Inline]]
            parts.append(_stringify(el["c"][1]))
    return "".join(parts)


# ---------------------------------------------------------------------------
# Core checker
# ---------------------------------------------------------------------------

def check_file(path: Path) -> List[Violation]:
    """Return all ISO clause violations in a single Markdown file.

    A violation occurs when a heading at level N is followed by one or more
    non-blank body blocks before the first heading at level N+1 (its first
    direct child subclause).

    Pandoc parses the file with the +sourcepos extension so that every block
    carries its source line number.  Only top-level document blocks are
    examined; headings or text nested inside block quotes, lists, or other
    containers are intentionally ignored.

    Returns [] on OSError or if Pandoc is unavailable.
    """
    try:
        raw_lines = path.read_text(encoding='utf-8').splitlines()
    except OSError:
        return []

    try:
        result = subprocess.run(
            ["pandoc", "-f", "commonmark_x+sourcepos", "-t", "json", str(path)],
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError:
        # Pandoc is not installed — skip silently.
        return []
    except subprocess.CalledProcessError:
        # Pandoc rejected the file (parse error) — skip.
        return []

    doc = json.loads(result.stdout)

    violations: List[Violation] = []
    # State: the most recently seen top-level heading.
    current_heading: Optional[Tuple[int, str, int]] = None  # (level, text, lineno)
    body_seen = False  # True if any non-heading block followed current_heading.

    for block in doc["blocks"]:
        if block["t"] == "Header":
            level: int = block["c"][0]
            attr: list = block["c"][1]
            inlines: list = block["c"][2]
            lineno: Optional[int] = _get_sourcepos(attr)
            text: str = _stringify(inlines).strip()

            # Check for a violation: the previous heading has body content
            # and this heading is its first direct child (level N+1).
            if (current_heading is not None
                    and body_seen
                    and lineno is not None
                    and level == current_heading[0] + 1):
                cur_level, cur_text, cur_lineno = current_heading
                # Collect non-blank raw lines between the two headings.
                # cur_lineno and lineno are 1-based; raw_lines is 0-indexed.
                # The first line after the parent heading is raw_lines[cur_lineno]
                # (0-indexed), and the last line before the child heading is
                # raw_lines[lineno - 2] (0-indexed).
                body_lines = [
                    (i + 1, raw_lines[i])
                    for i in range(cur_lineno, lineno - 1)
                    if i < len(raw_lines) and raw_lines[i].strip()
                ]
                violations.append(Violation(
                    file=path,
                    heading_lineno=cur_lineno,
                    heading_level=cur_level,
                    heading_text=cur_text,
                    first_sub_lineno=lineno,
                    first_sub_level=level,
                    first_sub_text=text,
                    body_lines=body_lines,
                ))

            # Advance state: this heading is now the current open heading.
            # If Pandoc produced no sourcepos (shouldn't happen with +sourcepos
            # but be defensive), keep the previous heading so we don't lose
            # our position in the document.
            if lineno is not None:
                current_heading = (level, text, lineno)
                body_seen = False

        else:
            # Any non-heading top-level block is body content.
            if current_heading is not None:
                body_seen = True

    return violations


def check_spec(
    spec_root: Path,
    workers: int = DEFAULT_WORKERS,
) -> List[Violation]:
    """Walk *spec_root* recursively and return all violations in .md files.

    Files are processed in parallel (up to *workers* simultaneous Pandoc
    subprocesses) for speed, then results are sorted by (file path, line
    number) so that output is stable across runs.
    """
    md_files: List[Path] = []
    for dirpath, dirnames, filenames in os.walk(spec_root):
        dirnames.sort()
        for fname in sorted(filenames):
            if fname.endswith('.md'):
                md_files.append(Path(dirpath) / fname)

    all_violations: List[Violation] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(check_file, p): p for p in md_files}
        for future in as_completed(futures):
            all_violations.extend(future.result())

    all_violations.sort(key=lambda v: (str(v.file), v.heading_lineno))
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

    # Group by file for tidier output.
    by_file: dict = {}
    for v in violations:
        rel = v.file.relative_to(spec_root) if spec_root else v.file
        by_file.setdefault(rel, []).append(v)

    sections: List[str] = []
    total = 0
    for rel_path, file_violations in by_file.items():
        block_lines = [f'{rel_path}']
        for v in file_violations:
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
    parser.add_argument(
        '--workers',
        type=int,
        default=DEFAULT_WORKERS,
        metavar='N',
        help=f'Parallel Pandoc workers (default: {DEFAULT_WORKERS})',
    )
    args = parser.parse_args(argv)
    spec_root = Path(args.path).resolve()
    violations = check_spec(spec_root, workers=args.workers)
    report = format_report(violations, context=args.context, spec_root=spec_root)
    if report:
        print(report)
        sys.exit(1)
    else:
        print('No ISO clause structure violations found.')


if __name__ == '__main__':
    main()
