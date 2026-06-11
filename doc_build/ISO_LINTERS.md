# ISO linters

Three linters check Markdown specification sources for compliance with
ISO/IEC Directives, Part 2.  Each can run standalone or as a DocBuilder
subcommand.  All accept a directory (scanned recursively) or a single
`.md` file.

## Run all linters at once

```sh
# Lint only (exits non-zero on any violation)
pixi run python -m doc_build.doc_builder iso_lint_all

# Fix what can be auto-fixed
pixi run python -m doc_build.doc_builder iso_fix_all
```

`iso_fix_all` auto-fixes heading case and bold table headers.  Run
`iso_lint_all` afterwards to check for clause structure issues
(which require manual editing).

## Heading sentence case

ISO 11.4 requires clause titles in sentence case.

```sh
# Check (exits non-zero on violations)
pixi run python -m doc_build.iso_heading_case_lint specification/

# Check a single file
pixi run python -m doc_build.iso_heading_case_lint specification/color/README.md

# Fix in-place
pixi run python -m doc_build.iso_heading_case_lint --fix specification/

# With a custom proper-nouns allowlist
pixi run python -m doc_build.iso_heading_case_lint --fix \
    --proper-nouns iso_heading_proper_nouns.yaml specification/
```

Proper nouns (OpenUSD, API, camelCase identifiers, etc.) are preserved
automatically.  Add domain terms to `iso_heading_proper_nouns.yaml` if
they are lowercased incorrectly.

## Bold table headers

ISO requires table column headings to be bold.

```sh
# Check
pixi run python -m doc_build.iso_bold_table_lint specification/

# Check a single file
pixi run python -m doc_build.iso_bold_table_lint specification/color/README.md

# Fix in-place
pixi run python -m doc_build.iso_bold_table_lint --fix specification/
```

Code spans in header cells (`` `value` ``) are left unwrapped.

## Clause structure

Checks that clauses with subclauses have no body text between the
heading and the first subclause.

```sh
pixi run python -m doc_build.iso_clause_lint specification/

# Single file
pixi run python -m doc_build.iso_clause_lint specification/composition/README.md
```

This linter has no auto-fix; violations require manual editing.

## DocBuilder subcommands

All linters are also available as subcommands of the doc builder:

```sh
pixi run python -m doc_build.doc_builder iso_lint_all
pixi run python -m doc_build.doc_builder iso_fix_all

pixi run python -m doc_build.doc_builder heading_case_lint
pixi run python -m doc_build.doc_builder heading_case_fix
pixi run python -m doc_build.doc_builder bold_table_lint
pixi run python -m doc_build.doc_builder bold_table_fix
pixi run python -m doc_build.doc_builder iso_clause_lint
```

## GitHub Actions

Add a lint job to your workflow file (`.github/workflows/*.yml`):

```yaml
  iso-lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: prefix-dev/setup-pixi@v0.8.9
        with:
          pixi-version: v0.59.0

      - name: ISO compliance checks
        run: pixi run python -m doc_build.doc_builder iso_lint_all
```

Or run the linters individually:

```yaml
      - name: ISO heading sentence case
        run: pixi run python -m doc_build.iso_heading_case_lint specification/

      - name: ISO bold table headers
        run: pixi run python -m doc_build.iso_bold_table_lint specification/

      - name: ISO clause structure
        run: pixi run python -m doc_build.iso_clause_lint specification/
```

Each linter exits with code 1 when violations are found, which fails the
CI step.
