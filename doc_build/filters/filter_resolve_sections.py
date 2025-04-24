#!/usr/bin/env python3
import os
from pandocfilters import toJSONFilter, Link


def get_spec_doc_roots():
    found = {}
    specification_root = os.getcwd()
    for root, _, files in os.walk(specification_root):
        for f in files:
            if not f.endswith(".md"):
                continue
            path = os.path.join(root, f)

            with open(path, "r", encoding="utf-8") as md:
                for line in md.readlines():
                    line = line.strip()
                    if line.startswith("#"):
                        section = line
                        break

                else:
                    continue

            name = "-".join([t.lower() for t in section.split() if t.isalnum()])
            found[path] = f"#{name}"

    return found


SPEC_DOC_ROOTS = get_spec_doc_roots()


def resolve_sections(key, value, _format, _metadata):
    if key != "Link":
        return

    link = value[2][0]
    if link.startswith(("http://", "https://", "#")):
        return

    tokens = link.split("#")

    if len(tokens) == 2:
        value[2][0] = f"#{tokens[1]}"
    elif len(tokens) == 1:
        link = tokens[0].replace("../", "")
        paths = [k for k in SPEC_DOC_ROOTS if k.endswith(link)]
        if paths:
            path = paths[0]
            value[2][0] = SPEC_DOC_ROOTS[path]
    else:
        return

    return Link(value[0], value[1], value[2])


if __name__ == "__main__":
    toJSONFilter(resolve_sections)
