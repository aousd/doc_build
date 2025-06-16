import re
import sys


def convert_standard_peg_to_pegen(standard_peg: str) -> str:

    rule_pattern = re.compile(r"([\w<>]+)\s*<-\s*(.+)")
    unicode_pattern = re.compile(r"\\u[0-9A-Fa-f]{4}|\\U[0-9A-Fa-f]{8}")
    unicode_u_plus_pattern = re.compile(r"U\+([0-9A-Fa-f]{4,8})")
    char_class_pattern = re.compile(r"\[([^\]]+)\]")     # Character class brackets

    def convert_u_plus_to_unicode_symbol(match):
        codepoint = match.group(1)
        return f"U➕{codepoint.zfill(4)}" if len(codepoint) <= 4 else f"U➕{codepoint.zfill(8)}"

    def normalize_literal(match):
        literal = match.group(1) if match.group(1) is not None else match.group(2)
        return f'"{literal}"'

    def replace_brackets(text):
        # Convert [] to ⟦ ⟧ and <> to ⟨ ⟩
        text = text.replace("[", "⟦").replace("]", "⟧")
        text = text.replace("<", "⟨").replace(">", "⟩")
        return text

    # Replace character class brackets and internal symbols
    def replace_char_class(match):
        content = match.group(1).strip()
        content = content.replace("U+", "U➕")
        content = content.replace("+", "➕")
        content = content.replace("-", "−")
        return f"⟦{content}⟧"

    lines = standard_peg.splitlines()
    pegen_lines = []

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            pegen_lines.append(line)
            continue

        rule_match = rule_pattern.match(line)
        if rule_match:
            rule_name, rule_body = rule_match.groups()

            rule_body = char_class_pattern.sub(replace_char_class, rule_body)

            # protect some letters by replacing them with Unicode equivalents
            rule_body = rule_body.replace("'/'", "'∕'")
            rule_body = rule_body.replace("'\\'", "'＼'")
            rule_body = rule_body.replace("'", "＇")
            rule_body = rule_body.replace('"', '＂')

            # Unicode and literal normalization
            rule_body = unicode_u_plus_pattern.sub(convert_u_plus_to_unicode_symbol, rule_body)
            rule_body = unicode_pattern.sub(lambda match: match.group(0), rule_body)

            # PEG-specific features
            rule_body = rule_body.replace("/", "| ")

            # Replace disallowed brackets with visual Unicode lookalikes
            rule_body = replace_brackets(rule_body)
            rule_body = re.sub(r" +", " ", rule_body)

            pegen_lines.append(f"{replace_brackets(rule_name)}: {rule_body}")
        else:
            # Also replace in comments or unmatched lines
            pegen_lines.append(replace_brackets(line))

    return "\n".join(pegen_lines)
