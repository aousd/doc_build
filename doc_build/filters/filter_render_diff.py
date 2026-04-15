#!/usr/bin/env python3

"""Pandoc filter that renders insertion/deletion/substitution Div blocks from
ast_diff.py into format-specific diff markup (underline/strikeout, HTML
ins/del tags, or LaTeX textcolor+strikeout).
"""

import json
from typing import Any, Dict, List, Optional, Type

from diff_match_patch import diff_match_patch
from pandocfilters import Strikeout, toJSONFilter

from doc_build.diff_colors import (
    DIFF_SECTION_DEL_PALE_RED,
    DIFF_SECTION_INS_PALE_GREEN,
    DIFF_WORD_DEL_RED,
    DIFF_WORD_INS_GREEN,
)

try:
    from pandocfilters import Underline
except ImportError:

    def Underline(inlines: List[Dict]) -> Dict:
        return {"t": "Underline", "c": inlines}


###############################################################################
# diff-match-patch operation constants
###############################################################################

DIFF_DELETE = -1
DIFF_INSERT = 1
DIFF_EQUAL = 0

###############################################################################
# HTML diff styling
###############################################################################

# Block-level backgrounds (pale) for insertion/deletion Divs
_HTML_BLOCK_DIFF_BG_INSERTION = f"#{DIFF_SECTION_INS_PALE_GREEN}"
_HTML_BLOCK_DIFF_BG_DELETION = f"#{DIFF_SECTION_DEL_PALE_RED}"

# Word-level backgrounds (stronger) for span-level changes inside substitutions
_HTML_WORD_DIFF_BG_INSERTION = f"#{DIFF_WORD_INS_GREEN}"
_HTML_WORD_DIFF_BG_DELETION = f"#{DIFF_WORD_DEL_RED}"

_HTML_BLOCK_DIFF_BG = {
    "insertion": _HTML_BLOCK_DIFF_BG_INSERTION,
    "deletion": _HTML_BLOCK_DIFF_BG_DELETION,
}
_HTML_WORD_DIFF_BG = {
    "insertion": _HTML_WORD_DIFF_BG_INSERTION,
    "deletion": _HTML_WORD_DIFF_BG_DELETION,
}
_HTML_TEXT_DECORATION = {
    "insertion": "underline",
    "deletion": "line-through",
}

###############################################################################
# GFM diff styling
###############################################################################

# Colored square emojis used as line-level diff markers in GFM markdown output
_GFM_EMOJI = {
    "insertion": "\U0001f7e9",  # green square
    "deletion": "\U0001f7e5",   # red square
}

# Pandoc passes "gfm" when the output format is gfm.  Only this format gets
# GFM-compatible rendering (emoji block prefixes, <u>/~~ word-level markup).
_GFM_FORMATS = frozenset({"gfm"})

# LaTeX color names used with \textcolor{color}{content} inside math expressions.
# GitHub's MathJax renderer honors these standard color names.
_GFM_MATH_COLOR = {
    "insertion": "green",
    "deletion": "red",
}

###############################################################################
# LaTeX diff styling
###############################################################################

# Named colors defined in default.latex via \definecolor, values from diff_colors.py
_LATEX_BLOCK_DIFF_BG = {
    "insertion": "DiffSectionInsPaleGreen",
    "deletion": "DiffSectionDelPaleRed",
}
_LATEX_WORD_DIFF_BG = {
    "insertion": "DiffWordInsGreen",
    "deletion": "DiffWordDelRed",
}
# ulem commands for text-only content: \uline for underline, \sout for strikethrough
_LATEX_TEXT_CMD = {
    "insertion": "\\uline",
    "deletion": "\\sout",
}
# math-safe commands: \underline and \textsout (defined in latex_diff_preamble.tex)
# Use when content contains inline math, which ulem cannot wrap.
_LATEX_MATH_TEXT_CMD = {
    "insertion": "\\underline",
    "deletion": "\\textsout",
}
# pandoc's default shadecolor for Shaded/verbatim environments
_LATEX_SHADECOLOR_DEFAULT = "lightgray"
# notebg default color name (defined via \colorlet{notebgdefault}{notebg} in after-header-includes.latex)
_LATEX_NOTEBG_DEFAULT = "notebgdefault"


