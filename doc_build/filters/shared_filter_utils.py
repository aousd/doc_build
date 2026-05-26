from pathlib import Path

HASH_ATTR_KEY = "data-image-hash"


def get_image_rel(src_abs: Path, images_root: Path) -> Path:
    """Compute destination relative path under images/, stripping 'images' components.

    Strips any path components named 'images' or '..' from the path relative to
    images_root.  Used by image-bundling and diff-image filters to determine the
    destination path when copying images to an output images directory.
    """
    rel = src_abs.relative_to(images_root, walk_up=True)
    parts = [p for p in rel.parts if p not in ("images", "..")]
    if not parts:
        raise ValueError(
            f"Image {src_abs} reduces to an empty path after removing"
            f" 'images' and '..' components"
        )
    return Path(*parts)


def get_metadata_str(metadata: dict, key: str) -> str:
    """Extract a string value from pandoc filter metadata.

    Handles both MetaString (produced by -M on the command line) and
    MetaInlines (produced by --metadata-file YAML).
    """
    try:
        entry = metadata[key]
        if entry.get("t") == "MetaString":
            return entry["c"]
        return entry["c"][0]["c"]
    except (KeyError, IndexError, TypeError) as e:
        raise KeyError(f"Missing or malformed metadata key {key!r}: {e}") from e
