#!/usr/bin/env python3

from pandocfilters import toJSONFilter, Para, Image, CodeBlock, get_caption

import io

from peg_to_peg import convert_peg_parsimonious_to_pegen
from gen_svg import convert_node, Nothing
import railroad as railroad

import tokenize
from pegen.tokenizer import Tokenizer
from pegen.grammar_parser import GeneratedParser as GrammarParser

counter = 0


def create_diagram(key, value, format, metadata):
    global counter
    if key == "CodeBlock":
        [[ident, classes, keyvals], code] = value

        if classes == ["peg"]:
            build_directory = metadata["AOUSD_BUILD"]["c"][0]["c"]
            part_name = metadata["PART"]["c"][0]["c"]

            old_peg = "".join(code.split("\n"))
            new_peg = convert_peg_parsimonious_to_pegen(old_peg)

            try:
                ss = list(tokenize.generate_tokens(io.StringIO(new_peg).readline))
            except:
                raise Exception(f"Rule not tokenizable after conversion: {new_peg}")

            tokenizer = Tokenizer(
                tokenize.generate_tokens(io.StringIO(new_peg).readline), verbose=False
            )
            parser = GrammarParser(tokenizer, verbose=False)
            grammar = parser.start()

            if not grammar:
                print("No grammar", repr(old_peg))
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
                    railroad.Diagram(rule.as_railroad()).writeStandalone(f.write)
                    f.close()

                    caption, typef, keyvals = get_caption(keyvals)
                    counter += 1

                    return [
                        CodeBlock([ident, classes, keyvals], code),
                        Para([Image([ident, [], keyvals], caption, [filename, typef])]),
                    ]


if __name__ == "__main__":
    toJSONFilter(create_diagram)
