"""Pandoc AST differencing. Core logic for the Pandoc AST Differencing Tool.

The core logic uses the Longest Common Subsequence (LCS) algorithm to align
the block-level elements of the two documents.

- **Added** blocks from the new file are included and marked.
- **Removed** blocks from the old file are included and marked.
- **Changed** blocks are detected by a direct comparison of common elements and
  are included as a substitution Div wrapping a deletion and an insertion Div.

Metadata is added by wrapping the target block in a Pandoc 'Div' element
with a class indicating its diff status:
- class 'insertion' for added blocks
- class 'deletion' for removed blocks
- class 'substitution' wrapping a deletion Div and insertion Div for changed blocks
"""

import json

from typing import List, Dict, Any, Tuple

PandocNode = Dict[str, Any]
PandocAst = Dict[str, Any]
NodeList = List[PandocNode]


def add_diff_meta(node: PandocNode, css_class: str) -> PandocNode:
    """
    Wraps a Pandoc AST node in a Div block to add diff metadata.

    This is the standard Pandoc method for adding block-level attributes.

    Args:
        node: The Pandoc node to wrap.
        css_class: The diff class ('insertion', 'deletion').

    Returns:
        A new 'Div' node containing the original node and the diff class.
    """
    attr: Tuple[str, List[str], List[Tuple[str, str]]] = ("", [css_class], [])

    return {"t": "Div", "c": [attr, [node]]}


def make_substitution_div(old_node: PandocNode, new_node: PandocNode) -> PandocNode:
    """
    Wraps old and new nodes in a substitution Div for changed blocks.

    The substitution Div contains a deletion Div (old_node) followed by an
    insertion Div (new_node).

    Args:
        old_node: The 'before' version of the block (will be wrapped as deletion).
        new_node: The 'after' version of the block (will be wrapped as insertion).

    Returns:
        A new 'Div' node with class 'substitution' containing the two diff Divs.
    """
    deletion_div = add_diff_meta(old_node, "deletion")
    insertion_div = add_diff_meta(new_node, "insertion")
    attr: Tuple[str, List[str], List[Tuple[str, str]]] = ("", ["substitution"], [])
    return {"t": "Div", "c": [attr, [deletion_div, insertion_div]]}


