#!/usr/bin/env python3
"""Pandoc filter that injects a SHA-256 content hash into each Image AST node.

The hash is stored under the key ``data-image-hash`` in the image node's
attribute key-value list (c[0][2]).  Relative image paths are resolved against
AOUSD_ARTIFACTS_DIR metadata (the artifacts directory).  If the metadata is not
present, paths are resolved against the current working directory.

When pandoc later diffs before/after AST files, a hash change causes the image
node to be treated as a substitution even if the filename is identical, enabling
binary-level image change detection.
"""

import hashlib
from pathlib import Path

from pandocfilters import toJSONFilter, Image
from shared_filter_utils import get_metadata_str

HASH_ATTR_KEY = "data-image-hash"


def _sha256(path: Path) -> str:
    """Return the hex-encoded SHA-256 digest of the file at path."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def inject_image_hash(key, value, _format, meta):
    if key != "Image":
        return

    attr, caption, target = value
    image_path = target[0]

    try:
        artifacts_dir = Path(get_metadata_str(meta, "AOUSD_ARTIFACTS_DIR"))
    except KeyError:
        artifacts_dir = Path.cwd()

    src = Path(image_path)
    if not src.is_absolute():
        src = artifacts_dir / src

    if not src.exists():
        # Skip images that cannot be found (e.g. generated at a later stage).
        return

    digest = _sha256(src)

    id_, classes, kv_pairs = attr
    # Remove any existing hash entry, then append the fresh one.
    new_kv = [(k, v) for k, v in kv_pairs if k != HASH_ATTR_KEY]
    new_kv.append((HASH_ATTR_KEY, digest))
    new_attr = [id_, classes, new_kv]

    return Image(new_attr, caption, target)


if __name__ == "__main__":
    toJSONFilter(inject_image_hash)