###############################################################################
# AST helpers
###############################################################################


def Str(text: str) -> Dict:
    return {"t": "Str", "c": text}


def Space() -> Dict:
    return {"t": "Space"}


def Header(level: int, attr: List, inlines: List[Dict]) -> Dict:
    return {"t": "Header", "c": [level, attr, inlines]}


def _gfm_prefix_inlines(inlines: List[Dict], diff_class: str) -> List[Dict]:
    """Prepend a colored emoji marker and a space to a list of inline elements."""
    return [Str(_GFM_EMOJI[diff_class]), Space()] + inlines


def _gfm_color_block_math(block: Dict, diff_class: str) -> Dict:
    """Apply \\textcolor math styling to all math content in a block for GFM.

    For Para/Plain/Header, colors all Math nodes in the inline list.
    For math CodeBlocks, wraps the content string with \\textcolor{}{}.
    Other block types are returned unchanged.
    """
    t = block.get("t")
    c = block.get("c")
    if t in ("Para", "Plain"):
        return {"t": t, "c": _gfm_color_math_inlines(c, diff_class)}
    if t == "Header":
        level, attr, inlines = c
        return Header(level, attr, _gfm_color_math_inlines(inlines, diff_class))
    if t == "CodeBlock":
        attr, code_str = c
        if "math" in attr[1]:
            color = _GFM_MATH_COLOR[diff_class]
            return {"t": "CodeBlock", "c": [attr, f"\\textcolor{{{color}}}{{{code_str}}}"]}
    return block


def _gfm_prefix_blocks(block: Dict, diff_class: str) -> List[Dict]:
    """Add a GFM emoji prefix to a block element, returning a list of blocks.

    For Para/Plain/Header, the emoji is prepended inline to the block's inline
    list and a single-item list is returned.  For other block types (CodeBlock,
    etc.) that cannot carry an inline prefix, a separate Para containing only
    the emoji is prepended, returning a two-item list.
    """
    t = block["t"]
    c = block["c"]
    if t in ("Para", "Plain"):
        return [{"t": t, "c": _gfm_prefix_inlines(c, diff_class)}]
    if t == "Header":
        level, attr, inlines = c
        return [Header(level, attr, _gfm_prefix_inlines(inlines, diff_class))]
    # Non-inline block: emit a standalone emoji Para, then the block itself.
    emoji_para = {"t": "Para", "c": [Str(_GFM_EMOJI[diff_class])]}
    return [emoji_para, block]


def make_diff_span(diff_class: str, inlines: List[Dict]) -> Dict:
    """Wrap inlines in a Span tagged with the given diff class."""
    return {"t": "Span", "c": [["", [diff_class], []], inlines]}


def _make_styled_div(bg_color: str, blocks: List[Dict]) -> Dict:
    """Wrap blocks in a Pandoc Div with an inline background-color style."""
    return {
        "t": "Div",
        "c": [["", [], [("style", f"background-color: {bg_color};")]], blocks],
    }


def _has_math(inlines: List[Dict]) -> bool:
    """Return True if any node in inlines is a Math element (inline or display).

    Used to decide whether to skip ulem text-decoration commands (\\uline,
    \\sout), which cannot safely wrap any math content.
    """
    for node in inlines:
        if node.get("t") == "Math":
            return True
    return False


def _has_display_math(inlines: List[Dict]) -> bool:
    """Return True if any node in inlines is a DisplayMath element.

    Display math (\\[...\\]) cannot be nested inside LaTeX box commands such as
    \\colorbox or \\parbox.  Use this guard before adding any box wrapper.
    """
    for node in inlines:
        if node.get("t") == "Math":
            math_type = node["c"][0].get("t")
            if math_type == "DisplayMath":
                return True
    return False


def _has_link(inlines: List[Dict]) -> bool:
    """Return True if any node in inlines is a Link element.

    Used to skip ulem text-decoration commands (\\uline, \\sout) when content
    contains hyperlinks.  Hyperref's link commands manipulate TeX group state
    internally (via \\aftergroup hooks used for color/link scope cleanup).
    ulem's token scanner opens its own groups, so hyperref's \\aftergroup fires
    on the wrong group, causing 'Extra }, or forgotten \\endgroup' errors.
    """
    return any(node.get("t") == "Link" for node in inlines)


