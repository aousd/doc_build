#!/usr/bin/env python3.10

import sys
from collections import defaultdict
from pandocfilters import toJSONFilter
import subprocess
import platform

words = defaultdict(int)
deflang = "en"


# Function to get the default language from the metadata
def get_default_language(meta):
    return {}  # Eliminate metadata so it isn't spellchecked


# Function to handle results after processing all elements
def process_results(key, value, format, meta):
    if key == "Pandoc":
        keys = list(words.keys())
        inp = "\n".join(keys)

        if platform.system() != "Darwin":
            try:
                result = subprocess.run(
                    ["aspell", "list", "-l", deflang],
                    input=inp,
                    text=True,
                    capture_output=True,
                    check=True,
                )
                outp = result.stdout
            except subprocess.CalledProcessError as e:
                sys.stderr.write(f"Error running aspell: {e}\n")
                sys.exit(1)

            for word in outp.strip().split("\n"):
                if word:
                    print(word)
        else:
            import mac_spellchecker

            for term in keys:
                mac_spellchecker.wrapper(term)

        sys.exit(0)  # Exit to prevent further processing


# Function to check strings for duplicate words
def check_string(key, value, format, meta):
    if key == "Str":
        words[value] += 1


# Function to check spans for words and handle language attribute
def check_span(key, value, format, meta):
    if key == "Span":
        _, content = value
        for c in content:
            if c["t"] == "Str":
                words[c["c"]] += 1
        return []  # Remove span so it isn't rechecked


# Function to check divs for words and handle language attribute
def check_div(key, value, format, meta):
    if key == "Div":
        _, content = value
        for c in content:
            if c["t"] == "Str":
                words[c["c"]] += 1
        return []  # Remove div so it isn't rechecked


# Register filters for handling metadata, divs, spans, and strings
def spellchecking_filter(key, value, format, meta):
    if key == "Meta":
        return get_default_language(value)
    elif key == "Div":
        return check_div(key, value, format, meta)
    elif key == "Span":
        return check_span(key, value, format, meta)
    elif key == "Str":
        return check_string(key, value, format, meta)
    # elif key == 'Pandoc':
    #     return process_results(key, value, format, meta)


if __name__ == "__main__":
    toJSONFilter(spellchecking_filter)
    process_results("Pandoc", None, None, None)
