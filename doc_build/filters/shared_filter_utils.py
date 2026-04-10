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