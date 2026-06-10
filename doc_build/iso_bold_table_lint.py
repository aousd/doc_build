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
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Set, Tuple

try:
    from doc_build.filters.pandocfilters import stringify
except ImportError:
    from filters.pandocfilters import stringify

DEFAULT_WORKERS = 8

# Regex matching a pipe-table separator row:  |---|---|  or  |:---:|---:|
_SEPARATOR_RE = re.compile(
    r'^\s*\|'           # leading pipe (optional whitespace)
    r'[\s:_-]+'         # first cell: dashes, colons, spaces
    r'(\|[\s:_-]+)*'    # subsequent cells
    r'\|?\s*$'          # trailing pipe (optional)
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

    def format(self) -> str:
        cells_str = ', '.join(f'"{c.strip()}"' for c in self.non_bold_cells)
        return (
            f"{self.file}:{self.lineno}: {self.header_text.strip()}\n"
            f"  non-bold cells: {cells_str}"
        )


# ---------------------------------------------------------------------------
# AST-based detection (lint)
# ---------------------------------------------------------------------------

def _get_sourcepos(attr: list) -> Optional[int]:
    """Extract the start line of the full table span from a Pandoc sourcepos Attr.

    Pandoc's data-pos for pipe tables may contain two semicolon-separated
    ranges: the first covers the separator row, the second covers the entire
    table (header through last body row).  We want the earliest start line
    across all ranges — that is the header row.
    """
    for key, val in attr[2]:
        if key == "data-pos":
            # Strip optional "filepath@" prefix.
            pos = val.split("@")[-1]
            # Multiple ranges separated by ";".
            min_line = None
            for span in pos.split(";"):
                start = span.split("-")[0]
                line = int(start.split(":")[0])
                if min_line is None or line < min_line:
                    min_line = line
            return min_line
    return None


def _unwrap_sourcepos_spans(inlines: list) -> list:
    """Unwrap Span nodes injected by Pandoc's +sourcepos extension.

    With +sourcepos, every inline is wrapped in a Span carrying a
    data-pos attribute.  This function peels those wrappers so that the
    structural content (Strong, Code, Str, …) is directly visible.
    """
    result = []
    for node in inlines:
        if (isinstance(node, dict)
                and node.get("t") == "Span"
                and any(k == "wrapper" for k, _ in node["c"][0][2])):
            result.extend(_unwrap_sourcepos_spans(node["c"][1]))
        else:
            result.append(node)
    return result


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
        inlines = _unwrap_sourcepos_spans(block.get("c", []))
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
        table_lineno = _get_sourcepos(table_attr)

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

    all_violations.sort(key=lambda v: (str(v.file), v.lineno))
    return all_violations


# ---------------------------------------------------------------------------
# Source-level fix
# ---------------------------------------------------------------------------

def _is_separator_line(line: str) -> bool:
    """Return True if *line* is a pipe-table separator row."""
    return bool(_SEPARATOR_RE.match(line))


def _bold_header_row(line: str) -> str:
    """Wrap non-bold, non-code cells in a pipe-table header row with **…**.

    Splits the line by ``|``, processes each cell, and reassembles.
    Cells that are already bold (``**…**``) or are code spans (``` `…` ```)
    are left unchanged.  Empty/whitespace-only cells are left unchanged.
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
        original = lines[idx]
        newline_suffix = ''
        if original.endswith('\n'):
            newline_suffix = '\n'
            original = original[:-1]
        bolded = _bold_header_row(original)
        if bolded != original:
            lines[idx] = bolded + newline_suffix
            fixed += 1

    if fixed:
        path.write_text(''.join(lines), encoding='utf-8')

    return fixed


def fix_spec(
    spec_root: Path,
    workers: int = DEFAULT_WORKERS,
) -> Tuple[int, int]:
    """Fix all violations under *spec_root*.  Returns (files_fixed, rows_fixed)."""
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
                header_text=v.header_text,
                non_bold_cells=v.non_bold_cells,
            )
            block_lines.append(display_v.format())
            total += 1
        sections.append('\n'.join(block_lines))

    file_count = len(by_file)
    header = f'{total} bold-table-header violation(s) in {file_count} file(s)\n'
    return header + '\n' + '\n\n'.join(sections)


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

        # Group and fix.
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