###############################################################################
# style_inlines - recursive wrapper (used for whole-block "other formats")
###############################################################################


def style_inlines(inlines: List[Dict], Wrapper: Type) -> List[Dict]:
    """Recursively traverse inlines and wrap text content with Wrapper."""
    new_list = []
    for inline in inlines:
        t = inline.get("t")
        c = inline.get("c")
        if t in ("Str", "Space", "SoftBreak", "LineBreak"):
            if t == "Str" and not c:
                continue
            new_list.append(Wrapper([inline]))
        elif t in ("Emph", "Strong"):
            new_list.append({"t": t, "c": style_inlines(c, Wrapper)})
        elif t == "Quoted":
            quote_type, quoted_inlines = c
            new_list.append(
                {"t": t, "c": [quote_type, style_inlines(quoted_inlines, Wrapper)]}
            )
        elif t == "Link":
            attr, link_text, target = c
            new_list.append(
                {"t": "Link", "c": [attr, style_inlines(link_text, Wrapper), target]}
            )
        elif t == "Cite":
            citations, citation_text = c
            new_list.append(
                {"t": "Cite", "c": [citations, style_inlines(citation_text, Wrapper)]}
            )
        else:
            new_list.append(inline)
    return new_list


###############################################################################
# Format-specific rendering
###############################################################################

def _raw_inline(fmt: str, text: str) -> Dict:
    return {"t": "RawInline", "c": [fmt, text]}


def _latex_text_cmd_wrap(diff_class: str, content: List[Dict], math: bool = False) -> List[Dict]:
    """Wrap content with underline or strikethrough.

    When math=False (default): uses \\uline/\\sout from ulem (supports line
    breaking, but cannot wrap Math nodes).
    When math=True: uses \\underline/\\textsout (math-safe, defined in
    latex_diff_preamble.tex, but does not support line breaking).
    """
    cmd = _LATEX_MATH_TEXT_CMD[diff_class] if math else _LATEX_TEXT_CMD[diff_class]
    return (
        [_raw_inline("latex", f"\\protect{cmd}{{")]
        + content
        + [_raw_inline("latex", "}")]
    )


def _latex_span_wrap(diff_class: str, content: List[Dict]) -> List[Dict]:
    """Wrap word-level span content in a colored box + text decoration.

    Uses \\colorbox{DiffSpanXxx}{\\strut \\uline/\\sout{content}} for text
    content, and \\colorbox{DiffSpanXxx}{\\strut \\underline/\\textsout{content}}
    when content contains inline math (ulem cannot wrap math).
    When content contains links or display math, text decoration is skipped
    entirely and only the colored box background is emitted: hyperref's link
    commands use \\aftergroup hooks that interfere with ulem's token scanner,
    and display math cannot be nested inside \\colorbox at all.
    """
    if _has_display_math(content):
        # Display math cannot be inside \colorbox at all.  Background is
        # applied at the block level via tcolorbox; no span-level styling.
        return list(content)
    bg = _LATEX_WORD_DIFF_BG[diff_class]
    if _has_link(content):
        # Links use \hyperref/\href which manipulate TeX group state via
        # \aftergroup hooks; ulem's token scanner opens its own groups and the
        # interaction causes "Extra }" errors.  Colorbox background is enough.
        return (
            [_raw_inline("latex", f"\\colorbox{{{bg}}}{{\\strut ")]
            + content
            + [_raw_inline("latex", "}")]
        )
    inner = _latex_text_cmd_wrap(diff_class, content, math=_has_math(content))
    return (
        [_raw_inline("latex", f"\\colorbox{{{bg}}}{{\\strut ")]
        + inner
        + [_raw_inline("latex", "}")]
    )


def _latex_block_bg_wrap(diff_class: str, content: List[Dict]) -> List[Dict]:
    """Wrap block inline content in a pale-background \\colorbox/\\parbox.

    Prepends \\noindent\\colorbox{DiffSectionInsPaleGreen}{\\parbox{...}{ and appends }}.
    The text decoration (\\uline/\\sout) is applied to the content by the
    caller before passing it here - this function only adds the outer box.
    """
    bg = _LATEX_BLOCK_DIFF_BG[diff_class]
    open_cmd = (
        f"\\noindent\\colorbox{{{bg}}}"
        "{\\parbox{\\dimexpr\\linewidth-2\\fboxsep}{"
    )
    return (
        [_raw_inline("latex", open_cmd)]
        + content
        + [_raw_inline("latex", "}}")]
    )


