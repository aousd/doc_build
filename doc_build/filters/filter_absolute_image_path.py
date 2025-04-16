#!/usr/bin/env python3
import os
from pandocfilters import toJSONFilter, Image
from pathlib import Path


def convert_image_paths(key, value, format, metadata):
    if key == "Image":
        alt_text, image_path = value[1], value[2][0]

        # If the image path is relative, make it absolute
        if not os.path.isabs(image_path):
            build_directory = metadata["PATH"]["c"][0]["c"]
            absolute_path = (Path(build_directory) / image_path).resolve().as_posix()  # otherwise Pandoc would fail
            value[2][0] = absolute_path

        return Image(value[0], value[1], value[2])


if __name__ == "__main__":
    toJSONFilter(convert_image_paths)
