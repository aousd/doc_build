#!/usr/bin/env python
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "numpy",
#   "pillow",
# ]
# ///

"""Build side-by-side composites from cropped before/after pairs and
optionally compute pixel-diff stats.

For each immediate subdirectory of ``--screenshots-dir`` that contains
a matching ``before_pNN_cropped.png`` / ``after_pNN_cropped.png`` pair,
writes ``side_by_side.png`` (before on left, after on right with a small
gap and a header label band).

If ``--readme`` is given, also writes a top-level ``README.md`` listing
each branch dir, the page numbers found, and pixel-diff counts (full
page if available, plus cropped).  This README is intentionally minimal:
the agent should hand-edit it to add narrative ("what to look for"
descriptions) since those are task-specific and judgment-driven.
"""

import argparse
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image

CROPPED_RE = re.compile(r"^before_p(\d+)_cropped\.png$")


def diff_count(before_path: Path, after_path: Path, threshold: int = 8) -> int:
    a = np.array(Image.open(before_path).convert("RGB"))
    b = np.array(Image.open(after_path).convert("RGB"))
    if a.shape != b.shape:
        return -1
    return int((np.abs(a.astype(np.int16) - b.astype(np.int16)).max(axis=2) > threshold).sum())


def composite(before_path: Path, after_path: Path, out_path: Path,
              gap: int = 12, label_h: int = 32) -> None:
    before = Image.open(before_path).convert("RGB")
    after = Image.open(after_path).convert("RGB")
    w = max(before.width, after.width)
    h = max(before.height, after.height)
    canvas = Image.new("RGB", (w * 2 + gap, h + label_h), "white")
    canvas.paste(before, (0, label_h))
    canvas.paste(after, (w + gap, label_h))
    canvas.save(out_path)


def find_pairs(branch_dir: Path):
    pairs = []
    for before in sorted(branch_dir.iterdir()):
        m = CROPPED_RE.match(before.name)
        if not m:
            continue
        page = int(m.group(1))
        after = branch_dir / f"after_p{page:02d}_cropped.png"
        if after.exists():
            pairs.append((page, before, after))
    return pairs


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--screenshots-dir", required=True, type=Path)
    parser.add_argument(
        "--readme", action="store_true",
        help="Also write a minimal README.md at --screenshots-dir top level",
    )
    parser.add_argument(
        "--title", default="Branch before/after screenshots",
        help="Title for the README, when --readme is given",
    )
    parser.add_argument(
        "--threshold", default=8, type=int,
        help="Per-pixel max-channel delta to count as 'differing'",
    )
    args = parser.parse_args(argv)

    root = args.screenshots_dir.resolve()
    if not root.is_dir():
        raise SystemExit(f"--screenshots-dir not a directory: {root}")

    entries = []
    for sub in sorted(root.iterdir()):
        if not sub.is_dir() or sub.name.startswith("_") or sub.name.startswith("."):
            continue
        pairs = find_pairs(sub)
        if not pairs:
            print(f"{sub.name}: no cropped pairs, skipping")
            continue
        side = sub / "side_by_side.png"
        composite(pairs[0][1], pairs[0][2], side)
        print(f"{sub.name}: composite -> {side}")

        per_page = []
        for page, before_crop, after_crop in pairs:
            crop_diff = diff_count(before_crop, after_crop, args.threshold)
            full_before = sub / f"before_p{page:02d}.png"
            full_after = sub / f"after_p{page:02d}.png"
            full_diff = (
                diff_count(full_before, full_after, args.threshold)
                if full_before.exists() and full_after.exists() else None
            )
            per_page.append((page, full_diff, crop_diff))
        entries.append((sub.name, per_page))

    if args.readme:
        lines = [f"# {args.title}", ""]
        lines.append(
            "Per-branch cropped before/after comparisons.  Each branch "
            "directory contains:"
        )
        lines.append("")
        lines.append("- `before_pNN.png` / `after_pNN.png`: full-page renders.")
        lines.append(
            "- `before_pNN_cropped.png` / `after_pNN_cropped.png`: focused crops."
        )
        lines.append("- `side_by_side.png`: composite of the cropped views.")
        lines.append("")
        for name, per_page in entries:
            lines.append(f"## {name}")
            lines.append("")
            for page, full_diff, crop_diff in per_page:
                lines.append(f"- Page {page}")
                if full_diff is not None:
                    lines.append(f"  - Full-page differing pixels: {full_diff}")
                lines.append(f"  - Cropped differing pixels: {crop_diff}")
            lines.append("")
        readme_path = root / "README.md"
        readme_path.write_text("\n".join(lines))
        print(f"wrote {readme_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
