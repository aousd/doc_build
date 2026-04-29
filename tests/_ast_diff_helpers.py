"""Shared Pandoc AST helpers for ast_diff tests.

Used by tests/feature/test_ast_diff.py and
tests/regression/test_diff_ordering_with_duplicate_nodes.py.  The functions
construct just enough of the real Pandoc AST shape for the ast_diff module
to walk over without going through pandoc itself.
"""


def _str(s):
    return {"t": "Str", "c": s}


def _space():
    return {"t": "Space"}


def _inlines(text):
    """Pandoc inline list from a plain string (single-space-separated words)."""
    out = []
    for i, word in enumerate(text.split()):
        if i:
            out.append(_space())
        out.append(_str(word))
    return out


def header(level, ident, text):
    return {"t": "Header", "c": [level, [ident, [], []], _inlines(text)]}


def para(text):
    return {"t": "Para", "c": _inlines(text)}


def plain(text):
    return {"t": "Plain", "c": _inlines(text)}


def bullet_list(*item_texts):
    return {"t": "BulletList", "c": [[plain(t)] for t in item_texts]}


def diff_classes(node):
    if node.get("t") == "Div":
        return tuple(node["c"][0][1])
    return ()


def block_kind(node):
    """Short identifier for asserting on diff structure."""
    cls = diff_classes(node)
    if cls:
        return f"Div({'+'.join(cls)})"
    return node.get("t", "?")
