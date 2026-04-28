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

from collections.abc import Callable
from typing import List, Dict, Any, Optional, Tuple

from doc_build.filters.shared_filter_utils import HASH_ATTR_KEY

PandocNode = Dict[str, Any]
PandocAst = Dict[str, Any]
NodeList = List[PandocNode]

IMAGE_ATTRIBUTES_CHANGED_KEY = "image_attributes_changed"


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


def make_substitution_div(
    old_node: PandocNode,
    new_node: PandocNode,
    extra_kv: Optional[List[Tuple[str, str]]] = None,
) -> PandocNode:
    """
    Wraps old and new nodes in a substitution Div for changed blocks.

    The substitution Div contains a deletion Div (old_node) followed by an
    insertion Div (new_node).

    Args:
        old_node: The 'before' version of the block (will be wrapped as deletion).
        new_node: The 'after' version of the block (will be wrapped as insertion).
        extra_kv: Optional key-value pairs to attach to the substitution Div's
            attributes (used e.g. to carry image_attributes_changed metadata).

    Returns:
        A new 'Div' node with class 'substitution' containing the two diff Divs.
    """
    deletion_div = add_diff_meta(old_node, "deletion")
    insertion_div = add_diff_meta(new_node, "insertion")
    kv: List[Tuple[str, str]] = list(extra_kv) if extra_kv else []
    attr: Tuple[str, List[str], List[Tuple[str, str]]] = ("", ["substitution"], kv)
    return {"t": "Div", "c": [attr, [deletion_div, insertion_div]]}


def diff_image_attributes(old_img: PandocNode, new_img: PandocNode) -> List[str]:
    """Return the list of attribute names that differ between two Image nodes.

    Recognized attribute names: 'binary' (SHA-256 content hash from
    data-image-hash), 'path' (image URL/filename), 'title', 'caption',
    'id', 'classes', plus any other attribute key present in the Image's
    key-value list (e.g. 'width', 'height').  Caption is compared as the
    full inline AST so formatting-only changes (e.g. adding Emph) count
    as a change.  Order is stable: binary, path, title, caption, id,
    classes, then remaining kv keys sorted.
    """
    old_attr, old_caption, old_target = old_img["c"]
    new_attr, new_caption, new_target = new_img["c"]
    old_id, old_classes, old_kv = old_attr
    new_id, new_classes, new_kv = new_attr
    old_kv_map = dict(old_kv)
    new_kv_map = dict(new_kv)

    changed: List[str] = []
    if old_kv_map.get(HASH_ATTR_KEY) != new_kv_map.get(HASH_ATTR_KEY):
        changed.append("binary")
    if old_target[0] != new_target[0]:
        changed.append("path")
    if old_target[1] != new_target[1]:
        changed.append("title")
    if old_caption != new_caption:
        changed.append("caption")
    if old_id != new_id:
        changed.append("id")
    if old_classes != new_classes:
        changed.append("classes")
    extra_keys = (set(old_kv_map) | set(new_kv_map)) - {HASH_ATTR_KEY}
    for k in sorted(extra_keys):
        if old_kv_map.get(k) != new_kv_map.get(k):
            changed.append(k)
    return changed


def _extract_single_image(block: PandocNode) -> Optional[PandocNode]:
    """Return the Image node from a block that contains exactly one Image.

    Handles Figure, Para, and Plain block containers.  For Para/Plain,
    allows whitespace-only siblings (Space, SoftBreak) alongside the Image.
    Returns None for any other structure.
    """
    t = block.get("t")
    if t == "Figure":
        # Figure c = [attr, caption, content (blocks)]
        _attr, _caption, content = block["c"]
        if len(content) != 1:
            return None
        return _extract_single_image(content[0])
    if t in ("Para", "Plain"):
        inlines = block.get("c", [])
        image: Optional[PandocNode] = None
        for n in inlines:
            nt = n.get("t")
            if nt == "Image":
                if image is not None:
                    return None
                image = n
            elif nt in ("Space", "SoftBreak"):
                continue
            else:
                return None
        return image
    return None


def _image_substitution_kv(
    old_block: PandocNode, new_block: PandocNode
) -> Optional[List[Tuple[str, str]]]:
    """Return substitution kv pairs describing image attribute changes, if any.

    Returns None if either block does not contain a single Image, or if the
    two images have no differing attributes.
    """
    old_img = _extract_single_image(old_block)
    new_img = _extract_single_image(new_block)
    if old_img is None or new_img is None:
        return None
    changed = diff_image_attributes(old_img, new_img)
    if not changed:
        return None
    return [(IMAGE_ATTRIBUTES_CHANGED_KEY, ",".join(changed))]


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


