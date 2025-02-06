import re
import sys


def convert_peg_parsimonious_to_pegen(parsimonious_peg: str) -> str:
    # Define regex patterns for rule declarations, string literals, and unicode escape sequences.
    rule_pattern = re.compile(r"([\w<>]+)\s*=\s*(.+)")  # Matches 'rule = ...'
    literal_pattern = re.compile(
        r"'([^']*)'"
    )  # Matches single-quoted string literals in Parsimonious
    unicode_pattern = re.compile(
        r"\\u[0-9A-Fa-f]{4}|\\U[0-9A-Fa-f]{8}"
    )  # Matches unicode escapes
    unicode_u_plus_pattern = re.compile(
        r"U\+([0-9A-Fa-f]{4,8})"
    )  # Matches U+XXXX or U+XXXXXXXX

    # Function to convert U+XXXX to \uXXXX or \UXXXXXXXX
    def convert_u_plus_to_escape(match):
        codepoint = match.group(1)
        # Use \u for 4-digit codepoints, \U for longer ones
        if len(codepoint) <= 4:
            return f"\\u{codepoint.zfill(4)}"
        else:
            return f"\\U{codepoint.zfill(8)}"

    # Split the input by lines to process each rule
    lines = parsimonious_peg.splitlines()
    pegen_lines = []

    for line in lines:
        # Ignore empty lines or comments
        line = line.strip()
        if not line or line.startswith("#"):
            pegen_lines.append(line)
            continue

        # Convert rule declarations from '=' to ':'
        rule_match = rule_pattern.match(line)
        if rule_match:
            rule_name, rule_body = rule_match.groups()

            # print("?", rule_name, rule_body)

            rule_body = rule_body.replace("**", '"')

            # replace <> with {} to allow processing for the railroad images
            rule_name = rule_name.replace("<", "_")
            rule_name = rule_name.replace(">", "_")

            rule_body = rule_body.replace("<", "_")
            rule_body = rule_body.replace(">", "_")

            # Replace '/' with '|'
            rule_body = rule_body.replace("/", "| ")

            # Convert the single-quoted literals to double-quoted literals
            rule_body = literal_pattern.sub(r'"\1"', rule_body)

            # Convert U+XXXX format to \uXXXX or \UXXXXXXXX
            rule_body = unicode_u_plus_pattern.sub(convert_u_plus_to_escape, rule_body)

            # Ensure that Unicode escape sequences are preserved
            rule_body = unicode_pattern.sub(lambda match: match.group(0), rule_body)

            # Convert the rule to pegen style: 'rule: ...'
            pegen_lines.append(f"{rule_name}: {rule_body}")
        else:
            # For any line that doesn't match, preserve it as is.
            pegen_lines.append(line)

    # Join the converted lines back into a single string
    # sys.stderr.write("\n".join(pegen_lines)+"\n")
    return "\n".join(pegen_lines)


if __name__ == "__main__":
    parsimonious_peg = """
    # This is a comment with a Unicode literal
    rule1 = 'a' / '\\u00F1' / '\\U0001F600'
    rule2 = rule1 / 'ñ' / 'ü'
    """

    pegen_peg = convert_peg_parsimonious_to_pegen(parsimonious_peg)
    print(pegen_peg)
