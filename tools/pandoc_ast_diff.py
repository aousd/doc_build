#!/usr/bin/env python3

"""
Pandoc AST Differencing Tool

This script takes two JSON files representing Pandoc Abstract Syntax Trees (ASTs),
computes the difference between them, and outputs a new Pandoc AST JSON file.
The output file contains a merged view, with added or removed
nodes annotated with custom metadata.

Usage:
    python pandoc_ast_diff.py before.json after.json output.json
"""

import argparse
import sys
from pathlib import Path

try:
    from doc_build.ast_diff import diff_ast_files
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from doc_build.ast_diff import diff_ast_files


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Diff two Pandoc AST JSON files and annotate the changes."
    )
    parser.add_argument("before_file", help="Path to the 'before' Pandoc JSON file.")
    parser.add_argument("after_file", help="Path to the 'after' Pandoc JSON file.")
    parser.add_argument("output_file", help="Path for the output annotated JSON file.")

    args = parser.parse_args()

    diff_ast_files(args.before_file, args.after_file, args.output_file)