def _pair_adjacent_changes(
    raw: List[Tuple[str, Any]],
    *,
    pair: Callable[[Any, Any], List[Any]],
    wrap_deletion: Callable[[Any], Any],
    wrap_insertion: Callable[[Any], Any],
) -> List[Any]:
    """Walk an ``(op, element)`` stream from `_merge_with_lcs` and fold
    adjacent deletion+insertion runs into per-pair recursive diffs (or
    substitutions).

    ``"equal"`` elements pass through unchanged.  Each contiguous deletion run
    is gathered together with its immediately following insertion run; pairs
    are converted via ``pair(deletion, insertion)``, which returns a (possibly
    empty or multi-element) list of result elements to splice in.  Excess
    unpaired deletions / insertions are emitted via ``wrap_deletion`` /
    ``wrap_insertion`` respectively.

    Generic over element type: callers pass blocks (``PandocNode``) or list
    items (``List[PandocNode]``) and supply matching callbacks.  The LCS-based
    diff in `_merge_with_lcs` always emits deletions before insertions within
    each gap, which is what this function expects.
    """
    result: List[Any] = []
    i = 0
    while i < len(raw):
        op, element = raw[i]
        if op == "equal":
            result.append(element)
            i += 1
            continue
        if op == "insertion":
            # Insertion not preceded by a deletion run: emit bare.
            result.append(wrap_insertion(element))
            i += 1
            continue
        # op == "deletion".  Gather the deletion run, then any immediately
        # following insertion run.
        deletions: List[Any] = []
        while i < len(raw) and raw[i][0] == "deletion":
            deletions.append(raw[i][1])
            i += 1
        insertions: List[Any] = []
        while i < len(raw) and raw[i][0] == "insertion":
            insertions.append(raw[i][1])
            i += 1
        n_pairs = min(len(deletions), len(insertions))
        for j in range(n_pairs):
            result.extend(pair(deletions[j], insertions[j]))
        for d in deletions[n_pairs:]:
            result.append(wrap_deletion(d))
        for ins in insertions[n_pairs:]:
            result.append(wrap_insertion(ins))
    return result


def _pair_blocks(d: PandocNode, ins: PandocNode) -> NodeList:
    """Pair strategy for `diff_block_lists`: recurse for like containers,
    otherwise produce a substitution Div."""
    if _is_list_node(d) and _is_list_node(ins) and d.get("t") == ins.get("t"):
        return [diff_list_nodes(d, ins)]
    if d.get("t") == "BlockQuote" and ins.get("t") == "BlockQuote":
        return [diff_block_quote_nodes(d, ins)]
    if d.get("t") == "LineBlock" and ins.get("t") == "LineBlock":
        return diff_line_block_nodes(d, ins)
    return [make_substitution_div(d, ins, extra_kv=_image_substitution_kv(d, ins))]


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

    # find_longest_common_subsequence and _merge_with_lcs both serialize each
    # element via json.dumps, so they work on list items (List[PandocNode])
    # just as well as on PandocNode.
    lcs = find_longest_common_subsequence(old_items, new_items)  # type: ignore
    raw = _merge_with_lcs(old_items, new_items, lcs)  # type: ignore

    result_items = _pair_adjacent_changes(
        raw,
        pair=lambda d, ins: [diff_block_lists(d, ins)],
        wrap_deletion=lambda item: [add_diff_meta(_item_to_block(item), "deletion")],
        wrap_insertion=lambda item: [add_diff_meta(_item_to_block(item), "insertion")],
    )
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
    raw = _merge_with_lcs(before_blocks, after_blocks, lcs_nodes)
    return _pair_adjacent_changes(
        raw,
        pair=_pair_blocks,
        wrap_deletion=lambda b: add_diff_meta(b, "deletion"),
        wrap_insertion=lambda b: add_diff_meta(b, "insertion"),
    )


def _merge_with_lcs(
    before: List[Any],
    after: List[Any],
    lcs_elements: List[Any],
) -> List[Tuple[str, Any]]:
    """Walk `before` and `after` in lockstep with the LCS, yielding an ordered
    stream of ``(op, element)`` tuples in document order.

    `op` is one of ``"equal"``, ``"deletion"`` or ``"insertion"``.  Elements
    not in the LCS are emitted as deletions (from `before`) or insertions
    (from `after`); LCS elements are emitted as ``"equal"``.  Within each
    changed gap, deletions are emitted before insertions, which is what
    `_pair_adjacent_changes` needs to fold them into substitution-style
    annotations.

    Elements may be Pandoc blocks (``PandocNode``) or list items
    (``List[PandocNode]``); the only requirement is that ``json.dumps(element,
    sort_keys=True)`` gives a stable equality key.
    """
    lcs_set = {json.dumps(n, sort_keys=True) for n in lcs_elements}

    raw: List[Tuple[str, Any]] = []
    ptr_a = ptr_b = 0
    while ptr_a < len(before) or ptr_b < len(after):
        a = before[ptr_a] if ptr_a < len(before) else None
        b = after[ptr_b] if ptr_b < len(after) else None
        a_str = json.dumps(a, sort_keys=True) if a is not None else None
        b_str = json.dumps(b, sort_keys=True) if b is not None else None

        if a is not None and a_str not in lcs_set:
            raw.append(("deletion", a))
            ptr_a += 1
        elif b is not None and b_str not in lcs_set:
            raw.append(("insertion", b))
            ptr_b += 1
        elif a is not None and b is not None:
            raw.append(("equal", a))
            ptr_a += 1
            ptr_b += 1
        elif ptr_a < len(before):
            raw.append(("deletion", before[ptr_a]))
            ptr_a += 1
        else:
            raw.append(("insertion", after[ptr_b]))
            ptr_b += 1
    return raw


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