def find_longest_common_subsequence(list_a: NodeList, list_b: NodeList) -> NodeList:
    """
    Computes the Longest Common Subsequence (LCS) of two lists of nodes.

    This uses a classic dynamic programming approach. The nodes are compared
    for deep equality.
    """
    m, n = len(list_a), len(list_b)
    dp = [[[] for _ in range(n + 1)] for _ in range(m + 1)]
    a_strs = [json.dumps(node, sort_keys=True) for node in list_a]
    b_strs = [json.dumps(node, sort_keys=True) for node in list_b]

    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if a_strs[i - 1] == b_strs[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + [list_a[i - 1]]
            else:
                if len(dp[i - 1][j]) > len(dp[i][j - 1]):
                    dp[i][j] = dp[i - 1][j]
                else:
                    dp[i][j] = dp[i][j - 1]
    return dp[m][n]


def _pair_adjacent_changes(blocks: NodeList) -> NodeList:
    """Pair adjacent deletion+insertion runs into substitution Divs.

    The LCS-based diff emits all deletions before all insertions within a
    changed section (because nodes not in the LCS are drained from 'before'
    first). This pass pairs them 1-to-1 as substitution Divs so the render
    filter can produce per-word inline diffs.

    Excess deletions or insertions (when counts differ) remain as-is.
    """

    def _div_classes(block: PandocNode) -> List[str]:
        if block.get("t") == "Div" and block.get("c"):
            return block["c"][0][1]
        return []

    result: NodeList = []
    i = 0
    while i < len(blocks):
        if "deletion" not in _div_classes(blocks[i]):
            result.append(blocks[i])
            i += 1
            continue

        # Collect a consecutive run of deletions.
        deletions: NodeList = []
        while i < len(blocks) and "deletion" in _div_classes(blocks[i]):
            deletions.append(blocks[i]["c"][1][0])  # unwrap inner block
            i += 1

        # Collect the immediately following run of insertions.
        insertions: NodeList = []
        while i < len(blocks) and "insertion" in _div_classes(blocks[i]):
            insertions.append(blocks[i]["c"][1][0])  # unwrap inner block
            i += 1

        # Pair 1-to-1 as substitutions; excess remain as bare deletions/insertions.
        n_pairs = min(len(deletions), len(insertions))
        for j in range(n_pairs):
            d, ins = deletions[j], insertions[j]
            if _is_list_node(d) and _is_list_node(ins) and d.get("t") == ins.get("t"):
                result.append(diff_list_nodes(d, ins))
            elif d.get("t") == "BlockQuote" and ins.get("t") == "BlockQuote":
                result.append(diff_block_quote_nodes(d, ins))
            elif d.get("t") == "LineBlock" and ins.get("t") == "LineBlock":
                result.extend(diff_line_block_nodes(d, ins))
            else:
                result.append(make_substitution_div(d, ins))
        for node in deletions[n_pairs:]:
            result.append(add_diff_meta(node, "deletion"))
        for node in insertions[n_pairs:]:
            result.append(add_diff_meta(node, "insertion"))

    return result


LIST_TYPES = frozenset({"BulletList", "OrderedList"})


def _is_list_node(node: PandocNode) -> bool:
    return node.get("t") in LIST_TYPES


def _get_list_items(node: PandocNode) -> List[List[PandocNode]]:
    t, c = node.get("t"), node["c"]
    if t == "BulletList":
        return c
    _, items = c  # OrderedList: c = [list_attrs, items]
    return items


def _build_list_with_items(node: PandocNode, items: List[List[PandocNode]]) -> PandocNode:
    t, c = node.get("t"), node["c"]
    if t == "BulletList":
        return {"t": "BulletList", "c": items}
    list_attrs, _ = c  # OrderedList
    return {"t": "OrderedList", "c": [list_attrs, items]}


def _item_to_block(item: List[PandocNode]) -> PandocNode:
    """Convert a list item's blocks to a single block for diff wrapping.

    Used for unpaired deletions/insertions.  Single-block items are returned
    as-is (the common case: Plain or Para).  Multi-block items are wrapped in
    an anonymous Div so they can be passed to add_diff_meta as a unit.
    """
    if len(item) == 1:
        return item[0]
    return {"t": "Div", "c": [("", [], []), item]}


def diff_list_nodes(old_node: PandocNode, new_node: PandocNode) -> PandocNode:
    """Diff two same-type list nodes at the item level.

    Returns a single reconstructed list node whose items carry per-item
    insertion/deletion/substitution Div annotations.  For changed item pairs
    where both items contain a single Plain/Para block, the substitution Div
    triggers word-level inline diffing in the render filter.
    """
    old_items = _get_list_items(old_node)
    new_items = _get_list_items(new_node)

    # find_longest_common_subsequence serializes each element via json.dumps, so
    # it works on list items (List[PandocNode]) just as well as on PandocNode.
    lcs = find_longest_common_subsequence(old_items, new_items)  # type: ignore
    lcs_strs = {json.dumps(item, sort_keys=True) for item in lcs}

    # Walk like diff_block_lists to produce an ordered stream of (op, item) pairs.
    raw: List[Tuple[str, List[PandocNode]]] = []
    ptr_a, ptr_b = 0, 0
    while ptr_a < len(old_items) or ptr_b < len(new_items):
        a = old_items[ptr_a] if ptr_a < len(old_items) else None
        b = new_items[ptr_b] if ptr_b < len(new_items) else None
        a_str = json.dumps(a, sort_keys=True) if a is not None else None
        b_str = json.dumps(b, sort_keys=True) if b is not None else None

        if a is not None and a_str not in lcs_strs:
            raw.append(("deletion", a))
            ptr_a += 1
        elif b is not None and b_str not in lcs_strs:
            raw.append(("insertion", b))
            ptr_b += 1
        elif a is not None and b is not None:
            raw.append(("equal", a))
            ptr_a += 1
            ptr_b += 1
        elif ptr_a < len(old_items):
            raw.append(("deletion", old_items[ptr_a]))
            ptr_a += 1
        else:
            raw.append(("insertion", new_items[ptr_b]))
            ptr_b += 1

    # Pair consecutive deletion+insertion runs into substitution items.
    result_items: List[List[PandocNode]] = []
    i = 0
    while i < len(raw):
        op, item = raw[i]
        if op == "equal":
            result_items.append(item)
            i += 1
            continue
        if op == "insertion":
            result_items.append([add_diff_meta(_item_to_block(item), "insertion")])
            i += 1
            continue

        # Collect a run of deletions then the immediately following insertions.
        deletions: List[List[PandocNode]] = []
        while i < len(raw) and raw[i][0] == "deletion":
            deletions.append(raw[i][1])
            i += 1
        insertions: List[List[PandocNode]] = []
        while i < len(raw) and raw[i][0] == "insertion":
            insertions.append(raw[i][1])
            i += 1

        n_pairs = min(len(deletions), len(insertions))
        for j in range(n_pairs):
            result_items.append(diff_block_lists(deletions[j], insertions[j]))
        for del_item in deletions[n_pairs:]:
            result_items.append([add_diff_meta(_item_to_block(del_item), "deletion")])
        for ins_item in insertions[n_pairs:]:
            result_items.append([add_diff_meta(_item_to_block(ins_item), "insertion")])

    return _build_list_with_items(old_node, result_items)


def diff_block_quote_nodes(old_node: PandocNode, new_node: PandocNode) -> PandocNode:
    """Diff two BlockQuote nodes at the block level.

    Recursively diffs the content blocks of both BlockQuotes and returns a
    single reconstructed BlockQuote whose contents carry per-block
    insertion/deletion/substitution annotations.  Because the contents are
    passed through diff_block_lists, any iterable types nested inside the
    BlockQuote (lists, further BlockQuotes, LineBlocks) are themselves
    recursively diffed.
    """
    diffed_blocks = diff_block_lists(old_node["c"], new_node["c"])
    return {"t": "BlockQuote", "c": diffed_blocks}


def _line_to_plain(line: List[PandocNode]) -> PandocNode:
    """Convert a LineBlock line (list of inlines) to a Plain block."""
    return {"t": "Plain", "c": line}


def diff_line_block_nodes(old_node: PandocNode, new_node: PandocNode) -> NodeList:
    """Diff two LineBlock nodes at the line level.

    Converts each line to a Plain block and delegates to diff_block_lists,
    which handles LCS matching, pairing, and substitution Div creation.
    Changed line pairs become substitution Divs wrapping Plain blocks, so
    the render filter applies word-level diffs to each changed line.

    Returns a flat NodeList rather than a single node; callers must use
    extend() rather than append() when inserting into a block list.
    """
    old_blocks = [_line_to_plain(line) for line in old_node["c"]]
    new_blocks = [_line_to_plain(line) for line in new_node["c"]]
    return diff_block_lists(old_blocks, new_blocks)


def diff_block_lists(before_blocks: NodeList, after_blocks: NodeList) -> NodeList:
    """
    Compares two lists of Pandoc blocks and generates a merged list with annotations.

    This is the core diffing engine. It walks through both lists and the LCS
    to identify added and removed blocks, then pairs adjacent deletion+insertion
    groups as substitution Divs for per-word inline diffing.
    """
    lcs_nodes = find_longest_common_subsequence(before_blocks, after_blocks)
    lcs_set = {json.dumps(node, sort_keys=True) for node in lcs_nodes}

    merged_blocks: NodeList = []

    ptr_a, ptr_b = 0, 0
    while ptr_a < len(before_blocks) or ptr_b < len(after_blocks):
        node_a = before_blocks[ptr_a] if ptr_a < len(before_blocks) else None
        node_b = after_blocks[ptr_b] if ptr_b < len(after_blocks) else None

        node_a_str = json.dumps(node_a, sort_keys=True) if node_a else None
        node_b_str = json.dumps(node_b, sort_keys=True) if node_b else None

        if node_a and node_a_str not in lcs_set:
            # This node from 'before' is not in the LCS, so it was removed.
            merged_blocks.append(add_diff_meta(node_a, "deletion"))
            ptr_a += 1
        elif node_b and node_b_str not in lcs_set:
            # This node from 'after' is not in the LCS, so it was added.
            merged_blocks.append(add_diff_meta(node_b, "insertion"))
            ptr_b += 1
        elif node_a and node_b:
            # Both nodes are in the LCS (and therefore identical).
            merged_blocks.append(node_a)
            ptr_a += 1
            ptr_b += 1
        elif ptr_a < len(before_blocks):
            # Exhausted 'after_blocks', remaining 'before' blocks are removals.
            merged_blocks.append(add_diff_meta(before_blocks[ptr_a], "deletion"))
            ptr_a += 1
        elif ptr_b < len(after_blocks):
            # Exhausted 'before_blocks', remaining 'after' blocks are additions.
            merged_blocks.append(add_diff_meta(after_blocks[ptr_b], "insertion"))
            ptr_b += 1

    return _pair_adjacent_changes(merged_blocks)


def diff_ast_files(before_path, after_path, output_path):
    """Read two Pandoc AST JSON files, diff their blocks, write the result."""
    with open(before_path, "r", encoding="utf-8") as f:
        before_ast: PandocAst = json.load(f)

    with open(after_path, "r", encoding="utf-8") as f:
        after_ast: PandocAst = json.load(f)

    before_blocks: NodeList = before_ast.get("blocks", [])
    after_blocks: NodeList = after_ast.get("blocks", [])

    merged_blocks = diff_block_lists(before_blocks, after_blocks)

    output_ast: PandocAst = {
        "pandoc-api-version": after_ast["pandoc-api-version"],
        "meta": after_ast["meta"],
        "blocks": merged_blocks,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_ast, f, indent=2)

    return output_ast
