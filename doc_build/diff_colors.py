"""Diff color hex values - single source of truth for HTML/CSS and LaTeX.

Hex values are without the leading '#'.  HTML callers prepend '#'; LaTeX
callers use them directly with \\definecolor{...}{HTML}{...}.

These are passed to the LaTeX template via pandoc '-V diff-section-ins-pale-green=...' etc.
and used in HTML inline styles by filter_render_diff.py.
"""

DIFF_SECTION_INS_PALE_GREEN = "e6ffec"  # pale green - block-level insertion background
DIFF_SECTION_DEL_PALE_RED   = "ffeef0"  # pale red   - block-level deletion background
DIFF_WORD_INS_GREEN         = "acf2bd"  # green      - word-level insertion background
DIFF_WORD_DEL_RED           = "ffb5bd"  # red        - word-level deletion background
