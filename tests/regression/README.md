# Regression tests for `doc_build`

Stdlib-`unittest` regression tests for the Python modules in `doc_build/`.
No third-party test dependency.

Each test here corresponds to a specific bug that was fixed; the docstring
should describe the bug and the failure mode it would reproduce against the
unfixed code. Add a new test file (or test case) per fixed bug, rather than
rewriting existing ones.

## Running

From the repo root:

    pixi run python -m unittest discover -s tests/regression -t .

Or run a single file directly:

    pixi run python tests/regression/test_diff_ordering_with_duplicate_nodes.py
