#!/usr/bin/env python3
import os
from pandocfilters import toJSONFilter, Image
import shutil
import subprocess

rsvg_convert = shutil.which("rsvg-convert")
if not rsvg_convert:
    raise RuntimeError("rsvg-convert not found")


def convert_svg(key, value, format, metadata):
    if key != "Image":
        return

    image_path = value[2][0]
    base, ext = os.path.splitext(image_path)
    if ext != ".svg":
        return

    png_path = base + ".png"
    dpi = str(192)
    subprocess.check_call(
        [rsvg_convert, image_path, "-o", png_path, "-d", dpi, "-p", dpi]
    )

    value[2][0] = png_path

    return Image(value[0], value[1], value[2])


if __name__ == "__main__":
    toJSONFilter(convert_svg)
