#!/usr/bin/env python
"""Feature tests for doc_build.ast_diff.

These tests construct minimal Pandoc-style block AST fragments and assert on
the structural shape of the diff output, without going through pandoc.  They
exercise diff_block_lists end-to-end (no mocking of LCS / pairing helpers).
Tests that specifically reproduce a previously fixed bug live under
tests/regression/.
"""

import sys
import unittest
from pathlib import Path

# Make `doc_build` importable when run as a script (e.g. `python test_ast_diff.py`)
# as well as via `python -m unittest discover -s tests/feature`.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_TESTS_DIR = _REPO_ROOT / "tests"
for _p in (_REPO_ROOT, _TESTS_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from doc_build.ast_diff import diff_block_lists  # noqa: E402

from _ast_diff_helpers import (  # noqa: E402
    block_kind,
    bullet_list,
    diff_classes,
    header,
    para,
)


class TestDiffBlockListsBasics(unittest.TestCase):
    """Sanity checks for the simple, no-duplicates path."""

    def test_no_changes_returns_inputs_unwrapped(self):
        before = [header(2, "h", "Title"), para("body text")]
        after = [header(2, "h", "Title"), para("body text")]
        merged = diff_block_lists(before, after)
        self.assertEqual([block_kind(b) for b in merged], ["Header", "Para"])

    def test_pure_insertion(self):
        before = [header(2, "h", "Title")]
        after = [header(2, "h", "Title"), para("new body")]
        merged = diff_block_lists(before, after)
        self.assertEqual(
            [block_kind(b) for b in merged], ["Header", "Div(insertion)"]
        )

    def test_pure_deletion(self):
        before = [header(2, "h", "Title"), para("old body")]
        after = [header(2, "h", "Title")]
        merged = diff_block_lists(before, after)
        self.assertEqual(
            [block_kind(b) for b in merged], ["Header", "Div(deletion)"]
        )

    def test_changed_para_becomes_substitution(self):
        before = [header(2, "h", "Title"), para("old body")]
        after = [header(2, "h", "Title"), para("new body")]
        merged = diff_block_lists(before, after)
        self.assertEqual(
            [block_kind(b) for b in merged], ["Header", "Div(substitution)"]
        )

    def test_changed_bullet_list_returns_diffed_list(self):
        before = [bullet_list("a", "b", "c")]
        after = [bullet_list("a", "z", "c")]
        merged = diff_block_lists(before, after)
        self.assertEqual([block_kind(b) for b in merged], ["BulletList"])
        # The middle item should be a per-item substitution Div.
        items = merged[0]["c"]
        self.assertEqual(diff_classes(items[1][0]), ("substitution",))


class TestDiffBlockListsStructuralShape(unittest.TestCase):
    """Structural checks involving duplicates and drift.

    These cases exercise the same code paths that the LCS-ordering regression
    test in tests/regression covers, but they happen to produce the same
    output under both the buggy and fixed implementations, so they aren't
    sufficient on their own to catch the bug.  They serve as documentation
    of the expected shape and as guard rails against unrelated regressions.
    """

    def test_duplicated_paragraphs_with_local_change_yields_substitution(self):
        # Both 'Deprecated Fields' subsections share the SAME boilerplate
        # paragraph ("These fields are reserved...").  The pandoc-style
        # auto-numbered ids make the headings distinct.  Only the *first*
        # subsection's bullet list differs between before and after.
        boiler = para("These fields are reserved though their usage is deprecated")

        before = [
            header(4, "deprecated-fields", "Deprecated Fields"),
            boiler,
            bullet_list("relocates", "permission"),
            header(3, "property-spec", "Property Spec"),
            header(4, "deprecated-fields-1", "Deprecated Fields"),
            boiler,
            bullet_list("foo", "bar"),
        ]
        after = [
            header(4, "deprecated-fields", "Deprecated Fields"),
            boiler,
            # added a leading item:
            bullet_list("displayGroupOrder", "relocates", "permission"),
            header(3, "property-spec", "Property Spec"),
            header(4, "deprecated-fields-1", "Deprecated Fields"),
            boiler,
            bullet_list("foo", "bar"),
        ]

        merged = diff_block_lists(before, after)
        kinds = [block_kind(b) for b in merged]

        # Expected: heading, paragraph, (single diffed BulletList from
        # diff_list_nodes), property-spec heading, second heading, paragraph,
        # second (unchanged) BulletList.
        self.assertEqual(
            kinds,
            [
                "Header",
                "Para",
                "BulletList",
                "Header",
                "Header",
                "Para",
                "BulletList",
            ],
            "boiler paragraph must remain between the heading and the diffed "
            "bullet list, not be displaced by a separate insertion+deletion",
        )

        # The diffed BulletList should carry one item-level insertion.
        diffed_list = merged[2]
        items = diffed_list["c"]
        item_kinds = [block_kind(item[0]) for item in items]
        self.assertEqual(
            item_kinds,
            ["Div(insertion)", "Plain", "Plain"],
            "first item should be an item-level insertion, others preserved",
        )

    def test_transposition_emits_separate_insertion_and_deletion(self):
        # Pure transposition: 'X' moves from before slot 1 to after slot 2.
        # LCS-based diffs cannot represent moves, so the canonical output is
        # a separate deletion (at the old location) and insertion (at the
        # new location), rather than a substitution.  This is the same shape
        # under both the buggy and fixed implementations - it documents that
        # the fix did not change handling of transpositions.
        a = header(2, "a", "A")
        b = header(2, "b", "B")
        x = header(2, "x", "X")
        y = header(2, "y", "Y")

        before = [a, x, b, y]
        after = [a, b, x, y]

        merged = diff_block_lists(before, after)
        kinds = [block_kind(blk) for blk in merged]

        # The selected LCS (with the current tie-breaking) is [A, B, Y], so
        # the unmatched X appears as a deletion before B and an insertion
        # after B.  Either is fine as long as one is a deletion, the other
        # an insertion, and they straddle a preserved B.
        self.assertEqual(
            kinds,
            [
                "Header",
                "Div(deletion)",
                "Header",
                "Div(insertion)",
                "Header",
            ],
            "transposition should emit a deletion+insertion pair around the "
            "preserved element, not a substitution",
        )


if __name__ == "__main__":
    unittest.main()
