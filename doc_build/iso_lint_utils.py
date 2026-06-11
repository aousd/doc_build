"""Shared utilities for ISO linters.

Common helpers used by ``iso_heading_case_lint``, ``iso_bold_table_lint``,
and ``iso_clause_lint``.
"""

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, List, Optional

try:
    from doc_build.filters.pandocfilters import stringify
except ImportError:
    from filters.pandocfilters import stringify

# Re-export so linters can ``from doc_build.iso_lint_utils import stringify``.
__all__ = [
    "DEFAULT_WORKERS",
    "collect_md_files",
    "format_report",
    "get_sourcepos",
    "run_parallel_check",
    "stringify",
    "unwrap_sourcepos_spans",
]

# Maximum number of parallel Pandoc subprocesses.
DEFAULT_WORKERS = 8


def collect_md_files(path: Path) -> List[Path]:
    """Return a list of ``.md`` files under *path*.

    *path* may be a single file or a directory (walked recursively).
    """
    path = Path(path)
    if path.is_file():
        return [path] if path.suffix == '.md' else []
    md_files: List[Path] = []
    for dirpath, dirnames, filenames in os.walk(path):
        dirnames.sort()
        for fname in sorted(filenames):
            if fname.endswith('.md'):
                md_files.append(Path(dirpath) / fname)
    return md_files


def run_parallel_check(
    md_files: List[Path],
    check_fn: Callable,
    sort_key: Callable,
    workers: int = DEFAULT_WORKERS,
) -> list:
    """Run *check_fn* on each file in parallel and return sorted results.

    *check_fn* is called with a single ``Path`` argument and must return
    a list of violation objects.  Results are concatenated, sorted by
    *sort_key*, and returned.
    """
    all_violations: list = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(check_fn, p): p for p in md_files}
        for future in as_completed(futures):
            all_violations.extend(future.result())
    all_violations.sort(key=sort_key)
    return all_violations


def get_sourcepos(attr: list) -> Optional[int]:
    """Extract the start line number from a Pandoc sourcepos Attr.

    Attr layout: ``[id, [classes], [[key, value], ...]]``

    When Pandoc reads from a file the ``data-pos`` value has the form
    ``filepath@startrow:startcol-endrow:endcol``; when reading from stdin
    it omits the ``filepath@`` prefix.  Both forms are handled here.

    Pandoc's data-pos for pipe tables may contain multiple
    semicolon-separated ranges.  This function returns the minimum start
    line across all ranges, which is the header row for tables and the
    only range for headings and other blocks.

    Returns the start row as a 1-based integer, or ``None`` if the
    attribute is absent.
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


def format_report(
    violations: List[Any],
    label: str,
    spec_root: Optional[Path] = None,
    **format_kwargs,
) -> str:
    """Format a list of violations into a human-readable report.

    Each violation must have a ``.file`` attribute (a ``Path``) and a
    ``.format(display_path=..., **kwargs)`` method.

    *label* is a short noun phrase used in the summary line, e.g.
    ``"heading case"`` → ``"3 heading case violation(s) in 2 file(s)"``.

    Extra *format_kwargs* are forwarded to each violation's ``.format()``
    call (e.g. ``context=5`` for the clause linter).
    """
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
            block_lines.append(v.format(display_path=rel_path, **format_kwargs))
            total += 1
        sections.append('\n'.join(block_lines))

    file_count = len(by_file)
    header = f'{total} {label} violation(s) in {file_count} file(s)\n'
    return header + '\n' + '\n\n'.join(sections)


def unwrap_sourcepos_spans(inlines: list) -> list:
    """Unwrap Span nodes injected by Pandoc's +sourcepos extension.

    With +sourcepos, every inline is wrapped in a Span carrying a
    ``data-pos`` attribute.  This function peels those wrappers so that
    the structural content (Strong, Code, Str, ...) is directly visible.
    """
    result = []
    for node in inlines:
        if (isinstance(node, dict)
                and node.get("t") == "Span"
                and any(k == "wrapper" for k, _ in node["c"][0][2])):
            result.extend(unwrap_sourcepos_spans(node["c"][1]))
        else:
            result.append(node)
    return result
