"""Utility functions for querying git metadata."""

import contextlib
import re
import subprocess
import time
from collections.abc import Generator
from pathlib import Path
from typing import Optional

_SEMVER_TAG_PATTERN = re.compile(r"^v\d+\.\d+\.\d+$")


def commit_hash(ref: str, repo_root: Path, *, short: bool = False) -> str:
    """Resolve a git ref (branch, tag, hash) to a commit hash in the repo."""
    args = ["git", "rev-parse", "--short", ref] if short else ["git", "rev-parse", ref]
    return subprocess.check_output(args, cwd=repo_root).decode("utf-8").strip()


def get_latest_tag(
    repo_root: Path,
    commit: str = "HEAD",
    glob: Optional[str] = None,
    pattern: Optional[re.Pattern] = None,
) -> Optional[str]:
    """Return the most recent tag reachable from commit, or None.

    glob:    shell glob passed to `git tag --list` to pre-filter tags
    pattern: compiled regexp used to filter results after git returns them
    """
    cmd = ["git", "tag", "--list", "--sort=-version:refname", f"--merged={commit}"]
    if glob is not None:
        cmd.append(glob)
    tag_output = subprocess.check_output(cmd, cwd=repo_root).decode("utf-8")
    return next(
        (
            line.strip()
            for line in tag_output.splitlines()
            if pattern is None or pattern.match(line.strip())
        ),
        None,
    )


def get_latest_semver_tag(repo_root: Path, commit: str = "HEAD") -> Optional[str]:
    """Return the most recent vX.Y.Z tag reachable from commit, or None."""
    return get_latest_tag(
        repo_root, commit, glob="v*.*.*", pattern=_SEMVER_TAG_PATTERN
    )


def repo_root(cwd: Path) -> Path:
    """Return the root of the git repo containing cwd."""
    return Path(
        subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"], cwd=cwd
        )
        .decode("utf-8")
        .strip()
    )


def get_remote_url(repo_root: Path, remote: str = "origin") -> Optional[str]:
    """Return the fetch URL of the given remote, or None if not set."""
    try:
        output = subprocess.check_output(
            ["git", "remote", "get-url", remote], cwd=repo_root
        ).decode("utf-8").strip()
        return output or None
    except subprocess.CalledProcessError:
        return None


@contextlib.contextmanager
def temp_worktree(
    repo_root: Path, ref: str, worktree_path: Path
) -> Generator[None, None, None]:
    """Context manager that adds a git worktree at worktree_path for ref, then removes it."""
    subprocess.check_call(
        ["git", "worktree", "add", str(worktree_path), ref], cwd=repo_root
    )
    try:
        yield
    finally:
        try:
            subprocess.check_call(
                ["git", "worktree", "remove", str(worktree_path)], cwd=repo_root
            )
        except subprocess.CalledProcessError:
            pass


def export_git_archive(base_filename: str, branch: str, output: Path) -> Path:
    """Export a git archive zip for branch into output, returning the filepath."""
    timestr = time.strftime("%Y%m%d-%H%M%S")
    filename = f"{base_filename}_{branch}_{timestr}.zip"
    filepath = output / filename
    print(f"Exporting archive to {filepath}...")
    subprocess.check_call(
        ["git", "archive", "--format", "zip", "--output", str(filepath), branch]
    )
    return filepath
