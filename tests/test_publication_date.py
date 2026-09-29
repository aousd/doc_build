"""Tests for the publication date that sets the cover date and copyright year."""

import argparse
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from doc_build.doc_builder import DocBuilder


class TestPublicationDate(unittest.TestCase):

    def setUp(self):
        self.builder = DocBuilder(repo_root=Path(__file__).parent)
        env = {k: v for k, v in os.environ.items() if k != "DOC_BUILD_DATE"}
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_flag_wins_over_environment(self):
        os.environ["DOC_BUILD_DATE"] = "2025-12-12"
        args = argparse.Namespace(publication_date=date(2026, 8, 13))
        self.assertEqual(self.builder.get_publication_date(args), date(2026, 8, 13))
        self.assertTrue(self.builder.has_explicit_publication_date(args))

    def test_environment_used_without_flag(self):
        os.environ["DOC_BUILD_DATE"] = "2027-03-01"
        args = argparse.Namespace(publication_date=None)
        self.assertEqual(self.builder.get_publication_date(args), date(2027, 3, 1))
        self.assertTrue(self.builder.has_explicit_publication_date(args))

    def test_defaults_to_today(self):
        args = argparse.Namespace()
        self.assertEqual(self.builder.get_publication_date(args), date.today())
        self.assertFalse(self.builder.has_explicit_publication_date(args))

    def test_publish_copyright_carries_publication_year(self):
        with tempfile.TemporaryDirectory() as tmp:
            combined = Path(tmp) / "combined.md"
            combined.write_text("body\n", encoding="utf-8")
            self.builder.add_publish_copyright(combined, date(2027, 1, 15))
            text = combined.read_text(encoding="utf-8")
        self.assertIn("Copyright @ 2027 Alliance for OpenUSD", text)
        self.assertNotIn("{{year}}", text)


if __name__ == "__main__":
    unittest.main()
