#!/usr/bin/env python3
import copy
import sys

from pandocfilters import toJSONFilter, Para, Image, CodeBlock, get_caption

import io

from peg_to_peg import convert_standard_peg_to_pegen
from gen_svg import convert_node, Nothing, Container
import railroad as railroad

import tokenize
from pegen.tokenizer import Tokenizer
from pegen.grammar_parser import GeneratedParser as GrammarParser

counter = 0


LINE_BREAK_MARKER = "↵"

from railroad import Sequence, Stack, NonTerminal


def split_for_stack(container):
    # TODO support for both CHOICE and STACK in the same PEG

    if not LINE_BREAK_MARKER in str(container):
        return container

    if not hasattr(container, "items"):
        return container  # Not splittable, return as is

    stack_parts = []
    current_part = []

    for item in container.items:
        if isinstance(item, NonTerminal) and item.text == LINE_BREAK_MARKER:
            if current_part:
                stack_parts.append(Sequence(*current_part))
                current_part = []
        else:
            current_part.append(item)

    if current_part:
        stack_parts.append(Sequence(*current_part))

    if len(stack_parts) == 1:
        return stack_parts[0]
    else:
        return Stack(*stack_parts)


def create_diagram(key, value, format, metadata):
    global counter
    if key == "CodeBlock":
        [[ident, classes, keyvals], code] = value

        if classes == ["peg"]:
            build_directory = metadata["AOUSD_BUILD"]["c"][0]["c"]
            part_name = metadata["PART"]["c"][0]["c"]

            old_peg = "".join(code.split("\n"))
            # sys.stderr.write("Old:"+old_peg+"\n")
            new_peg = convert_standard_peg_to_pegen(old_peg)
            # sys.stderr.write("New:"+new_peg+"\n")

            try:
                ss = list(tokenize.generate_tokens(io.StringIO(new_peg).readline))
            except:
                raise Exception(f"Rule not tokenizable after conversion: {new_peg}")

            tokenizer = Tokenizer(tokenize.generate_tokens(io.StringIO(new_peg).readline), verbose=False)
            parser = GrammarParser(tokenizer, verbose=False)
            grammar = parser.start()

            if not grammar:
                # sys.stderr.write("No grammar:"+repr(new_peg))
                raise parser.make_syntax_error(io.StringIO(new_peg))

            for node in grammar:
                name = node.name
                if name.startswith("invalid_"):
                    continue
                rule = convert_node(node)
                while (new := rule.simplify()) != rule:
                    rule = new
                if not isinstance(rule, Nothing):
                    filename = f"{build_directory}/{part_name}_{counter}.svg"
                    f = open(filename, "w")
                    structured = split_for_stack(rule.as_railroad())
                    diagram = railroad.Diagram(structured)
                    diagram.writeStandalone(f.write)
                    f.close()

                    caption, typef, keyvals = get_caption(keyvals)
                    counter += 1

                    def pixels_to_points(pixels, dpi=96*1.2):  # scaling to fit better with the fonts; yes, the 96 here and 72 next line are there for scaling
                        return pixels * (72 / dpi)

                    w = pixels_to_points(float(diagram.attrs['width']))
                    h = pixels_to_points(float(diagram.attrs['height']))

                    width = f"{w}pt"
                    height = f"{h}pt"

                    # centimetres = w * 2.54 / 72
                    # if centimetres > 19:  # hardcoded maximum width, good for debugging; should be 16 for A4 and legal
                    #     sys.stderr.write(f"DIAGRAM OVERFLOW {centimetres}:{old_peg}\n")

                    keyvals_code = copy.deepcopy(keyvals)

                    keyvals.append(("width", width))
                    keyvals.append(("height", height))

                    return [
                        CodeBlock([ident, classes, keyvals_code], code),
                        Para([Image([ident, [], keyvals], caption, [filename, typef])]),
                    ]


if __name__ == "__main__":
    toJSONFilter(create_diagram)
