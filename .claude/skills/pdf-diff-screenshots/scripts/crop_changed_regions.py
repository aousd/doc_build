#!/usr/bin/env python
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "numpy",
#   "pillow",
# ]
# ///

"""Crop before/after PNGs to one or more y-ranges of interest.

Pixel diff alone can't tell you what is *pertinent*.  Content reflow
makes layout shift below the actual change, so a naive bbox of all
changed pixels grows to cover unrelated downstream sections.  The
intended workflow:

1. Read the PDF (and the full-page PNG) to identify which document
   *sections* actually demonstrate the branch's change.
2. Note the pixel y-ranges for those sections by inspecting the
   rendered PNG.
3. Pass them to this script via ``--y-range Y0-Y1`` (repeatable).
4. The script crops each (before, after) pair to those ranges,
   concatenates the strips vertically, and writes
   ``before_pNN_cropped.png`` / ``after_pNN_cropped.png``.

When ``--y-range`` is not given, the script falls back to a coarse
auto-clustering of the pixel-diff mask (split changed rows into
clusters merged by ``--cluster-gap``, optionally keep only the top
``--max-strips`` by changed-row count).  Use the auto path for a quick
first look; switch to ``--y-range`` once you have read the PDF and know
which sections matter.

Walks ``--branch-dir`` for ``before_pNN.png`` / ``after_pNN.png`` pairs.
Falls back to a centered default crop when before and after are
pixel-identical (e.g. for a pure-refactor branch).

Why the horizontal clamp matters:
    A purely image-content change (e.g. a small image swap) has a
    tight x bbox that excludes the surrounding section heading and
    figure caption.  Without ``--min-content-x0`` / ``--min-content-x1``,
    the crop is too tight to recognize WHERE in the document the
    change occurred.  Set these to your document's left/right
    text-block boundaries (in pixels at the rendered DPI) to anchor
    crops to the full content width.
"""

import argparse
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image

PAGE_RE = re.compile(r"^before_p(\d+)\.png$")


def load_rgb(path: Path) -> np.ndarray:
    return np.array(Image.open(path).convert("RGB"))


def diff_mask(before: np.ndarray, after: np.ndarray, threshold: int) -> np.ndarray:
    if before.shape != after.shape:
        raise SystemExit(
            f"shape mismatch: before {before.shape} vs after {after.shape}"
        )
    diff = np.abs(before.astype(np.int16) - after.astype(np.int16)).max(axis=2)
    return diff > threshold


def x_range_for_mask(mask: np.ndarray, w: int, pad: int, min_x0, min_x1):
    """X-range covering all changed pixels, expanded by pad and clamped."""
    xs_any = mask.any(axis=0)
    if not xs_any.any():
        return None
    x0 = int(np.argmax(xs_any))
    x1 = w - int(np.argmax(xs_any[::-1]))
    left = max(0, x0 - pad)
    right = min(w, x1 + pad)
    if min_x0 is not None:
        left = min(min_x0, left)
    if min_x1 is not None:
        right = max(min_x1, right)
    return left, right


def find_y_clusters(mask: np.ndarray, gap_threshold: int):
    """Return [(y_start, y_end_exclusive), ...] clusters of changed rows.

    Adjacent changed-row runs separated by an unchanged gap of fewer
    than ``gap_threshold`` rows are merged into one cluster.
    """
    rows_changed = mask.any(axis=1)
    if not rows_changed.any():
        return []
    runs = []
    in_run = False
    start = 0
    for i, c in enumerate(rows_changed):
        if c and not in_run:
            start = i
            in_run = True
        elif not c and in_run:
            runs.append((start, i))
            in_run = False
    if in_run:
        runs.append((start, len(rows_changed)))
    merged = [list(runs[0])]
    for s, e in runs[1:]:
        if s - merged[-1][1] <= gap_threshold:
            merged[-1][1] = e
        else:
            merged.append([s, e])
    return [tuple(m) for m in merged]


def cluster_to_strip(cluster, pad: int, h: int, x_left: int, x_right: int):
    s, e = cluster
    return (x_left, max(0, s - pad), x_right, min(h, e + pad))


