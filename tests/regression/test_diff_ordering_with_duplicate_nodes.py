#!/usr/bin/env python
"""Regression tests for doc_build.ast_diff.

Each test here corresponds to a specific bug that was fixed and should be
expected to FAIL when run against the unfixed code.  Tests that document
normal behavior or structural shape (and pass against both fixed and unfixed
code) belong under tests/unit/ instead.
"""

import sys
import unittest
from pathlib import Path

# Make `doc_build` and the shared test helpers importable when run as a
# script (e.g. `python test_diff_ordering_with_duplicate_nodes.py`) as well
# as via `python -m unittest discover -s tests/regression`.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_TESTS_DIR = _REPO_ROOT / "tests"
for _p in (_REPO_ROOT, _TESTS_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from doc_build.ast_diff import diff_block_lists  # noqa: E402

from _ast_diff_helpers import block_kind, header  # noqa: E402


class TestDiffBlockListsLcsOrderingRegression(unittest.TestCase):
    """Regression tests for the bug where lcs_set membership lost positional
    info, causing two pointers that were each 'in the LCS' but at different
    positions to be treated as a matched pair.

    The most visible symptom in the spec build was a section like:

        #### Deprecated Fields
        These fields are reserved...
        - <bullet items, with one added>

    rendering as:

        #### Deprecated Fields
        [INSERTED bullet list]
        These fields are reserved...
        [REMOVED bullet list]

    instead of the expected substitution between the two lists.
    """

    def test_extra_duplicate_does_not_eat_following_lcs_block(self):
        # Minimal direct repro of the lcs_set-vs-lcs_list bug.  'X' appears
        # 3 times in 'before' and 2 times in 'after'.  The LCS uses two of
        # the X instances (the 1st and 3rd in 'before'), leaving the middle
        # one as a deletion.  But the buggy algorithm checked "X in lcs_set"
        # rather than "X is the next LCS element here", so the surplus X
        # was treated as preserved, forcing the next LCS element ('C' in
        # 'after') to be falsely reported as a deletion.
        x = header(2, "x", "X")
        a = header(2, "a", "A")
        b = header(2, "b", "B")
        c = header(2, "c", "C")

        before = [x, a, x, b, x, c]
        after = [x, a, x, c]

        merged = diff_block_lists(before, after)
        kinds = [block_kind(blk) for blk in merged]

        # Expected: [X, A, X, del(B), del(X), C] -- the surplus X is a
        # deletion, B is a deletion, and C is preserved.
        # Buggy output was [X, A, X, del(B), X, del(C)] (C falsely deleted).
        self.assertEqual(
            kinds,
            ["Header", "Header", "Header", "Div(deletion)", "Div(deletion)", "Header"],
            "the surplus duplicate X should be reported as a deletion, "
            "not allowed to consume the following preserved element",
        )
        # And specifically, C must remain preserved, not deleted.
        self.assertEqual(merged[-1], c)


if __name__ == "__main__":
    unittest.main()
