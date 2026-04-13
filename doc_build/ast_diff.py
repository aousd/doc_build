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
            result.append(make_substitution_div(deletions[j], insertions[j]))
        for node in deletions[n_pairs:]:
            result.append(add_diff_meta(node, "deletion"))
        for node in insertions[n_pairs:]:
            result.append(add_diff_meta(node, "insertion"))

    return result


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
