#! /usr/bin/env python3

from doc_build.doc_builder import DocBuilder
from pathlib import Path

test_root = Path(__file__).parent.parent

class MyDocBuilder(DocBuilder):
    pass


if __name__ == "__main__":
    MyDocBuilder(repo_root=test_root).process_argparser()
