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
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

from doc_build.iso_lint_utils import (
    DEFAULT_WORKERS,
    collect_md_files,
    format_report as _format_report,
    get_sourcepos,
    run_parallel_check,
    stringify,
)

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
    heading_level: int           # heading level (1–6)
    heading_text: str            # heading text as plain text (no markup)
    first_sub_lineno: int        # 1-based line number of the first subclause
    first_sub_level: int         # heading level of the first subclause
    first_sub_text: str          # first subclause text as plain text
    body_lines: List[Tuple[int, str]] = field(default_factory=list)
    # Non-blank source lines between the heading and the first subclause.
    # Each entry is (1-based line number, raw line content).

    def format(self, *, context: int = DEFAULT_CONTEXT_LINES, display_path: Optional[Path] = None) -> str:
        """Return a human-readable description of the violation."""
        path = display_path if display_path is not None else self.file
        h_marker = '#' * self.heading_level
        sub_marker = '#' * self.first_sub_level
        shown = self.body_lines[:context]
        remainder = len(self.body_lines) - len(shown)

        lines = [
            f"{path}:{self.heading_lineno}: "
            f"{h_marker} \"{self.heading_text}\"",
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


_HTML_COMMENT_RE = re.compile(r'^\s*<!--.*?-->\s*$', re.DOTALL)


def _is_html_comment_block(block: dict) -> bool:
    """True if *block* is an HTML comment (possibly wrapped in a sourcepos Div)."""
    candidates = [block]
    if block.get("t") == "Div":
        candidates = block.get("c", [None, []])[1]
    return all(
        b.get("t") == "RawBlock"
        and len(b.get("c", [])) == 2
        and b["c"][0] == "html"
        and _HTML_COMMENT_RE.match(b["c"][1])
        for b in candidates
    )


def _strip_html_comment_lines(
    lines: List[Tuple[int, str]],
) -> List[Tuple[int, str]]:
    """Remove lines that are (part of) an HTML comment.

    Handles single-line ``<!-- ... -->`` and multi-line comments where
    ``<!--`` and ``-->`` are on separate lines.  Lines that contain both
    non-comment text and a comment tag are kept (conservative).
    """
    result: List[Tuple[int, str]] = []
    in_comment = False
    for lineno, text in lines:
        stripped = text.strip()
        if not in_comment:
            if _HTML_COMMENT_RE.match(text):
                continue
            if stripped.startswith("<!--"):
                in_comment = True
                continue
            result.append((lineno, text))
        else:
            if "-->" in stripped:
                in_comment = False
            continue
    return result


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
            lineno: Optional[int] = get_sourcepos(attr)
            text: str = stringify(inlines).strip()

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
                body_lines = _strip_html_comment_lines([
                    (i + 1, raw_lines[i])
                    for i in range(cur_lineno, lineno - 1)
                    if i < len(raw_lines) and raw_lines[i].strip()
                ])
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
            # Any non-heading top-level block is body content, unless it
            # is an HTML comment which is invisible in rendered output.
            if current_heading is not None and not _is_html_comment_block(block):
                body_seen = True

    return violations


def check_spec(
    spec_root: Path,
    workers: int = DEFAULT_WORKERS,
) -> List[Violation]:
    """Walk *spec_root* recursively and return all violations in .md files.

    *spec_root* may be a single ``.md`` file or a directory.  Files are
    processed in parallel (up to *workers* simultaneous Pandoc
    subprocesses) for speed, then results are sorted by (file path, line
    number) so that output is stable across runs.
    """
    md_files = collect_md_files(spec_root)

    return run_parallel_check(
        md_files,
        check_fn=check_file,
        sort_key=lambda v: (str(v.file), v.heading_lineno),
        workers=workers,
    )


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
    return _format_report(
        violations, "clause structure", spec_root=spec_root, context=context,
    )


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
