#!/usr/bin/env python3

from pandocfilters import toJSONFilter, RawBlock, stringify


def header_to_subsubparagraph(key, value, format, meta):
    if key == 'Header':
        level, attr, contents = value
        if level == 6:
            text = stringify(contents)
            return RawBlock('latex', f'\\subsubparagraph{{{text}}}')


if __name__ == "__main__":
    toJSONFilter(header_to_subsubparagraph)
