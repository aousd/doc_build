"""
brew install poppler imagemagick
mkdir output_xelatex
mkdir output_tectonic
mkdir output_diff
python3 compare.py pdf_to_png xelatex.pdf output_xelatex
python3 compare.py pdf_to_png tectonic.pdf output_tectonic
python3 compare.py compare_pngs output_xelatex output_tectonic output_diff
"""

import os
import sys
import subprocess
import re
import threading
from concurrent.futures import ThreadPoolExecutor


def export_page(pdf_path, output_dir, density, page):
    png_path = os.path.join(output_dir, f"page{page}.png")
    # cmd = ["magick", "-density", str(density), f"{pdf_path}[{page-1}]", png_path]
    cmd = ["magick", "-density", str(density), f"{pdf_path}[{page-1}]", "-alpha", "off", png_path]
    subprocess.run(cmd, check=True)
    with threading.Lock():
        sys.stderr.write(".")
        sys.stderr.flush()


def pdf_to_png(pdf_path, output_dir, density=300):
    """Converts a PDF to PNG images, one per page."""

    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    try:
        page_count_cmd = ["pdfinfo", pdf_path]
        result = subprocess.run(page_count_cmd, capture_output=True, text=True, check=True)
        for line in result.stdout.splitlines():
            if "Pages:" in line:
                page_count = int(line.split(":")[1].strip())
                break
        else:
            raise ValueError("Could not determine page count.")

        with ThreadPoolExecutor(max_workers=8) as executor:
            for page in range(1, page_count + 1):
                executor.submit(export_page, pdf_path, output_dir, density, page)

        # for page in range(1, page_count + 1):
        #     png_path = os.path.join(output_dir, f"page{page}.png")
        #     magick_cmd = ["magick", "-density", str(density), f"{pdf_path}[{page-1}]", "-alpha", "off", png_path]
        #     subprocess.run(magick_cmd, check=True)
        #
        #     percent = page / float(page_count)
        #     progress_bar_size = 50
        #     filled_length = int(progress_bar_size * percent)
        #     bar = '=' * filled_length + '-' * (progress_bar_size - filled_length)
        #     sys.stdout.write(f'\r|{bar}| {percent * 100:.1f}%')
        #     sys.stdout.flush()

        sys.stderr.write("\n")

    except subprocess.CalledProcessError as e:
        print(f"Error: {e}")
        print(f"Stdout: {e.stdout.decode()}")
        print(f"Stderr: {e.stderr.decode()}")
        sys.exit(1)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        sys.exit(1)


def natural_sort_key(s):
    """Key for natural sorting."""
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]


def compare_pngs(png_dir1, png_dir2, output_diff_dir):
    """Compares PNG images in two directories, assuming filenames match."""

    if not os.path.exists(png_dir1):
        raise FileNotFoundError(f"PNG directory 1 not found: {png_dir1}")
    if not os.path.exists(png_dir2):
        raise FileNotFoundError(f"PNG directory 2 not found: {png_dir2}")

    if not os.path.exists(output_diff_dir):
        os.makedirs(output_diff_dir)

    png_files1 = sorted([f for f in os.listdir(png_dir1) if f.endswith(".png")], key=natural_sort_key)
    png_files2 = sorted([f for f in os.listdir(png_dir2) if f.endswith(".png")], key=natural_sort_key)

    if len(png_files1) != len(png_files2):
        raise ValueError("Number of PNG files in the directories do not match.")

    num_pages = len(png_files1)

    for i in range(num_pages):
        png1_path = os.path.join(png_dir1, png_files1[i])
        png2_path = os.path.join(png_dir2, png_files2[i])
        diff_path = os.path.join(output_diff_dir, f"diff_page{i+1}.png")

        try:
            print(" ".join(["compare", "-metric", "AE", "-highlight-color", "red", png1_path, png2_path, diff_path]))
            compare_cmd = ["compare", "-metric", "AE", "-highlight-color", "red", png1_path, png2_path, diff_path]
            subprocess.run(compare_cmd, check=True)
        except subprocess.CalledProcessError as e:
            pass # because compare would return != 0 for every diff

if __name__ == "__main__":
    if len(sys.argv) < 4 or len(sys.argv) > 5:
        print("Usage (PDF to PNG): python script.py pdf_to_png <pdf_path> <output_png_dir> [<density>]")
        print("Usage (Compare PNGs): python script.py compare_pngs <png_dir1> <png_dir2> <output_diff_dir>")
        sys.exit(1)

    command = sys.argv[1]

    if command == "pdf_to_png":
        pdf_path = sys.argv[2]
        output_png_dir = sys.argv[3]
        density = int(sys.argv[4]) if len(sys.argv) == 5 else 300
        pdf_to_png(pdf_path, output_png_dir, density)
        print(f"PNG images saved to: {output_png_dir}")

    elif command == "compare_pngs":
        png_dir1 = sys.argv[2]
        png_dir2 = sys.argv[3]
        output_diff_dir = sys.argv[4]
        compare_pngs(png_dir1, png_dir2, output_diff_dir)
        print(f"Diff images saved to: {output_diff_dir}")
    
    else:
        print("Invalid command. Use 'pdf_to_png' or 'compare_pngs'.")
        sys.exit(1)