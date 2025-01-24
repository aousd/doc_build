#!/usr/bin/env python3
from pandocfilters import toJSONFilter, Para, Math


def convert_math_blocks(key, value, _format, _metadata):
    """Pandoc seems to not reliably deal with math code blocks in github flavoured markdown, so we replace them
    Modified from the sample at https://github.com/jgm/pandocfilters/blob/master/examples/gitlab_markdown.py"""

    if key == "CodeBlock":
        [[_identification, classes, _keyvals], code] = value
        if len(classes) > 0 and classes[0] == "math":
            fmt = {'t': 'DisplayMath',
                   'c': []}
            return Para([Math(fmt, code)])

    elif key == "Math":
        [fmt, code] = value
        if isinstance(fmt, dict) and fmt['t'] == "InlineMath":
            return Math(fmt, code.strip('`'))


if __name__ == "__main__":
    toJSONFilter(convert_math_blocks)
