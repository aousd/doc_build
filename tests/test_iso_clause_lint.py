"""Tests for doc_build.iso_clause_lint — focused on HTML comment handling."""

import tempfile
import unittest
from pathlib import Path

from doc_build.iso_clause_lint import (
    _is_html_comment_block,
    _is_html_comment_line,
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


class TestIsHtmlCommentLine(unittest.TestCase):
    """Unit tests for the _is_html_comment_line helper."""

    def test_single_line_comment(self):
        self.assertTrue(_is_html_comment_line("<!-- comment -->"))

    def test_opening_tag(self):
        self.assertTrue(_is_html_comment_line("<!--"))

    def test_closing_tag(self):
        self.assertTrue(_is_html_comment_line("  -->"))

    def test_blank_line(self):
        self.assertTrue(_is_html_comment_line("   "))

    def test_regular_text(self):
        self.assertFalse(_is_html_comment_line("Some body text."))

    def test_heading(self):
        self.assertFalse(_is_html_comment_line("## Heading"))


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

    def test_comment_lines_excluded_from_body_lines(self):
        path = _write_md(
            "# Parent\n\n<!-- comment -->\n\nReal body text.\n\n## Child\n\nText.\n"
        )
        violations = check_file(path)
        self.assertEqual(len(violations), 1)
        raw_texts = [line for _, line in violations[0].body_lines]
        for text in raw_texts:
            self.assertNotIn("<!--", text)

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
