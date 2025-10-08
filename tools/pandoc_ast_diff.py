#!/usr/bin/env python3

"""
Pandoc AST Differencing Tool

This script takes two JSON files representing Pandoc Abstract Syntax Trees (ASTs),
computes the difference between them, and outputs a new Pandoc AST JSON file.
The output file contains a merged view, with added or removed
nodes annotated with custom metadata.

The core logic uses the Longest Common Subsequence (LCS) algorithm to align
the block-level elements of the two documents.

- **Added** blocks from the new file are included and marked.
- **Removed** blocks from the old file are included and marked.
- **Changed** blocks are detected by a direct comparison of common elements and
  are included (from the new version) with a 'changed' mark.

Metadata is added by wrapping the target block in a Pandoc 'Div' element
with the attribute `diff=<status>`, where status is one of:
- 'added'
- 'removed'

Usage:
    python pandoc_ast_diff.py before.json after.json output.json
"""

import json
import argparse
from typing import List, Dict, Any, Tuple

PandocNode = Dict[str, Any]
PandocAst = Dict[str, Any]
NodeList = List[PandocNode]

def add_diff_meta(node: PandocNode, status: str) -> PandocNode:
    """
    Wraps a Pandoc AST node in a Div block to add diff metadata.

    This is the standard Pandoc method for adding block-level attributes.

    Args:
        node: The Pandoc node to wrap.
        status: The difference status ('added', 'removed').

    Returns:
        A new 'Div' node containing the original node and the diff attribute.
    """
    attr: Tuple[str, List[str], List[Tuple[str, str]]] = ("", [], [("diff", status)])
    
    return {"t": "Div", "c": [attr, [node]]}

def find_longest_common_subsequence(list_a: NodeList, list_b: NodeList) -> NodeList:
    """
    Computes the Longest Common Subsequence (LCS) of two lists of nodes.
    
    This uses a classic dynamic programming approach. The nodes are compared
    for deep equality.
    """
    m, n = len(list_a), len(list_b)
    dp = [[[] for _ in range(n + 1)] for _ in range(m + 1)]

    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if json.dumps(list_a[i-1], sort_keys=True) == json.dumps(list_b[j-1], sort_keys=True):
                dp[i][j] = dp[i-1][j-1] + [list_a[i-1]]
            else:
                if len(dp[i-1][j]) > len(dp[i][j-1]):
                    dp[i][j] = dp[i-1][j]
                else:
                    dp[i][j] = dp[i][j-1]
    return dp[m][n]

def diff_block_lists(before_blocks: NodeList, after_blocks: NodeList) -> NodeList:
    """
    Compares two lists of Pandoc blocks and generates a merged list with annotations.

    This is the core diffing engine. It walks through both lists and the LCS
    to identify added and removed blocks.
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
            merged_blocks.append(add_diff_meta(node_a, "removed"))
            ptr_a += 1
        elif node_b and node_b_str not in lcs_set:
            # This node from 'after' is not in the LCS, so it was added.
            merged_blocks.append(add_diff_meta(node_b, "added"))
            ptr_b += 1
        elif node_a and node_b:
            # Both nodes are present and part of the LCS path.
            # Check if they are identical. If not, mark as changed.
            if node_a_str != node_b_str:
                # The content at this aligned position has changed.
                # Mark the 'before' version as removed and 'after' as added.
                # This is a common way to show a "change".
                merged_blocks.append(add_diff_meta(node_a, "removed"))
                merged_blocks.append(add_diff_meta(node_b, "added"))
            else:
                # The blocks are identical, add them without modification.
                merged_blocks.append(node_a)
            ptr_a += 1
            ptr_b += 1
        elif ptr_a < len(before_blocks):
            # Exhausted 'after_blocks', remaining 'before' blocks are removals.
             merged_blocks.append(add_diff_meta(before_blocks[ptr_a], "removed"))
             ptr_a += 1
        elif ptr_b < len(after_blocks):
             # Exhausted 'before_blocks', remaining 'after' blocks are additions.
             merged_blocks.append(add_diff_meta(after_blocks[ptr_b], "added"))
             ptr_b += 1

    return merged_blocks

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Diff two Pandoc AST JSON files and annotate the changes.")
    parser.add_argument("before_file", help="Path to the 'before' Pandoc JSON file.")
    parser.add_argument("after_file", help="Path to the 'after' Pandoc JSON file.")
    parser.add_argument("output_file", help="Path for the output annotated JSON file.")
    
    args = parser.parse_args()

    with open(args.before_file, 'r', encoding='utf-8') as f:
        before_ast: PandocAst = json.load(f)

    with open(args.after_file, 'r', encoding='utf-8') as f:
        after_ast: PandocAst = json.load(f)

    before_blocks: NodeList = before_ast.get("blocks", [])
    after_blocks: NodeList = after_ast.get("blocks", [])

    merged_blocks = diff_block_lists(before_blocks, after_blocks)
    
    output_ast: PandocAst = {
        "pandoc-api-version": after_ast["pandoc-api-version"],
        "meta": after_ast["meta"],
        "blocks": merged_blocks
    }

    with open(args.output_file, 'w', encoding='utf-8') as f:
        json.dump(output_ast, f, indent=2)