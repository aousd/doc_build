#!/usr/bin/env python3
"""Lint and fix bold table headers in Markdown specification files.

ISO/IEC Directives, Part 2 requires table column headings to be in bold.
In Markdown pipe tables this means every header cell should be wrapped in
``**…**``.  Code spans (``` `` ```) are considered visually distinct and
are left unwrapped.

Two modes:

Lint (default)
    Parse each ``.md`` file with Pandoc, walk the AST to find Table nodes
    whose header cells are not bold, and report violations with file and
    line number.

Fix (``--fix``)
    For every file with violations, rewrite the header row in-place so that
    non-bold, non-code cells are wrapped in ``**…**``.

Usage from the command line::

    python3 -m doc_build.iso_bold_table_lint specification/
    python3 -m doc_build.iso_bold_table_lint --fix specification/

Usage as a library::

    from doc_build.iso_bold_table_lint import check_spec, fix_file
    violations = check_spec(Path("specification/"))
    for v in violations:
        print(v.format())
    fix_file(Path("specification/some_file.md"), violations)
"""

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from doc_build.iso_lint_utils import (
    DEFAULT_WORKERS,
    collect_md_files,
    format_report as _format_report,
    get_sourcepos,
    run_parallel_check,
    stringify,
    unwrap_sourcepos_spans,
)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class Violation:
    """A table whose header row has non-bold cells."""
    file: Path
    lineno: int              # 1-based line number of the header row
    header_text: str         # raw source text of the header row
    non_bold_cells: List[str]  # cell texts that are not bold

    def format(self, *, display_path: Optional[Path] = None) -> str:
        path = display_path if display_path is not None else self.file
        cells_str = ', '.join(f'"{c.strip()}"' for c in self.non_bold_cells)
        return (
            f"{path}:{self.lineno}: {self.header_text.strip()}\n"
            f"  non-bold cells: {cells_str}"
        )


# ---------------------------------------------------------------------------
# AST-based detection (lint)
# ---------------------------------------------------------------------------

def _cell_needs_bold(blocks: list) -> bool:
    """Return True if a header cell's content is not bold.

    A cell is considered bold if its Para/Plain block contains a single
    Strong wrapper around all content.  A cell containing only a Code
    span is considered exempt (visually distinct already).
    Empty cells are exempt.

    Handles Pandoc's +sourcepos Span wrappers transparently.
    """
    if not blocks:
        return False

    for block in blocks:
        bt = block.get("t")
        if bt not in ("Para", "Plain"):
            continue
        inlines = unwrap_sourcepos_spans(block.get("c", []))
        if not inlines:
            continue

        # Single Code span — exempt.
        if len(inlines) == 1 and inlines[0].get("t") == "Code":
            continue

        # Single Strong wrapping everything — already bold.
        if len(inlines) == 1 and inlines[0].get("t") == "Strong":
            continue

        # Anything else: not bold.
        return True

    return False


def _cell_text(blocks: list) -> str:
    """Extract plain text from a cell's blocks for reporting."""
    return stringify(blocks).strip()