def _latex_bg_blocks(block: Dict, diff_class: str) -> List[Dict]:
    """Apply a diff background to a block for LaTeX output.

    Wraps the block in a tcolorbox and sets shadecolor and notebg to match.
    All three are applied unconditionally so that background-bearing children
    at any nesting depth inherit the diff color:

    - shadecolor: read by CodeBlock's Shaded/snugshade environment.
    - notebg: read by BlockQuote's tcolorbox (colback=notebg).  The outer
      tcolorbox cannot override an inner tcolorbox's colback, so setting notebg
      is the only way to propagate the diff color into a BlockQuote.

    Setting all three handles nested combinations correctly: a CodeBlock inside
    a BlockQuote, a BulletList inside a BlockQuote, a CodeBlock inside a
    BulletList inside a BlockQuote, etc.  The outer tcolorbox adds a thin layer
    of extra padding around BlockQuote's own box (boxsep=0pt, left=2pt,
    right=2pt, top=1pt, bottom=1pt), which is an acceptable trade-off.
    """
    bg = _LATEX_BLOCK_DIFF_BG[diff_class]
    open_cmd = (
        f"\\colorlet{{shadecolor}}{{{bg}}}"
        f"\\colorlet{{notebg}}{{{bg}}}"
        f"\\begin{{tcolorbox}}[colback={bg},colframe={bg},"
        "boxrule=0pt,boxsep=0pt,left=2pt,right=2pt,top=1pt,bottom=1pt,"
        "enhanced,breakable]"
    )
    close_cmd = (
        f"\\end{{tcolorbox}}"
        f"\\colorlet{{shadecolor}}{{{_LATEX_SHADECOLOR_DEFAULT}}}"
        f"\\colorlet{{notebg}}{{{_LATEX_NOTEBG_DEFAULT}}}"
    )
    return [
        {"t": "RawBlock", "c": ["latex", open_cmd]},
        block,
        {"t": "RawBlock", "c": ["latex", close_cmd]},
    ]


def render_span_inlines(inlines: List[Dict], format: str) -> List[Dict]:
    """Convert Span(["insertion"/"deletion"], [...]) elements to format-specific markup.

    Non-Span elements pass through unchanged.
    """
    result = []
    for node in inlines:
        if node.get("t") != "Span":
            result.append(node)
            continue
        span_attrs, span_content = node["c"]
        span_classes = span_attrs[1]
        if "insertion" in span_classes:
            diff_class = "insertion"
        elif "deletion" in span_classes:
            diff_class = "deletion"
        else:
            result.append(node)
            continue

        result.extend(_render_span(span_content, format, diff_class))

    return result


def _gfm_color_math_node(node: Dict, diff_class: str) -> Dict:
    """Rewrite a Math node's LaTeX string with \\textcolor{color}{...}."""
    math_type, latex_str = node["c"]
    color = _GFM_MATH_COLOR[diff_class]
    return {"t": "Math", "c": [math_type, f"\\textcolor{{{color}}}{{{latex_str}}}"]}


def _gfm_color_math_inlines(inlines: List[Dict], diff_class: str) -> List[Dict]:
    """Apply \\textcolor color styling to all Math nodes in an inline list."""
    return [
        _gfm_color_math_node(node, diff_class) if node.get("t") == "Math" else node
        for node in inlines
    ]


def _gfm_wrap_math_content(content: List[Dict], diff_class: str) -> List[Dict]:
    """Handle GFM span content that contains math nodes.

    Processes content node-by-node:
    - Math nodes (inline or display): rewritten with \\textcolor{green/red}{...}
      so GitHub's MathJax renders the color inside the math expression.
    - All other nodes: collected into runs and wrapped with <u>...</u> or
      ~~...~~ as usual.
    """
    is_insertion = diff_class == "insertion"
    open_marker = _raw_inline("html", "<u>") if is_insertion else _raw_inline("markdown", "~~")
    close_marker = _raw_inline("html", "</u>") if is_insertion else _raw_inline("markdown", "~~")

    result: List[Dict] = []
    text_run: List[Dict] = []

    def flush_text_run():
        if text_run:
            result.extend([open_marker] + text_run + [close_marker])
            text_run.clear()

    for node in content:
        if node.get("t") == "Math":
            flush_text_run()
            result.append(_gfm_color_math_node(node, diff_class))
        else:
            text_run.append(node)

    flush_text_run()
    return result


