#!/usr/bin/env python3

from pandocfilters import toJSONFilter, Header, RawBlock

def add_clearpage_before_header(key, value, format, meta):
    if key == 'Header':
        level, attr, contents = value
        if level == 1:
            return [
                RawBlock('latex', r'\clearpage'),
                Header(level, attr, contents)
            ]

if __name__ == "__main__":
    toJSONFilter(add_clearpage_before_header)
