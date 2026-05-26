#!/usr/bin/env python3
"""Pandoc filter to bundle images into output/images/ and rewrite paths to be relative.

For each image path (assumed to be under AOUSD_IMAGES_ROOT):
  1. Compute the path relative to AOUSD_IMAGES_ROOT.
  2. Remove any path components named "images".
  3. Copy the image to AOUSD_OUTPUT_DIR/images/<relative>.
  4. Rewrite the AST image path to images/<relative> (relative from output/ to output/images/).

Both absolute and relative image paths are processed. Relative paths are
resolved against the images root directory (the pandoc input file's directory).

Required pandoc metadata:
  AOUSD_IMAGES_ROOT: absolute path to the images root directory
  AOUSD_OUTPUT_DIR: absolute path to the output directory

An in-process dict tracks which source files have been copied to each destination,
detecting collisions where two different sources map to the same destination path.
"""

import shutil
from pathlib import Path

from pandocfilters import toJSONFilter, Image
from shared_filter_utils import get_image_rel, get_metadata_str

# Maps rel_key -> str(src_abs) for collision detection within a single pandoc run.
_seen: dict[str, str] = {}


def bundle_image(key, value, _format, metadata):
    if key != "Image":
        return

    image_path = value[2][0]

    images_root = Path(get_metadata_str(metadata, "AOUSD_IMAGES_ROOT"))
    output_dir = Path(get_metadata_str(metadata, "AOUSD_OUTPUT_DIR"))

    src = Path(image_path)
    if not src.is_absolute():
        # Relative paths are relative to the images root (pandoc input file location)
        src = images_root / src

    image_rel = get_image_rel(src, images_root)

    dest = output_dir / "images" / image_rel
    rel_key = image_rel.as_posix()

    if rel_key in _seen:
        if _seen[rel_key] != str(src):
            raise RuntimeError(
                f"Image name collision at {rel_key!r}: already mapped from "
                f"{_seen[rel_key]!r}, cannot also map from {str(src)!r}"
            )
        # Already copied earlier in this run; skip
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        _seen[rel_key] = str(src)

    # Relative from output/ (where the .md output file lives) to output/images/.
    new_path = (Path("images") / image_rel).as_posix()

    value[2][0] = new_path
    return Image(value[0], value[1], value[2])


if __name__ == "__main__":
    toJSONFilter(bundle_image)
