#!/usr/bin/env python
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///

"""Render specific pages from a before/after PDF pair to PNGs.

Output filenames are ``before_pNN.png`` / ``after_pNN.png`` in
``--out-dir``, where NN is the zero-padded 1-indexed page number.

IMPORTANT - page numbering:
    pdftoppm pages are 1-indexed AND include any title/cover page that
    has no printed footer number.  If the document footer reads
    "Page N", the corresponding pdftoppm page is typically N+1.  When
    the user names a page from a footer, add 1 before passing it here
    (and verify by reading the rendered PNG).
"""

import argparse
import subprocess
import sys
from pathlib import Path


def render_page(pdf_path: Path, page: int, out_dir: Path, prefix: str, dpi: int) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp_prefix = out_dir / f"_render_{prefix}_p{page:02d}"
    subprocess.check_call([
        "pdftoppm",
        "-r", str(dpi),
        "-png",
        "-f", str(page),
        "-l", str(page),
        str(pdf_path),
        str(tmp_prefix),
    ])
    rendered = sorted(out_dir.glob(f"{tmp_prefix.name}-*.png"))
    if not rendered:
        rendered = sorted(out_dir.glob(f"{tmp_prefix.name}.png"))
    if not rendered:
        raise SystemExit(f"pdftoppm did not produce a PNG for {pdf_path} page {page}")
    final = out_dir / f"{prefix}_p{page:02d}.png"
    if final.exists():
        final.unlink()
    rendered[-1].rename(final)
    return final


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--before-pdf", required=True, type=Path)
    parser.add_argument("--after-pdf", required=True, type=Path)
    parser.add_argument(
        "--page", action="append", required=True, type=int, dest="pages",
        help="Page number to render (1-indexed, pdftoppm convention). Repeatable.",
    )
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--dpi", default=150, type=int)
    args = parser.parse_args(argv)

    for page in args.pages:
        before_png = render_page(args.before_pdf, page, args.out_dir, "before", args.dpi)
        after_png = render_page(args.after_pdf, page, args.out_dir, "after", args.dpi)
        print(f"page {page}: {before_png.name}, {after_png.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
