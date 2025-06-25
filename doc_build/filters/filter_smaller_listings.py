#!/usr/bin/env python3

from pandocfilters import CodeBlock, RawBlock


def latex_smaller_code_listings(key, value, format, meta):
    if key == 'CodeBlock' and format == "latex":
        [[ident, classes, keyvals], code] = value

        return [
                RawBlock('latex', r'{\small'),
                CodeBlock([ident, classes, keyvals], code),
                RawBlock('latex', r'}'),
            ]


if __name__ == '__main__':
    from pandocfilters import toJSONFilter
    toJSONFilter(latex_smaller_code_listings)