def check_file(path: Path) -> List[Violation]:
    """Return all bold-table-header violations in a single Markdown file."""
    try:
        raw_lines = path.read_text(encoding='utf-8').splitlines()
    except OSError:
        return []

    try:
        result = subprocess.run(
            ["pandoc", "-f", "commonmark_x+sourcepos+pipe_tables", "-t", "json",
             str(path)],
            capture_output=True, text=True, check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return []

    doc = json.loads(result.stdout)
    violations: List[Violation] = []

    for block in doc["blocks"]:
        if block["t"] != "Table":
            continue

        # Table: [attr, caption, colspecs, head, bodies, foot]
        table_attr = block["c"][0]
        head = block["c"][3]
        table_lineno = get_sourcepos(table_attr)

        # TableHead: [head_attr, rows]
        _, rows = head
        if not rows:
            continue

        for row in rows:
            _, cells = row
            non_bold = []
            for cell in cells:
                # Cell: [attr, alignment, rowspan, colspan, blocks]
                cell_blocks = cell[4]
                if _cell_needs_bold(cell_blocks):
                    non_bold.append(_cell_text(cell_blocks))

            if non_bold and table_lineno is not None:
                # The header row is at the table's start line.
                header_line = raw_lines[table_lineno - 1] if table_lineno <= len(raw_lines) else ""
                violations.append(Violation(
                    file=path,
                    lineno=table_lineno,
                    header_text=header_line,
                    non_bold_cells=non_bold,
                ))

    return violations


def check_spec(
    spec_root: Path,
    workers: int = DEFAULT_WORKERS,
) -> List[Violation]:
    """Walk *spec_root* recursively and return all violations in .md files."""
    md_files = collect_md_files(spec_root)

    return run_parallel_check(
        md_files,
        check_fn=check_file,
        sort_key=lambda v: (str(v.file), v.lineno),
        workers=workers,
    )


# ---------------------------------------------------------------------------
# Source-level fix
# ---------------------------------------------------------------------------

def _bold_header_row(line: str) -> str:
    """Wrap non-bold, non-code cells in a pipe-table header row with **…**.

    Splits the line by ``|``, processes each cell, and reassembles.
    Cells that are already bold (``**…**``) or are code spans (``` `…` ```)
    are left unchanged.  Empty/whitespace-only cells are left unchanged.

    Note: partially bold cells (e.g. ``| **Name** extra |``) are treated
    as not bold — the whole cell text gets wrapped.  This is intentional:
    partial bold in a header cell is almost certainly a formatting error,
    and wrapping the full cell produces the correct result.
    """
    # Split preserving the pipe delimiters.  A typical header row:
    #   "| Name | Type | Description |"
    # splits to: ['', ' Name ', ' Type ', ' Description ', '']
    if '|' not in line:
        return line

    parts = line.split('|')
    new_parts = []

    for i, part in enumerate(parts):
        stripped = part.strip()

        # First and last parts are outside the table pipes — leave as-is.
        if i == 0 or i == len(parts) - 1:
            new_parts.append(part)
            continue

        # Empty cell.
        if not stripped:
            new_parts.append(part)
            continue

        # Already bold.
        if stripped.startswith('**') and stripped.endswith('**'):
            new_parts.append(part)
            continue

        # Code span — exempt.
        if stripped.startswith('`') and stripped.endswith('`'):
            new_parts.append(part)
            continue

        # Wrap in bold, preserving surrounding whitespace.
        leading = part[:len(part) - len(part.lstrip())]
        trailing = part[len(part.rstrip()):]
        new_parts.append(f"{leading}**{stripped}**{trailing}")

    return '|'.join(new_parts)


def fix_file(path: Path, violations: Optional[List[Violation]] = None) -> int:
    """Edit *path* in-place, bolding table header rows.

    If *violations* is None, runs check_file() first.
    Returns the number of header rows fixed.
    """
    if violations is None:
        violations = check_file(path)
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
        bolded = _bold_header_row(original)
        if bolded != original:
            lines[idx] = bolded + trailing
            fixed += 1

    if fixed:
        path.write_text(''.join(lines), encoding='utf-8')

    return fixed


def fix_spec(
    spec_root: Path,
    workers: int = DEFAULT_WORKERS,
    violations: Optional[List[Violation]] = None,
) -> Tuple[int, int]:
    """Fix all violations under *spec_root*.  Returns (files_fixed, rows_fixed).

    If *violations* is provided, skips the check pass and fixes those
    directly — useful when the caller already ran ``check_spec()``.
    """
    if violations is None:
        violations = check_spec(spec_root, workers=workers)
    if not violations:
        return 0, 0

    # Group by file.
    by_file: dict = {}
    for v in violations:
        by_file.setdefault(v.file, []).append(v)

    files_fixed = 0
    rows_fixed = 0
    for file_path, file_violations in by_file.items():
        n = fix_file(file_path, file_violations)
        if n:
            files_fixed += 1
            rows_fixed += n

    return files_fixed, rows_fixed


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------

def format_report(
    violations: List[Violation],
    spec_root: Optional[Path] = None,
) -> str:
    return _format_report(violations, "bold-table-header", spec_root=spec_root)


# ---------------------------------------------------------------------------
# Command-line entry point
# ---------------------------------------------------------------------------

def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(
        description='Check (and optionally fix) Markdown table headers for bold formatting.'
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
        help='Edit files in-place to bold non-bold table header cells.',
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
        violations = check_spec(spec_root, workers=args.workers)
        if not violations:
            print('No bold-table-header violations found.')
            return
        report = format_report(violations, spec_root=spec_root)
        print(report)
        print()

        files_fixed, rows_fixed = fix_spec(spec_root, workers=args.workers, violations=violations)
        print(f'Fixed {rows_fixed} header row(s) in {files_fixed} file(s).')
    else:
        violations = check_spec(spec_root, workers=args.workers)
        report = format_report(violations, spec_root=spec_root)
        if report:
            print(report)
            sys.exit(1)
        else:
            print('No bold-table-header violations found.')


if __name__ == '__main__':
    main()
