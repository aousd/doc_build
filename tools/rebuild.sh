#!/usr/bin/env sh

rm -rf build
python3.10 pdf_to_png.py pdf_to_png /Users/oleksiypuzikov/aousd_git/core-spec-wg/build/aousd_core_spec.pdf build
python3.10 verify_right_margin.py build