def stack_strips(image: np.ndarray, strips, strip_gap: int,
                 gap_color=(255, 255, 255)) -> Image.Image:
    crops = [image[y0:y1, x0:x1] for x0, y0, x1, y1 in strips]
    if not crops:
        raise ValueError("no strips")
    width = max(c.shape[1] for c in crops)
    total_h = sum(c.shape[0] for c in crops) + strip_gap * (len(crops) - 1)
    canvas = np.full((total_h, width, 3), gap_color, dtype=np.uint8)
    y = 0
    for c in crops:
        ch, cw = c.shape[:2]
        canvas[y:y + ch, :cw] = c
        y += ch + strip_gap
    return Image.fromarray(canvas)


def find_pairs(branch_dir: Path):
    pairs = []
    for before in sorted(branch_dir.iterdir()):
        m = PAGE_RE.match(before.name)
        if not m:
            continue
        page = int(m.group(1))
        after = branch_dir / f"after_p{page:02d}.png"
        if after.exists():
            pairs.append((page, before, after))
    return pairs


def strips_from_y_ranges(y_ranges, h, x_left, x_right):
    return [(x_left, max(0, y0), x_right, min(h, y1)) for y0, y1 in y_ranges]


def auto_strips(mask, padding, cluster_gap, max_strips, h, w, min_x0, min_x1):
    """Return (strips, note) for the auto-cluster path."""
    x_range = x_range_for_mask(mask, w, padding, min_x0, min_x1)
    if x_range is None:
        raise RuntimeError("mask had changed pixels but no x-range")
    x_left, x_right = x_range
    clusters = find_y_clusters(mask, cluster_gap)
    if max_strips is not None and len(clusters) > max_strips:
        ranked = sorted(clusters, key=lambda c: c[1] - c[0], reverse=True)
        kept = set(map(tuple, ranked[:max_strips]))
        clusters = [c for c in clusters if tuple(c) in kept]
    strips = [cluster_to_strip(c, padding, h, x_left, x_right) for c in clusters]
    kept_note = "" if max_strips is None else f", kept top {max_strips}"
    note = (
        f"x-range [{x_left}, {x_right}); {len(clusters)} y-cluster(s) "
        f"(merge gap <= {cluster_gap}px{kept_note}) -> strips {strips}"
    )
    return strips, note


