#! /usr/bin/env python3

import re
from pathlib import Path

from doc_build.doc_builder import DocBuilder

test_root = Path(__file__).parent.parent


def check_no_absolute_image_paths(output_dir: Path):
    """Assert that HTML and MD outputs contain no absolute image paths."""
    absolute_path_pattern = re.compile(r'!\[.*?\]\((/[^)]+)\)|src="(/[^"]+\.(svg|png|jpg|jpeg|gif))"')
    errors = []
    for suffix in (".html", ".md"):
        for output_file in output_dir.glob(f"*{suffix}"):
            content = output_file.read_text(encoding="utf-8")
            for match in absolute_path_pattern.finditer(content):
                abs_path = match.group(1) or match.group(2)
                errors.append(f"{output_file}: absolute image path found: {abs_path!r}")
    if errors:
        raise AssertionError(
            "Absolute image paths found in output (should be relative):\n"
            + "\n".join(f"  {e}" for e in errors)
        )


class MyDocBuilder(DocBuilder):

    def build_docs(self, args):
        result = super().build_docs(args)
        check_no_absolute_image_paths(args.output)
        return result


if __name__ == "__main__":
    MyDocBuilder(repo_root=test_root).process_argparser()
