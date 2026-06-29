"""Tests for doc_build.iso_clause_lint — focused on HTML comment handling."""

import tempfile
import unittest
from pathlib import Path

from doc_build.iso_clause_lint import (
    _is_html_comment_block,
    _strip_html_comment_lines,
    check_file,
)


class TestIsHtmlCommentBlock(unittest.TestCase):
    """Unit tests for the _is_html_comment_block helper."""

    def test_single_line_raw_block(self):
        block = {"t": "RawBlock", "c": ["html", "<!-- comment -->\n"]}
        self.assertTrue(_is_html_comment_block(block))

    def test_multi_line_raw_block(self):
        block = {"t": "RawBlock", "c": ["html", "<!--\n  multi\n  line\n-->\n"]}
        self.assertTrue(_is_html_comment_block(block))

    def test_sourcepos_div_wrapping_comment(self):
        block = {
            "t": "Div",
            "c": [
                ["", [], [["wrapper", "1"], ["data-pos", "3:1-4:1"]]],
                [{"t": "RawBlock", "c": ["html", "<!-- wrapped -->\n"]}],
            ],
        }
        self.assertTrue(_is_html_comment_block(block))

    def test_non_comment_raw_block(self):
        block = {"t": "RawBlock", "c": ["html", "<div>not a comment</div>"]}
        self.assertFalse(_is_html_comment_block(block))

    def test_para_block(self):
        block = {"t": "Para", "c": [{"t": "Str", "c": "text"}]}
        self.assertFalse(_is_html_comment_block(block))

    def test_div_wrapping_para(self):
        block = {
            "t": "Div",
            "c": [
                ["", [], []],
                [{"t": "Para", "c": [{"t": "Str", "c": "text"}]}],
            ],
        }
        self.assertFalse(_is_html_comment_block(block))

    def test_non_html_raw_block(self):
        block = {"t": "RawBlock", "c": ["latex", "\\newpage"]}
        self.assertFalse(_is_html_comment_block(block))


class TestStripHtmlCommentLines(unittest.TestCase):
    """Unit tests for _strip_html_comment_lines."""

    def test_single_line_comment_removed(self):
        lines = [(1, "<!-- comment -->"), (2, "real text")]
        self.assertEqual(_strip_html_comment_lines(lines), [(2, "real text")])

    def test_multi_line_comment_removed(self):
        lines = [
            (1, "<!--"),
            (2, "  multi-line content"),
            (3, "-->"),
            (4, "real text"),
        ]
        self.assertEqual(_strip_html_comment_lines(lines), [(4, "real text")])

    def test_long_single_line_iso_comment(self):
        comment = (
            "<!-- ISO TODO (#437 §5.1, §8 step 7): This clause is "
            "informative. Lane: human + LLM. -->"
        )
        lines = [(1, comment), (2, "real text")]
        self.assertEqual(_strip_html_comment_lines(lines), [(2, "real text")])

    def test_no_comments(self):
        lines = [(1, "first"), (2, "second")]
        self.assertEqual(_strip_html_comment_lines(lines), lines)

    def test_empty_input(self):
        self.assertEqual(_strip_html_comment_lines([]), [])

    def test_all_comments(self):
        lines = [(1, "<!-- one -->"), (2, "<!-- two -->")]
        self.assertEqual(_strip_html_comment_lines(lines), [])

    def test_multi_line_comment_between_text(self):
        lines = [
            (1, "before"),
            (2, "<!--"),
            (3, "  inner"),
            (4, "-->"),
            (5, "after"),
        ]
        self.assertEqual(
            _strip_html_comment_lines(lines),
            [(1, "before"), (5, "after")],
        )

    def test_multiple_multi_line_comments(self):
        lines = [
            (1, "<!--"),
            (2, "first comment"),
            (3, "-->"),
            (4, "text"),
            (5, "<!--"),
            (6, "second comment"),
            (7, "-->"),
        ]
        self.assertEqual(_strip_html_comment_lines(lines), [(4, "text")])


def _write_md(content: str) -> Path:
    """Write content to a temp .md file and return its path."""
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8"
    )
    f.write(content)
    f.close()
    return Path(f.name)


class TestCheckFileHtmlComments(unittest.TestCase):
    """Integration tests: check_file with HTML comments between headings."""

    def test_single_line_comment_not_flagged(self):
        path = _write_md(
            "# Parent\n\n<!-- comment -->\n\n## Child\n\nText.\n"
        )
        violations = check_file(path)
        self.assertEqual(violations, [])

    def test_multi_line_comment_not_flagged(self):
        path = _write_md(
            "# Parent\n\n<!--\n  multi-line\n  comment\n-->\n\n## Child\n\nText.\n"
        )
        violations = check_file(path)
        self.assertEqual(violations, [])

    def test_real_body_text_still_flagged(self):
        path = _write_md(
            "# Parent\n\nReal body text.\n\n## Child\n\nText.\n"
        )
        violations = check_file(path)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].heading_text, "Parent")

    def test_comment_plus_body_text_still_flagged(self):
        path = _write_md(
            "# Parent\n\n<!-- comment -->\n\nReal body text.\n\n## Child\n\nText.\n"
        )
        violations = check_file(path)
        self.assertEqual(len(violations), 1)

    def test_single_line_comment_excluded_from_body_lines(self):
        path = _write_md(
            "# Parent\n\n<!-- comment -->\n\nReal body text.\n\n## Child\n\nText.\n"
        )
        violations = check_file(path)
        self.assertEqual(len(violations), 1)
        raw_texts = [line for _, line in violations[0].body_lines]
        for text in raw_texts:
            self.assertNotIn("<!--", text)

    def test_multi_line_comment_excluded_from_body_lines(self):
        path = _write_md(
            "# Parent\n\n<!--\n  TODO note\n-->\n\nReal body text.\n\n## Child\n\nText.\n"
        )
        violations = check_file(path)
        self.assertEqual(len(violations), 1)
        raw_texts = [line for _, line in violations[0].body_lines]
        for text in raw_texts:
            self.assertNotIn("<!--", text)
            self.assertNotIn("-->", text)
            self.assertNotIn("TODO", text)

    def test_only_comments_between_sibling_headings(self):
        """Comments between same-level headings should not trigger either."""
        path = _write_md(
            "# First\n\n## Sub\n\nText.\n\n<!-- comment -->\n\n# Second\n\nText.\n"
        )
        violations = check_file(path)
        self.assertEqual(violations, [])

    def test_no_headings(self):
        path = _write_md("Just some text.\n\n<!-- comment -->\n")
        violations = check_file(path)
        self.assertEqual(violations, [])

    def test_multiple_comments_between_headings(self):
        path = _write_md(
            "# Parent\n\n<!-- one -->\n\n<!-- two -->\n\n## Child\n\nText.\n"
        )
        violations = check_file(path)
        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