def _render_span(content: List[Dict], format: str, diff_class: str) -> List[Dict]:
    """Emit format-specific inline markup wrapping content for one diff class.

    For HTML, word-level spans (inside substitutions) get the stronger shade
    background plus underline/strikethrough.
    For GFM markdown, <u>...</u> marks insertions and ~~...~~ marks deletions
    for text content.  When content contains math, text runs are wrapped as
    above and Math nodes are rewritten with \\textcolor{green/red}{} so
    GitHub's MathJax renders color inside the math expression.
    For LaTeX, word-level spans get a colored box plus ulem text decoration
    (or textcolor-only fallback when content contains math).
    """
    if format == "latex":
        return _latex_span_wrap(diff_class, content)
    elif format == "html":
        bg = _HTML_WORD_DIFF_BG[diff_class]
        decoration = _HTML_TEXT_DECORATION[diff_class]
        open_tag = (
            f'<span style="background-color: {bg}; text-decoration: {decoration};">'
        )
        return (
            [_raw_inline("html", open_tag)]
            + content
            + [_raw_inline("html", "</span>")]
        )
    elif format in _GFM_FORMATS:
        if _has_math(content):
            return _gfm_wrap_math_content(content, diff_class)
        if diff_class == "insertion":
            return (
                [_raw_inline("html", "<u>")]
                + content
                + [_raw_inline("html", "</u>")]
            )
        else:
            return (
                [_raw_inline("markdown", "~~")]
                + content
                + [_raw_inline("markdown", "~~")]
            )
    else:
        Wrapper = Underline if diff_class == "insertion" else Strikeout
        return [Wrapper(content)]


def render_inlines_raw(inlines: List[Dict], format: str, diff_class: str) -> List[Dict]:
    """Wrap an entire inline list in diff markup (for whole-block changes).

    For HTML, whole-block changes get text decoration only (the pale block
    background is applied at the Div level by handle_whole_block).
    For GFM markdown, the block-level emoji prefix (added by handle_whole_block)
    is sufficient; no additional inline markup is needed on the content.
    For LaTeX, no text decoration is added; the pale background from
    _latex_block_bg_wrap / tcolorbox is sufficient. ulem commands like
    \\uline and \\sout scan tokens internally and break when the content
    contains \\hyperref or other commands that change TeX group state.
    """
    if format == "latex":
        # Background applied at block level; no inline text decoration.
        return list(inlines)
    elif format == "html":
        decoration = _HTML_TEXT_DECORATION[diff_class]
        open_tag = f'<span style="text-decoration: {decoration};">'
        return (
            [_raw_inline("html", open_tag)]
            + inlines
            + [_raw_inline("html", "</span>")]
        )
    elif format in _GFM_FORMATS:
        # Emoji prefix is added at block level; content passes through unchanged.
        return list(inlines)
    else:
        Wrapper = Underline if diff_class == "insertion" else Strikeout
        return style_inlines(inlines, Wrapper)


###############################################################################
# Inline diff (element-granularity)
###############################################################################


def inline_diff(
    old_inlines: List[Dict], new_inlines: List[Dict]
) -> List[tuple[int, List[Dict]]]:
    """Diff two lists of pandoc inline elements at element granularity.

    Returns a list of (op, [node, ...]) pairs where op is DIFF_DELETE,
    DIFF_INSERT, or DIFF_EQUAL.
    """
    node_to_char: Dict[str, str] = {}
    char_to_node: Dict[str, Dict] = {}

    def encode(inlines: List[Dict]) -> str:
        chars = []
        for node in inlines:
            # Normalize SoftBreak to Space: both render as whitespace, so treating
            # them as identical avoids false positives when pandoc line-wraps a
            # paragraph differently across versions (e.g. because the math changed
            # length and the wrap point shifted).
            normalized = {"t": "Space"} if node.get("t") == "SoftBreak" else node
            key = json.dumps(normalized, sort_keys=True)
            if key not in node_to_char:
                # U+F0000 is the start of Supplementary Private Use Area-A,
                # which provides 65,534 private-use code points - far more
                # than any realistic paragraph needs.
                c = chr(0xF0000 + len(node_to_char))
                node_to_char[key] = c
                char_to_node[c] = normalized
            chars.append(node_to_char[key])
        return "".join(chars)

    enc_old = encode(old_inlines)
    enc_new = encode(new_inlines)
    dmp = diff_match_patch()
    diffs = dmp.diff_main(enc_old, enc_new)
    dmp.diff_cleanupSemantic(diffs)
    return [(op, [char_to_node[c] for c in chars]) for op, chars in diffs]


