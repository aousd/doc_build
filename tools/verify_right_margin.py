import os
import sys

from PIL import Image

image_dir = sys.argv[-1]    # Directory with PNG images
right_edge_width = 100      # Number of pixels from the right edge to check - 1cm margin with 300 dpi is ~120
black_threshold = 50        # Max value to consider a pixel "black" (0 is pure black)


def is_black(pixel, threshold):
    if isinstance(pixel, int):  # grayscale
        return pixel < threshold
    return all(channel < threshold for channel in pixel[:3])  # RGB(A)


def check_right_edge_for_black(image_path):
    with Image.open(image_path) as img:
        img = img.convert('RGB')
        width, height = img.size
        for x in range(width - right_edge_width, width):
            for y in range(height):
                if is_black(img.getpixel((x, y)), black_threshold):
                    return True
    return False


def scan_directory_for_right_edge_issues(directory):
    flagged_files = []
    for filename in sorted(os.listdir(directory)):
        if filename.lower().endswith('.png'):
            path = os.path.join(directory, filename)
            if check_right_edge_for_black(path):
                flagged_files.append(filename)
                print(f"⚠️ Black pixel detected on the right edge: {filename}")
    if not flagged_files:
        print("✅ No black pixels detected on right edges.")
    return flagged_files


scan_directory_for_right_edge_issues(image_dir)
