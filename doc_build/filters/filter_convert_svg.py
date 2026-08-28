#!/usr/bin/env python3
"""Rasterise SVG images to PNG so the DOCX writer can place them.

Word cannot place an SVG, so every SVG reference is rendered to a PNG here.
The raster is produced at ``AOUSD_DOCX_IMAGE_SCALE`` times the SVG's intrinsic
pixel size and then labelled with a matching physical resolution, so the figure
gains detail without changing the size it occupies on the page.
"""
import math
import os
import shutil
import struct
import subprocess
import zlib

from pandocfilters import toJSONFilter, Image
from shared_filter_utils import get_metadata_str

# Pandoc reads a PNG's physical resolution from its pHYs chunk and falls back to
# 72 dpi when there is none, so a 1x raster is laid out at intrinsic-pixels/72
# inches.  Declaring scale * 72 dpi therefore reproduces the 1x layout exactly.
PANDOC_PNG_FALLBACK_DPI = 72

# Kept in sync with DEFAULT_DOCX_IMAGE_SCALE in doc_builder.py; this value only
# applies when a caller drives the filter without passing the metadata key.
DEFAULT_SCALE = 3

METADATA_KEY = "AOUSD_DOCX_IMAGE_SCALE"

rsvg_convert = shutil.which("rsvg-convert")
if not rsvg_convert:
    raise RuntimeError("rsvg-convert not found")


def render(svg_path, png_path, extra_args=()):
    subprocess.check_call(
        [rsvg_convert, svg_path, "-o", png_path, *extra_args]
    )


def get_png_size(png_path):
    """Read a PNG's pixel dimensions out of its IHDR."""
    with open(png_path, "rb") as f:
        header = f.read(24)
    if header[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{png_path} is not a PNG")
    return struct.unpack(">II", header[16:24])


def _pixels_per_metre(dpi):
    """Smallest pHYs value that reads back as exactly `dpi`.

    Consumers recover dots-per-inch with integer arithmetic --- pandoc uses
    ``pixels_per_metre * 254 // 10000`` --- so a rounded conversion can land one
    below the intended value and silently resize the figure.  Rounding up keeps
    the truncated result exact.
    """
    return math.ceil(dpi * 10000 / 254)


def set_png_resolution(png_path, dpi):
    """Rewrite `png_path` with a pHYs chunk declaring `dpi` on both axes."""
    with open(png_path, "rb") as f:
        data = f.read()

    ppm = _pixels_per_metre(dpi)
    body = struct.pack(">IIB", ppm, ppm, 1)
    crc = zlib.crc32(b"pHYs" + body) & 0xFFFFFFFF
    phys = struct.pack(">I", len(body)) + b"pHYs" + body + struct.pack(">I", crc)

    # pHYs must precede the image data; drop any existing one so rerunning the
    # filter over its own output cannot leave two.
    chunks, offset, written = [data[:8]], 8, False
    while offset < len(data):
        (length,) = struct.unpack(">I", data[offset:offset + 4])
        chunk_type = data[offset + 4:offset + 8]
        end = offset + 12 + length
        if chunk_type != b"pHYs":
            if not written and chunk_type != b"IHDR":
                chunks.append(phys)
                written = True
            chunks.append(data[offset:end])
        offset = end

    with open(png_path, "wb") as f:
        f.write(b"".join(chunks))


def get_scale(metadata):
    try:
        return int(get_metadata_str(metadata, METADATA_KEY))
    except KeyError:
        return DEFAULT_SCALE


def convert_svg(key, value, format, metadata):
    if key != "Image":
        return

    image_path = value[2][0]
    base, ext = os.path.splitext(image_path)
    if ext != ".svg":
        return

    scale = get_scale(metadata)
    png_path = base + ".png"

    # rsvg-convert's -d/-p resolve *physical* SVG units, and every SVG here is
    # sized in pixels, so they cannot raise detail; only the output raster size
    # can.  Render 1:1 first to learn that size, then redraw the same pixel grid
    # scaled up.  -z would round each axis up independently and so can land a
    # pixel short of an exact multiple, which moves the figure on the page.
    render(image_path, png_path)
    if scale != 1:
        width, height = get_png_size(png_path)
        render(image_path, png_path,
               ["-w", str(width * scale), "-h", str(height * scale)])
    set_png_resolution(png_path, scale * PANDOC_PNG_FALLBACK_DPI)

    value[2][0] = png_path

    return Image(value[0], value[1], value[2])


if __name__ == "__main__":
    toJSONFilter(convert_svg)
