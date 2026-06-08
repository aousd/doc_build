#!/usr/bin/env python3
"""Pandoc filter: bold table header cells per ISO/IEC Directives, Part 2.

ISO/IEC Directives, Part 2 requires that table column headings shall be
in bold type.  This filter walks every Table node in the Pandoc AST and
wraps the inline content of each header cell in Strong (bold).

Cells that are already bold are left visually unchanged (the outer Strong
is still added, producing harmless nested ``<strong><strong>…`` in HTML
or ``\\textbf{\\textbf{…}}`` in LaTeX — both render identically).

Only Para and Plain blocks inside header cells are wrapped; other block
types (CodeBlock, BulletList, …) are passed through untouched since they
are uncommon in header cells and would not benefit from a Strong wrapper.
"""

from copy import deepcopy
from pandocfilters import toJSONFilter


def boldify_inline(inline, inside_strong=False):
    """Recursively process a single inline element for bolding.

    If the node is already Strong, recurse into its children (with the
    *inside_strong* flag set) but do not add another Strong wrapper.
    For every other node type, deepcopy it and recurse into its ``c``
    value so that nested inlines (Emph inside a Link, etc.) are handled.

    Returns a new (possibly transformed) inline node.
    """
    if not isinstance(inline, dict):
        return inline

    t = inline["t"]

    # Already bold — recurse into children but skip re-wrapping.
    if t == "Strong":
        return {
            "t": "Strong",
            "c": [
                boldify_inline(x, inside_strong=True)
                for x in inline["c"]
            ]
        }

    # Any other inline: deepcopy to avoid mutating the original AST,
    # then recurse into the node's content.
    result = deepcopy(inline)

    if "c" in result:
        result["c"] = boldify_value(
            result["c"],
            inside_strong=inside_strong
        )

    return result


def boldify_value(value, inside_strong=False):
    """Recursively walk an arbitrary Pandoc AST value (list, dict, or scalar).

    Dispatches typed dict nodes (those with a ``t`` key) to
    ``boldify_inline``; recurses into plain dicts and lists; returns
    scalars unchanged.
    """
    if isinstance(value, list):
        return [
            boldify_value(x, inside_strong)
            for x in value
        ]

    if isinstance(value, dict):
        # Typed AST node — delegate to inline handler.
        if "t" in value:
            return boldify_inline(
                value,
                inside_strong=inside_strong
            )

        # Untyped dict (e.g. metadata maps) — recurse into values.
        return {
            k: boldify_value(v, inside_strong)
            for k, v in value.items()
        }

    return value


def wrap_block_in_strong(block):
    """Wrap a Para or Plain block's inlines in a single Strong node.

    Transforms::

        Para  [inline, inline, …]
        Plain [inline, inline, …]

    into::

        Para  [Strong [inline, inline, …]]
        Plain [Strong [inline, inline, …]]

    Non-Para/Plain blocks (CodeBlock, BulletList, etc.) are returned
    unchanged — they are uncommon in table headers and would not
    benefit from bold wrapping.
    """
    if not isinstance(block, dict):
        return block

    t = block.get("t")

    if t not in ("Para", "Plain"):
        return block

    # Process children first so any pre-existing Strong nodes are
    # handled by boldify_inline before the outer wrap.
    inlines = [
        boldify_inline(x)
        for x in block["c"]
    ]

    return {
        "t": t,
        "c": [
            {
                "t": "Strong",
                "c": inlines
            }
        ]
    }


def process_cell_blocks(blocks):
    """Apply bold wrapping to every block inside a single header cell."""
    return [
        wrap_block_in_strong(block)
        for block in blocks
    ]


def process_table_head(head):
    """Walk the TableHead structure and bold every header cell.

    Pandoc 3.x TableHead layout::

        TableHead = [ head_attr, rows ]
        Row       = [ row_attr,  cells ]
        Cell      = [ attr, alignment, rowspan, colspan, blocks ]
    """
    head_attr, rows = head

    new_rows = []

    for row in rows:
        row_attr, cells = row

        new_cells = []

        for cell in cells:
            attr, alignment, rowspan, colspan, blocks = cell

            new_cells.append([
                attr,
                alignment,
                rowspan,
                colspan,
                process_cell_blocks(blocks)
            ])

        new_rows.append([
            row_attr,
            new_cells
        ])

    return [head_attr, new_rows]


def bold_table_headers(key, value, fmt, meta):
    """Top-level filter action: intercept Table nodes and bold their heads."""
    if key != "Table":
        return None

    # Pandoc 3.x Table layout:
    #   Table [ attr, caption, colspecs, head, bodies, foot ]
    attr, caption, colspecs, head, bodies, foot = value

    return {
        "t": "Table",
        "c": [
            attr,
            caption,
            colspecs,
            process_table_head(head),
            bodies,
            foot
        ]
    }


if __name__ == "__main__":
    toJSONFilter(bold_table_headers)
