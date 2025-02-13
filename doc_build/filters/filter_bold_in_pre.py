#!/usr/bin/env python3

import re
from pandocfilters import toJSONFilter, RawBlock

import re


def escape_tex_symbols(input_string: str) -> str:
    """
    Escapes TeX control symbols in a given string.

    Args:
        input_string (str): The string to escape.

    Returns:
        str: The escaped string.
    """
    # List of TeX special characters and their escaped versions
    tex_specials = {
        # '\\': r'\\textbackslash ',
        "{": r"\{",
        "}": r"\}",
        "%": r"\%",
        "&": r"\&",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "^": r"\^{}",
        "~": r"\~{}",
    }

    # Use regex to replace each special character with its escaped version
    def replacer(match):
        char = match.group(0)
        return tex_specials[char]

    # pattern = re.compile(r'[\\{}%&$#_^~]')
    pattern = re.compile(r"[{}%&$#_^~]")
    escaped_string = pattern.sub(replacer, input_string)

    return escaped_string


def bold_in_pre(key, value, format, _):
    if key == "CodeBlock":
        [[ident, classes, keyvals], code] = value
        if classes == ["peg"]:
            if format == "html":
                replaced = re.sub(r"\*\*(.*?)\*\*", r"<em>\1</em>", code)
                return RawBlock("html", f"<pre><code>{replaced}</code></pre>")
            elif format == "latex":
                code = escape_tex_symbols(code)
                replaced = re.sub(r"\*\*(.*?)\*\*", r"£\\CodeEmphasis{\1}£", code)
                lstlisting = "{lstlisting}"
                return RawBlock(
                    "latex",
                    f"\\begin{lstlisting}[escapechar=£]\n{replaced}\\end{lstlisting}",
                )


# TODO
# escape latex symbols }
# do not convert /
# remove "" from titles in railroads
# gray background for PDF code examples and SVGs?
# different replacement for code examples and railroad diagrams
# Math symbols in Menlo? ⟹ ⊔

if __name__ == "__main__":
    toJSONFilter(bold_in_pre)