###############################################################################
# Block rendering helpers
###############################################################################

# Block types that carry inline content
_INLINE_BLOCK_TYPES = ("Para", "Plain", "Header")


def _is_inline_block(block: Dict) -> bool:
    return block.get("t") in _INLINE_BLOCK_TYPES


def _get_block_inlines(block: Dict) -> List[Dict]:
    """Return the inline list from a Para, Plain, or Header block."""
    t = block.get("t")
    c = block.get("c")
    if t in ("Para", "Plain"):
        return c
    else:  # Header
        _level, _attr, inlines = c
        return inlines


def _build_inline_block(block: Dict, inlines: List[Dict]) -> Dict:
    """Reconstruct a Para/Plain/Header with new inlines."""
    t = block.get("t")
    c = block.get("c")
    if t in ("Para", "Plain"):
        return {"t": t, "c": inlines}
    else:  # Header
        level, attr, _old_inlines = c
        return Header(level, attr, inlines)


def render_whole_block(block: Dict, format: str, diff_class: str) -> Dict:
    """Apply whole-block diff markup to all inlines in a block.

    For LaTeX, Para and Plain blocks receive a pale-background colorbox wrapper.
    Header blocks receive text decoration only; the caller is responsible for
    adding a tcolorbox background wrapper at the block level.
    """
    t = block.get("t")
    c = block.get("c")
    if t in ("Para", "Plain"):
        styled = render_inlines_raw(c, format, diff_class)
        if format == "latex" and not _has_display_math(c):
            styled = _latex_block_bg_wrap(diff_class, styled)
        return {"t": t, "c": styled}
    elif t == "Header":
        level, attr, inlines = c
        styled = render_inlines_raw(inlines, format, diff_class)
        return Header(level, attr, styled)
    else:
        return block


###############################################################################
# handle_whole_block and handle_substitution
###############################################################################


def handle_whole_block(
    content: List[Dict], format: str, diff_class: str
) -> List[Dict]:
    """Handle a pure insertion or deletion Div.

    For HTML, each block is wrapped in a pale-background styled Div.
    For GFM markdown, each block is prefixed with a colored emoji square
    (green for insertion, red for deletion); no background Div is emitted
    because GFM does not render pandoc-style Div syntax.
    For LaTeX, CodeBlock elements are wrapped with shadecolor colorlet commands
    to give them a pale diff background via pandoc's Shaded environment.
    Para/Plain blocks containing display math are wrapped with a tcolorbox
    environment, which (unlike \\colorbox/\\parbox) supports display math.
    """
    if format == "html":
        rendered = [render_whole_block(block, format, diff_class) for block in content]
        bg = _HTML_BLOCK_DIFF_BG[diff_class]
        return [_make_styled_div(bg, rendered)]
    if format in _GFM_FORMATS:
        result = []
        for block in content:
            result.extend(_gfm_prefix_blocks(_gfm_color_block_math(block, diff_class), diff_class))
        return result
    result = []
    for block in content:
        if format == "latex":
            result.extend(_latex_bg_blocks(block, diff_class))
        else:
            result.append(render_whole_block(block, format, diff_class))
    return result


