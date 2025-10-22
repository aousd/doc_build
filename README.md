# AOUSD Shared Document Build

This repository includes shared document build code for all working groups at the Alliance for OpenUSD (AOUSD).

This is not meant for use outside the AOUSD, and no support is provided for other uses.

The repository uses the Apache 2.0 license, though dependencies might have their own licenses to be considered.


It combines multiple markdown files into a single document, and
typesets them using [Pandoc](https://pandoc.org) with the
 [Tectonic](https://tectonic-typesetting.github.io/en-US/) 
 PDF engine.

 The body text is set in *Georgia* sized at 10pt, with monospaced content in *Menlo* at 8pt.

## Setup

We recommend the following structure in your Git repo.

* `/specifications`: A folder to store your specification documents. It should contain a README.md that has links to documents that represent your individual sections.
* `/build_scripts`: A folder to store the build code needed.

We recommend using [pixi](https://pixi.sh/) to setup the Python environment necessary to build your doc with `pandoc`. You can use the following config file to setup your project:

**NOTE**: Make sure to use the latest commit from this repo and replace that in the rev below.

**pyproject.toml**
```toml
[project]
name = "my_spec"
version = "0.1.0"
description = "Build scripts for my WG spec"
requires-python = ">= 3.10"
dependencies = []

[tool.pixi.project]
channels = [ "conda-forge" ]
platforms = ["win-64", "linux-64", "osx-64", "osx-arm64"]
preview = ["pixi-build"]

[tool.pixi.dependencies]
# Update "rev" to the latest SHA1 on the doc_build repository
doc_build = { git = "ssh://git@github.com/aousd/doc_build.git", rev = "ec79f76f4df422a0ceba95311973f792a8d3c27d" }

[tool.pixi.tasks]
# Update this command if you use a different folder structure
main = "python build_scripts/build_docs.py"
```

Now create the following two files inside `/build_scripts`:

**defaults.yaml**
```yaml
metadata:
  title: "The Name of Your Document"
  author: [ "Your Authors" ]
  version: "0.0.0"
  keywords: [ Markdown, Example ]
```

**build_docs.py**
```python
#! /usr/bin/env python3
from doc_build import DocBuilder

class MyDocBuilder(DocBuilder):
    pass

if __name__ == "__main__":
    MyDocBuilder().process_argparser()
```

This provides you with a class that you can further customize to your specs needs.

If you choose a different project structure, you will need to override the `get_repo_root`
method on your class.

## Running Doc Builder

To run the doc builds, simply run `pixi run main <command>` with an appropriate sub command.

All subcommands have an optional `-o`/`--output` that can specify an output build directory. Otherwise, this is configured by the `AOUSD_BUILD` environment variable, or
will default to a folder called `build` in your repository root.

The following subcommands are available:

* `build`: Builds the documents.
    * `--no-html`: Turns of html generation
    * `--no-docx`: Turns off docx generation
    * `--no-pdf`: Turns off pdf generation
    * `--clean`: Runs the cleanup subcommand before running
    * `--only`/`--exclude`: Limits which sections get inlined during processing
    * `--no-draft`: Turns off the draft waterman on the PDF
* `clean`: Cleans any build artifacts.
* `lint`: Lints the build output for common issues.
* `export`: Exports the git archive to a zip for sharing.
* `todo`: Analyzes the build folder for TODOs and displays them.
* `index`: Analyzes the build folder and generates an index.
* `spellcheck`: Analyzes the build folder and displays misspelled words.
* `stylecheck`: Analyzes teh build folder and checks for common issues.

Only the `build` subcommand is routinely tested and supported. The others are convenience
methods and may or may not work.

### Dependencies

Dependencies are automatically installed by [pixi](https://pixi.sh), and should work on macOS/Linux/Windows.