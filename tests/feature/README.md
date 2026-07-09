# Feature tests for `doc_build`

Stdlib-`unittest` tests that exercise the public behavior of `doc_build`
modules end-to-end (within Python — they do not invoke pandoc).  No
third-party test dependency.

These are *not* strict unit tests — they call high-level entry points
(e.g. `diff_block_lists`) and let the call fan out through helpers like
`find_longest_common_subsequence`, `_pair_adjacent_changes`, and
`diff_list_nodes` rather than mocking them.

Tests that *specifically* reproduce a previously fixed bug live under
[`tests/regression/`](../regression/) instead — those tests should be
expected to fail against the unfixed code.

## Running

From the repo root:

    pixi run python -m unittest discover -s tests/feature -t .

Or run a single file directly:

    pixi run python tests/feature/test_ast_diff.py
