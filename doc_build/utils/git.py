"""Utility functions for querying git metadata."""

import collections.abc
import contextlib
import re
import subprocess
import time
from collections.abc import Generator
from pathlib import Path
from typing import Optional

_HEX_HASH_PATTERN = re.compile(r"^[0-9a-f]+$", re.IGNORECASE)
_SEMVER_TAG_PATTERN = re.compile(r"^v\d+\.\d+\.\d+$")


def get_tag_timestamps(
    repo_root: Path,
    tags: str | collections.abc.Iterable[str] | None = None,
) -> dict[str, int]:
    """Return a {tag_name: unix_timestamp} dict for tags in the repo.

    tags: a single tag name, an iterable of tag names, or None to fetch all tags.
    """
    if tags is None:
        refs = ["refs/tags/"]
    elif isinstance(tags, str):
        refs = [f"refs/tags/{tags}"]
    else:
        refs = [f"refs/tags/{t}" for t in tags]
        if not refs:
            return {}
    timestamps_output = (
        subprocess.check_output(
            ["git", "for-each-ref", "--format=%(creatordate:unix) %(refname:short)"] + refs,
            cwd=repo_root,
        )
        .decode("utf-8")
        .strip()
    )
    tag_ts: dict[str, int] = {}
    for line in timestamps_output.splitlines():
        parts = line.split(" ", 1)
        if len(parts) == 2:
            try:
                tag_ts[parts[1]] = int(parts[0])
            except ValueError:
                pass
    return tag_ts


def tag_sort_key(
    tag: str,
    *,
    tag_timestamp: dict[str, int] | str | None = None,
    repo_root: Path | None = None,
) -> tuple:
    """Return a sort key for a tag.

    Sorts semver tags first (0), then by timestamp ascending (older first),
    then by length, then alphabetically.

    tag_timestamp: a dict mapping tag names to unix timestamps, a single unix
                   timestamp as a str, or None. If None and repo_root is
                   provided, the timestamp is looked up automatically via
                   get_tag_timestamps. If None and no repo_root, raises
                   ValueError. Raises KeyError if a dict is provided but does
                   not contain the tag. Raises ValueError if auto-lookup via
                   repo_root finds no timestamp for the tag.
    """
    if isinstance(tag_timestamp, dict):
        if tag not in tag_timestamp:
            raise KeyError(f"tag {tag!r} not found in tag_timestamp dict")
        ts = tag_timestamp[tag]
    elif isinstance(tag_timestamp, str):
        ts = int(tag_timestamp)
    elif repo_root is not None:
        result = get_tag_timestamps(repo_root, tag)
        if tag not in result:
            raise ValueError(f"no timestamp found for tag {tag!r} in repo {repo_root}")
        ts = result[tag]
    else:
        raise ValueError(
            f"cannot determine timestamp for tag {tag!r}: "
            "provide tag_timestamp or repo_root"
        )
    is_semver = 0 if _SEMVER_TAG_PATTERN.match(tag) else 1
    return (is_semver, ts, len(tag), tag)


def sort_tags(tags: list[str], repo_root: Path) -> list[str]:
    """Return tags sorted by tag_sort_key.

    Fetches tag timestamps from git for-each-ref, then sorts.
    """
    tag_ts = get_tag_timestamps(repo_root)
    return sorted(tags, key=lambda t: tag_sort_key(t, tag_timestamp=tag_ts))


def _remote_tier(branch: str) -> int:
    """Return a sort tier for a branch based on its remote.

    origin remote = 0, other remotes = 1, local = 2.
    """
    if branch.startswith("remotes/origin/"):
        return 0
    if branch.startswith("remotes/"):
        return 1
    return 2


def _display_name(branch: str) -> str:
    """Return a human-readable display name for a branch ref."""
    if branch.startswith("remotes/"):
        parts = branch.split("/", 2)
        return parts[1] + "/" + parts[2] if len(parts) == 3 else branch
    return branch


def branch_sort_key(branch: str) -> tuple:
    """Return a sort key for a branch.

    Sorts by remote tier (origin=0, other remotes=1, local=2), then by
    display name length, then alphabetically.
    """
    name = _display_name(branch)
    return (_remote_tier(branch), len(name), name)


def sort_branches(branches: list[str]) -> list[str]:
    """Return branches sorted by branch_sort_key."""
    return sorted(branches, key=branch_sort_key)


def get_ref_symbolic_name(ref: str, repo_root: Path) -> Optional[str]:
    """Return a symbolic name for ref, or None if ref is a bare hash.

    If ref is not a hex string, return it directly.  Otherwise, look for
    tags pointing exactly to that commit (preferring semver, then older,
    then shorter, then alphabetical), then branches (preferring origin
    remote, then other remotes, then local; shorter/alphabetical within
    each tier).  Returns None if nothing is found.
    """
    if not _HEX_HASH_PATTERN.match(ref):
        return ref

    full_hash = (
        subprocess.check_output(["git", "rev-parse", ref], cwd=repo_root)
        .decode("utf-8")
        .strip()
    )

    tags_output = (
        subprocess.check_output(["git", "tag", "--points-at", full_hash], cwd=repo_root)
        .decode("utf-8")
        .strip()
    )
    if tags_output:
        tags = tags_output.splitlines()
        return sort_tags(tags, repo_root)[0]

    branches_output = (
        subprocess.check_output(
            ["git", "branch", "-a", "--points-at", full_hash], cwd=repo_root
        )
        .decode("utf-8")
        .strip()
    )
    if branches_output:
        branches = [b.strip().lstrip("* ") for b in branches_output.splitlines()]
        return _display_name(sort_branches(branches)[0])

    return None


def commit_hash(ref: str, repo_root: Path, *, short: bool = False) -> str:
    """Resolve a git ref (branch, tag, hash) to a commit hash in the repo."""
    args = ["git", "rev-parse", "--short", ref] if short else ["git", "rev-parse", ref]
    return subprocess.check_output(args, cwd=repo_root).decode("utf-8").strip()


def get_ref_pretty_str(ref: str, repo_root: Path) -> str:
    """Return '<symbolic-name> (<short-hash>)' or '(<short-hash>)' for ref."""
    short_hash = (
        subprocess.check_output(["git", "rev-parse", "--short", ref], cwd=repo_root)
        .decode("utf-8")
        .strip()
    )
    symbolic = get_ref_symbolic_name(ref, repo_root)
    if symbolic:
        return f"{symbolic} ({short_hash})"
    return f"({short_hash})"


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
