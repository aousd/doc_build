#!/usr/bin/env python3

"""Test the diff pipeline end-to-end using the diff test fixtures.

Creates a temporary git repository with two commits - one containing the
"before" fixture content and one containing the "after" fixture content -
then runs DocBuilder.build_docs() with --diff to exercise the full pipeline
(git worktrees, ast_diff, filter, pandoc) identically to real usage.

Outputs are written to tests/build/ using the diff_test-{1-before,2-after,3-diff}
naming. DocBuilder always produces Markdown output; HTML and PDF are optional.

Usage:
    python tests/build_scripts/build_diff.py [--html] [--pdf]

    With no format flags both HTML and PDF are built (plus Markdown always).
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import traceback
import types
from pathlib import Path

from doc_build.doc_builder import DocBuilder

TESTS_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = TESTS_ROOT / "diff_specification"
BUILD_DIR = TESTS_ROOT / "build"

# Fixed identity and timestamps so commit hashes are deterministic.
# GIT_CONFIG_NOSYSTEM + GIT_CONFIG_GLOBAL=/dev/null prevent any host
# git config (signing keys, defaultBranch, etc.) from leaking in.
_GIT_ENV = {
    **os.environ,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_AUTHOR_NAME": "Diff Test",
    "GIT_AUTHOR_EMAIL": "diff-test@example.com",
    "GIT_COMMITTER_NAME": "Diff Test",
    "GIT_COMMITTER_EMAIL": "diff-test@example.com",
}

_BEFORE_DATE = "2000-01-01T00:00:00+00:00"
_AFTER_DATE = "2000-01-02T00:00:00+00:00"


def _git(args: list[str], cwd: Path, env: dict | None = None) -> str:
    result = subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        env=env or _GIT_ENV,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed:\n{result.stderr.strip()}"
        )
    return result.stdout.strip()


def _setup_temp_repo(tmp: Path) -> tuple[str, str]:
    """Create a deterministic git repo with before and after commits.

    Returns (before_sha, after_sha). Commit hashes are stable as long as
    the fixture files and the fixed author/date constants are unchanged.
    """
    spec_dir = tmp / "specification"
    if spec_dir.exists():
        shutil.rmtree(spec_dir)

    _git(["init", "--initial-branch=main"], cwd=tmp)
    # Add a fake origin so get_file_base_name() derives "doc_build" from the remote URL,
    # matching the aousd_doc_build.* naming used in the copy/verify step below.
    _git(["remote", "add", "origin", "https://github.com/aousd/doc_build.git"], cwd=tmp)

    # Before commit - fixed author date so hash is deterministic
    shutil.copytree(FIXTURES_DIR / "before_commit", spec_dir)
    _git(["add", "."], cwd=tmp)
    _git(
        ["commit", "--no-gpg-sign", "-m", "before"],
        cwd=tmp,
        env={**_GIT_ENV, "GIT_AUTHOR_DATE": _BEFORE_DATE, "GIT_COMMITTER_DATE": _BEFORE_DATE},
    )
    before_sha = _git(["rev-parse", "HEAD"], cwd=tmp)

    # After commit - replace spec_dir contents with after_commit fixtures
    shutil.rmtree(spec_dir)
    shutil.copytree(FIXTURES_DIR / "after_commit", spec_dir)
    _git(["add", "."], cwd=tmp)
    # After commit - different fixed date
    _git(
        ["commit", "--no-gpg-sign", "-m", "after"],
        cwd=tmp,
        env={**_GIT_ENV, "GIT_AUTHOR_DATE": _AFTER_DATE, "GIT_COMMITTER_DATE": _AFTER_DATE},
    )
    after_sha = _git(["rev-parse", "HEAD"], cwd=tmp)

    return before_sha, after_sha


def build_diff(build_html: bool, build_pdf: bool) -> None:
    for path in (FIXTURES_DIR / "before_commit", FIXTURES_DIR / "after_commit"):
        if not path.is_dir():
            raise FileNotFoundError(f"Missing fixture directory: {path}")

    BUILD_DIR.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="doc_build_diff_test_") as tmp_str:
        tmp = Path(tmp_str)
        print("Setting up temporary git repo...")
        before_sha, after_sha = _setup_temp_repo(tmp)
        print(f"  before: {before_sha[:8]}  after: {after_sha[:8]}")

        diff_output = tmp / "build"
        diff_output.mkdir()

        builder = DocBuilder(repo_root=tmp)
        args = types.SimpleNamespace(
            diff=[before_sha, after_sha],
            output=diff_output,
            clean=False,
            no_md=False,
            no_html=not build_html,
            no_pdf=not build_pdf,
            no_docx=True,  # diff mode never emits DOCX
            no_draft=True,
            only=[],
            exclude=[],
        )

        print("Running DocBuilder.build_docs() with --diff...")
        builder.build_docs(args)

        # md is always built; html and pdf are optional
        num_expected = 1 + int(build_html) + int(build_pdf)

        # Copy outputs to tests/build/ with diff_test-* naming
        for subdir_name in ("diff_from", "diff_to", "diff"):
            source_subdir = diff_output / subdir_name
            dest_subdir = BUILD_DIR / subdir_name
            dest_subdir.mkdir(parents=True, exist_ok=True)

            glob_pattern = "aousd_doc_build.*"
            files = sorted(source_subdir.glob(glob_pattern))

            if len(files) != num_expected:
                raise RuntimeError(f"Expected {num_expected} files for {glob_pattern}, got {len(files)}: {files}")
            for source in files:
                destination = dest_subdir / source.name
                shutil.copy(source, destination)
                print(f"  Written: {destination}")
            images_src_dir = source_subdir / "images"
            if images_src_dir.is_dir():
                images_dst_dir = dest_subdir / "images"
                print(f"  Copying images from {images_src_dir} to {images_dst_dir}")
                shutil.copytree(images_src_dir, images_dst_dir, dirs_exist_ok=True)


###############################################################################
# CLI
###############################################################################


def get_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--html", action="store_true", help="Build HTML output")
    parser.add_argument("--pdf", action="store_true", help="Build PDF output")
    return parser


def main(argv=None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    parser = get_parser()
    args = parser.parse_args(argv)

    any_specified = args.html or args.pdf
    build_html = args.html or not any_specified
    build_pdf = args.pdf or not any_specified

    try:
        build_diff(build_html, build_pdf)
    except Exception:
        traceback.print_exc()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
