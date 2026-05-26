#!/usr/bin/env python
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///

"""Check out a specific commit in a worktree, build the diff PDF, and copy
it to a shared output directory under a label.

Designed to be run inside a worktree-isolated subagent.  The subagent
must pass its own worktree root as ``--repo-root``; do NOT hardcode the
main repo path.

Filename of the resulting PDF embeds the temp-repo before/after commit
hashes.  Two builds with the same fixture content will produce the same
filename - that is a useful diagnostic for "did my fixture writes
actually take effect?"
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def run(cmd, cwd):
    print(f"+ {' '.join(str(c) for c in cmd)} (cwd={cwd})", flush=True)
    subprocess.check_call(cmd, cwd=cwd)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--repo-root", required=True, type=Path,
        help="Absolute path to the worktree root (the subagent's own worktree)",
    )
    parser.add_argument(
        "--commit", required=True,
        help="Target commit hash to checkout (use a hash, not a branch name)",
    )
    parser.add_argument(
        "--label", required=True,
        help="Label used to prefix the output PDF filename (e.g. 'before' or 'after')",
    )
    parser.add_argument(
        "--out-dir", required=True, type=Path,
        help="Shared output directory (outside the worktree) for the labeled PDF",
    )
    parser.add_argument(
        "--build-cmd", default="pixi run build-diff --pdf",
        help="Shell-tokenized build command run inside the worktree",
    )
    parser.add_argument(
        "--build-output-dir", default="tests/build/diff",
        help="Path (relative to repo root) where the built PDF lands",
    )
    parser.add_argument(
        "--build-output-glob", default="aousd_doc_build.diff_*.pdf",
        help="Glob (within --build-output-dir) matching exactly the built PDF",
    )
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve()
    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    if not (repo_root / ".git").exists():
        raise SystemExit(f"--repo-root does not look like a git worktree: {repo_root}")

    print(f"Working in worktree: {repo_root}", flush=True)
    print(f"Target commit: {args.commit}", flush=True)
    print(f"Label: {args.label}", flush=True)
    print(f"Output dir: {out_dir}", flush=True)

    run(["git", "checkout", "--detach", args.commit, "--"], repo_root)
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo_root,
    ).decode().strip()
    if not head.startswith(args.commit):
        raise SystemExit(
            f"HEAD {head} does not match requested commit {args.commit}"
        )
    print(f"HEAD now at {head}", flush=True)

    build_dir = repo_root / args.build_output_dir
    if build_dir.exists():
        for old in build_dir.glob(args.build_output_glob):
            print(f"Removing stale PDF: {old}", flush=True)
            old.unlink()

    run(args.build_cmd.split(), repo_root)

    pdfs = list(build_dir.glob(args.build_output_glob))
    if len(pdfs) != 1:
        raise SystemExit(f"Expected exactly 1 diff PDF, found {len(pdfs)}: {pdfs}")
    pdf = pdfs[0]
    dest = out_dir / f"{args.label}__{pdf.name}"
    shutil.copy2(pdf, dest)
    print(f"Copied PDF -> {dest}", flush=True)
    print(f"DONE label={args.label} commit={args.commit} dest={dest}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