def process_pair(page, before_path, after_path, branch_dir, padding,
                 threshold, cluster_gap, max_strips, strip_gap,
                 min_x0, min_x1, y_ranges, y_ranges_before, y_ranges_after):
    before = load_rgb(before_path)
    after = load_rgb(after_path)
    h, w = before.shape[:2]

    mask = diff_mask(before, after, threshold)
    x_left = min_x0 if min_x0 is not None else 0
    x_right = min_x1 if min_x1 is not None else w

    asymmetric = bool(y_ranges_before or y_ranges_after)
    before_ranges = y_ranges_before or y_ranges
    after_ranges = y_ranges_after or y_ranges

    if before_ranges or after_ranges:
        before_strips = strips_from_y_ranges(before_ranges or [], h, x_left, x_right)
        after_strips = strips_from_y_ranges(after_ranges or [], h, x_left, x_right)
        kind = "asymmetric" if asymmetric else "symmetric"
        note = (
            f"manual y-ranges ({kind}); x-range [{x_left}, {x_right}); "
            f"before strips {before_strips}; after strips {after_strips}"
        )
    elif not mask.any():
        margin_x = w // 8
        margin_y = h // 6
        strip = (margin_x, margin_y, w - margin_x, int(h * 0.6))
        before_strips = after_strips = [strip]
        note = "no pixel difference; using a default centered crop"
    else:
        strips, note = auto_strips(mask, padding, cluster_gap, max_strips,
                                   h, w, min_x0, min_x1)
        before_strips = after_strips = strips
    print(f"  page {page}: {note}")

    before_img = stack_strips(before, before_strips, strip_gap)
    after_img = stack_strips(after, after_strips, strip_gap)
    before_crop = branch_dir / f"before_p{page:02d}_cropped.png"
    after_crop = branch_dir / f"after_p{page:02d}_cropped.png"
    before_img.save(before_crop)
    after_img.save(after_crop)
    print(f"  wrote {before_crop.name}, {after_crop.name}")
    return (before_strips, after_strips), note


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--branch-dir", required=True, type=Path)
    parser.add_argument("--padding", default=60, type=int,
                        help="Vertical px above/below each cluster")
    parser.add_argument("--diff-threshold", default=8, type=int,
                        help="Per-pixel max-channel delta to count as 'changed'")
    parser.add_argument(
        "--cluster-gap", default=120, type=int,
        help="Merge adjacent y-clusters separated by an unchanged gap "
             "shorter than this many px.  Larger -> fewer, taller "
             "strips that include more unchanged context.  Smaller -> "
             "tighter strips that drop more middle whitespace.",
    )
    parser.add_argument(
        "--strip-gap", default=8, type=int,
        help="Px of whitespace inserted between concatenated strips",
    )
    parser.add_argument(
        "--max-strips", default=None, type=int,
        help="Auto-cluster mode only: keep at most N clusters by changed-row "
             "count.  Useful to drop downstream-reflow noise clusters.",
    )
    parser.add_argument(
        "--y-range", action="append", default=[],
        help="Y0-Y1 (1-indexed pixel rows) to crop, repeatable.  When given, "
             "skips auto cluster detection entirely - the agent has decided "
             "from reading the PDF/PNG which y-bands are pertinent.  Padding "
             "is NOT applied; pass exact bounds.  Applies to both before and "
             "after unless overridden per-side below.",
    )
    parser.add_argument(
        "--y-range-before", action="append", default=[],
        help="Like --y-range but only for the BEFORE side.  Use when the "
             "change adds or removes content so the pertinent region is a "
             "different height in before vs after.",
    )
    parser.add_argument(
        "--y-range-after", action="append", default=[],
        help="Like --y-range but only for the AFTER side.",
    )
    parser.add_argument("--min-content-x0", default=None, type=int,
                        help="Left edge to clamp crops to (px). Anchors narrow "
                             "image-only diffs to the document content width.")
    parser.add_argument("--min-content-x1", default=None, type=int,
                        help="Right edge to clamp crops to (px).")
    parser.add_argument("--readme", action="store_true",
                        help="Append crop notes to README.txt in the branch dir")
    args = parser.parse_args(argv)

    def parse_ranges(raw, flag):
        out = []
        for r in raw:
            if "-" not in r:
                raise SystemExit(f"{flag} must be Y0-Y1, got: {r!r}")
            a, b = r.split("-", 1)
            y0, y1 = int(a), int(b)
            if y0 >= y1:
                raise SystemExit(f"{flag} Y0 must be < Y1, got {r!r}")
            out.append((y0, y1))
        return out

    y_ranges = parse_ranges(args.y_range, "--y-range")
    y_ranges_before = parse_ranges(args.y_range_before, "--y-range-before")
    y_ranges_after = parse_ranges(args.y_range_after, "--y-range-after")

    branch_dir = args.branch_dir.resolve()
    if not branch_dir.is_dir():
        raise SystemExit(f"--branch-dir not a directory: {branch_dir}")

    pairs = find_pairs(branch_dir)
    if not pairs:
        raise SystemExit(
            f"no before_pNN.png / after_pNN.png pairs found in {branch_dir}"
        )

    print(f"{branch_dir.name}: cropping {len(pairs)} page pair(s)")
    notes = []
    for page, before_path, after_path in pairs:
        strips, note = process_pair(
            page, before_path, after_path, branch_dir,
            args.padding, args.diff_threshold,
            args.cluster_gap, args.max_strips, args.strip_gap,
            args.min_content_x0, args.min_content_x1,
            y_ranges, y_ranges_before, y_ranges_after,
        )
        notes.append((page, strips, note))

    if args.readme:
        readme = branch_dir / "README.txt"
        existing = readme.read_text() if readme.exists() else ""
        with readme.open("w") as fh:
            fh.write(existing.rstrip() + "\n")
            for page, strips, note in notes:
                fh.write(f"Crop note (page {page}): {note}\n")
                fh.write(f"Crop strips page {page}: {strips}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
