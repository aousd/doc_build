#!/usr/bin/env python3
"""Pandoc filter: convert heading text to ISO sentence case.

ISO/IEC Directives, Part 2, 11.4: clause titles shall use sentence case.
This filter lowercases non-first words in headings unless they are proper
nouns (detected by heuristic or listed in a YAML allowlist).

The YAML path is passed via the ``HEADING_PROPER_NOUNS`` pandoc metadata
variable.  If absent, only heuristic detection is used.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from pandocfilters import Header, stringify, toJSONFilter

from heading_case import (
    heading_needs_conversion,
    load_proper_nouns,
    sentence_case_inlines,
)
from shared_filter_utils import get_metadata_str


class HeadingCaseFilter:
    """Stateful filter that converts headings to sentence case."""

    def __init__(self):
        self._extra_nouns = None

    def _initialize(self, metadata):
        if self._extra_nouns is not None:
            return
        try:
            yaml_path = get_metadata_str(metadata, 'HEADING_PROPER_NOUNS')
            from pathlib import Path
            self._extra_nouns = load_proper_nouns(Path(yaml_path))
        except KeyError:
            self._extra_nouns = set()

    def __call__(self, key, value, fmt, metadata):
        self._initialize(metadata)
        if key != 'Header':
            return None

        level, attr, inlines = value
        if not heading_needs_conversion(inlines, self._extra_nouns):
            return None

        new_inlines = sentence_case_inlines(inlines, self._extra_nouns)
        return Header(level, attr, new_inlines)


if __name__ == '__main__':
    toJSONFilter(HeadingCaseFilter())
