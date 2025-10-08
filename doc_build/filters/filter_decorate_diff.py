#!/usr/bin/env python3

from pandocfilters import toJSONFilter, Strikeout
from typing import Dict, Any, List, Optional, Type

try:
    from pandocfilters import Underline
except ImportError:
    def Underline(inlines: List[Dict]) -> Dict:
        return {'t': 'Underline', 'c': inlines}

def Str(text: str) -> Dict:
    return {'t': 'Str', 'c': text}

def Header(level: int, attr: List, inlines: List[Dict]) -> Dict:
    return {'t': 'Header', 'c': [level, attr, inlines]}

ULEM_PACKAGE_INCLUDED = False


def style_inlines(inlines: List[Dict], Wrapper: Type) -> List[Dict]:
    """
    Recursively traverses a list of inline elements, wrapping simple text
    content in the given Wrapper (e.g., Underline, Strikeout).
    """
    new_list = []
    for inline in inlines:
        t = inline.get('t')
        c = inline.get('c')

        if t in ['Str', 'Space', 'SoftBreak', 'LineBreak']:
            if t == 'Str' and not c:  # Skip empty strings
                continue
            new_list.append(Wrapper([inline]))
        elif t in ['Emph', 'Strong', 'Quoted']:
            styled_content = style_inlines(c, Wrapper)
            new_list.append({'t': t, 'c': styled_content})
        elif t == 'Link':
            attr, link_text, target = c
            styled_link_text = style_inlines(link_text, Wrapper)
            new_list.append({'t': 'Link', 'c': [attr, styled_link_text, target]})
        elif t == 'Cite':
            citations, citation_text = c
            styled_citation_text = style_inlines(citation_text, Wrapper)
            new_list.append({'t': 'Cite', 'c': [citations, styled_citation_text]})
        else:
            # For non-textual elements (Math, Image, RawInline), pass them through unchanged.
            new_list.append(inline)
    return new_list

def render_diffs(key: str, value: Any, format: str, meta: Dict) -> Optional[List[Dict]]:
    global ULEM_PACKAGE_INCLUDED

    if key != 'Div':
        return None

    div_attrs, div_content = value
    
    # Extract diff status from attributes: ["", [], [["diff", "added"]]]
    status = next((val for key, val in div_attrs[2] if key == 'diff'), None)

    if status not in ['added', 'removed']:
        return None

    Wrapper = Underline if status == 'added' else Strikeout
    
    # Handle LaTeX dependencies for Strikeout
    if status == 'removed' and format == 'latex' and not ULEM_PACKAGE_INCLUDED:
        usepackage = {"t": "MetaInlines", "c": [{"t": "RawInline", "c": ["latex", "\\usepackage{ulem}"]}]}
        if 'header-includes' not in meta:
            meta['header-includes'] = {"t": "MetaList", "c": []}
        meta['header-includes']['c'].append(usepackage)
        ULEM_PACKAGE_INCLUDED = True

    transformed_blocks = []
    for block in div_content:
        t = block.get('t')
        c = block.get('c')

        if t in ['Para', 'Plain']:
            transformed_blocks.append({'t': t, 'c': style_inlines(c, Wrapper)})
        elif t == 'Header':
            level, attr, inlines = c
            styled_content = style_inlines(inlines, Wrapper)
            # Fix for fragile LaTeX commands in headers
            if format == 'latex':
                protect_cmd = {'t': 'RawInline', 'c': ['latex', '\\protect']}
                styled_content.insert(0, protect_cmd)
            transformed_blocks.append(Header(level, attr, styled_content))
        # TODO Add handlers for other block types: lists or blockquotes if needed
        # TODO For now, pass them through.
        else:
            transformed_blocks.append(block)

    return transformed_blocks


if __name__ == "__main__":
    toJSONFilter(render_diffs)