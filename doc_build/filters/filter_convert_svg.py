#!/usr/bin/env python3
"""Rasterise SVG images to PNG for the DOCX writer.

The PNG is rendered at ``AOUSD_DOCX_SVG_SCALE`` times the SVG's intrinsic pixel
size and labelled with a matching pHYs resolution, so the figure gains detail
without changing the size it occupies on the page.
"""
import math
import os
import shutil
import struct
import subprocess
import zlib

from pandocfilters import toJSONFilter, Image
from shared_filter_utils import get_metadata_str

# What pandoc assumes for a PNG carrying no pHYs chunk.
PANDOC_PNG_FALLBACK_DPI = 72

METADATA_KEY = "AOUSD_DOCX_SVG_SCALE"

rsvg_convert = shutil.which("rsvg-convert")
if not rsvg_convert:
    raise RuntimeError("rsvg-convert not found")


def render(svg_path, png_path, extra_args=()):
    subprocess.check_call([rsvg_convert, svg_path, "-o", png_path, *extra_args])


def get_png_size(png_path):
    """Read a PNG's pixel dimensions out of its IHDR."""
    with open(png_path, "rb") as f:
        header = f.read(24)
    if header[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{png_path} is not a PNG")
    return struct.unpack(">II", header[16:24])


def _pixels_per_metre(dpi):
    # Rounds up, not to nearest: pandoc recovers dpi as ppm * 254 // 10000, so a
    # rounded value can read back one dpi low and resize the figure.
    return math.ceil(dpi * 10000 / 254)


def set_png_resolution(png_path, dpi):
    """Rewrite `png_path` with a pHYs chunk declaring `dpi` on both axes."""
    with open(png_path, "rb") as f:
        data = f.read()

    ppm = _pixels_per_metre(dpi)
    body = struct.pack(">IIB", ppm, ppm, 1)
    crc = zlib.crc32(b"pHYs" + body) & 0xFFFFFFFF
    phys = struct.pack(">I", len(body)) + b"pHYs" + body + struct.pack(">I", crc)

    # pHYs must precede the image data; drop any existing one so a rerun over
    # this filter's own output cannot leave two.
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
        return 1


def convert_svg(key, value, format, metadata):
    if key != "Image":
        return

    image_path = value[2][0]
    base, ext = os.path.splitext(image_path)
    if ext != ".svg":
        return

    scale = get_scale(metadata)
    png_path = base + ".png"

    render(image_path, png_path)
    if scale != 1:
        # Scale the 1:1 pixel grid explicitly rather than with -z, which rounds
        # each axis up on its own and can land a pixel short of an exact
        # multiple, moving the figure on the page.
        width, height = get_png_size(png_path)
        render(image_path, png_path,
               ["-w", str(width * scale), "-h", str(height * scale)])
    set_png_resolution(png_path, scale * PANDOC_PNG_FALLBACK_DPI)

    value[2][0] = png_path

    return Image(value[0], value[1], value[2])


if __name__ == "__main__":
    toJSONFilter(convert_svg)