def handle_substitution(content: List[Dict], format: str) -> List[Dict]:
    """Handle a substitution Div containing [deletion_div, insertion_div]."""

    deletion_div, insertion_div = content
    old_block = deletion_div["c"][1][0]
    new_block = insertion_div["c"][1][0]

    if (
        _is_inline_block(old_block)
        and _is_inline_block(new_block)
        and old_block.get("t") == new_block.get("t")
    ):
        old_inlines = _get_block_inlines(old_block)
        new_inlines = _get_block_inlines(new_block)
        diffs = inline_diff(old_inlines, new_inlines)

        # Build old (deletion) output block: EQUAL as-is, DELETE wrapped, INSERT omitted
        old_out: List[Dict] = []
        for op, nodes in diffs:
            if op == DIFF_EQUAL:
                old_out.extend(nodes)
            elif op == DIFF_DELETE:
                old_out.append(make_diff_span("deletion", nodes))
            # INSERT: omit from old block

        # Build new (insertion) output block: EQUAL as-is, INSERT wrapped, DELETE omitted
        new_out: List[Dict] = []
        for op, nodes in diffs:
            if op == DIFF_EQUAL:
                new_out.extend(nodes)
            elif op == DIFF_INSERT:
                new_out.append(make_diff_span("insertion", nodes))
            # DELETE: omit from new block

        old_out = render_span_inlines(old_out, format)
        new_out = render_span_inlines(new_out, format)

        old_result = _build_inline_block(old_block, old_out)
        new_result = _build_inline_block(new_block, new_out)
        gfm_color_math = False
    else:
        # Non-inline blocks: fall back to whole-block styling
        old_result = render_whole_block(old_block, format, "deletion")
        new_result = render_whole_block(new_block, format, "insertion")
        gfm_color_math = True

    if format == "html":
        return [
            _make_styled_div(_HTML_BLOCK_DIFF_BG["deletion"], [old_result]),
            _make_styled_div(_HTML_BLOCK_DIFF_BG["insertion"], [new_result]),
        ]
    if format in _GFM_FORMATS:
        if gfm_color_math:
            old_result = _gfm_color_block_math(old_result, "deletion")
            new_result = _gfm_color_block_math(new_result, "insertion")
        return (
            _gfm_prefix_blocks(old_result, "deletion")
            + _gfm_prefix_blocks(new_result, "insertion")
        )
    if format == "latex":
        return _latex_bg_blocks(old_result, "deletion") + _latex_bg_blocks(new_result, "insertion")
    return [old_result, new_result]


###############################################################################
# Top-level filter function
###############################################################################

_DIFF_TYPE_LABEL = {
    "insertion": "Add",
    "deletion": "Remove",
    "substitution": "Substitution",
}


def _get_meta_str(meta: Dict, key: str) -> Optional[str]:
    """Extract a plain string from pandoc metadata (MetaString or MetaInlines)."""
    entry = meta.get(key)
    if entry is None:
        return None
    t = entry.get("t")
    if t == "MetaString":
        return entry["c"]
    if t == "MetaInlines":
        parts = []
        for node in entry["c"]:
            nt = node.get("t")
            if nt == "Str":
                parts.append(node["c"])
            elif nt == "Space":
                parts.append(" ")
        return "".join(parts)
    return None


def _make_diff_label_para(from_pretty: str, to_pretty: str, diff_type: str) -> Dict:
    label = f"Diff - from {from_pretty} to {to_pretty} - {_DIFF_TYPE_LABEL[diff_type]}"
    return {"t": "Para", "c": [{"t": "Str", "c": label}]}


def render_diffs(key: str, value: Any, format: str, meta: Dict) -> Optional[List[Dict]]:
    if key != "Div":
        return None
    attrs, content = value
    classes = attrs[1]

    from_pretty = _get_meta_str(meta, "diff-from-pretty")
    to_pretty = _get_meta_str(meta, "diff-to-pretty")
    has_label = from_pretty is not None and to_pretty is not None

    if "substitution" in classes:
        result = handle_substitution(content, format)
        if has_label:
            result = [_make_diff_label_para(from_pretty, to_pretty, "substitution")] + result
        return result
    elif "insertion" in classes:
        result = handle_whole_block(content, format, "insertion")
        if has_label:
            result = [_make_diff_label_para(from_pretty, to_pretty, "insertion")] + result
        return result
    elif "deletion" in classes:
        result = handle_whole_block(content, format, "deletion")
        if has_label:
            result = [_make_diff_label_para(from_pretty, to_pretty, "deletion")] + result
        return result
    return None


if __name__ == "__main__":
    toJSONFilter(render_diffs)
