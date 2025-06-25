from __future__ import print_function
import re
import sys

from Cocoa import NSSpellChecker, NSString, NSRange

# List of common UK → US spelling patterns
SPELLING_PATTERNS = [
    (r'ise$', r'ize$'),
    (r'ises$', r'izes$'),
    (r'ised$', r'ized$'),
    (r'ising$', r'izing$'),

    (r'isation$', r'ization$'),
    (r'isations$', r'izations$'),

    (r'izability$', r'isability$'),
    (r'izable$', r'isable$'),
    (r'izables$', r'isables$'),

    (r'fulfil$', r'fulfill$'),
    (r'fulfilment$', r'fulfillment$'),

    (r'artefact$', r'artifact$'),
    (r'artefacts$', r'artifacts$'),

    (r'our$', r'or$'),
    (r'ours$', r'ors$'),

    (r're$', r'er$'),
    (r'res$', r'ers$'),

    (r'ogue$', r'og$'),
    (r'ogues$', r'ogs$'),

    (r'lled$', r'led$'),
    (r'lling$', r'ling$'),

    (r'ce$', r'se$'),
    (r'ces$', r'ses$'),
]


def generate_variants(word):
    """Generate possible UK/US variants of a word."""
    word = word.lower()
    variants = {word}
    for uk_pattern, us_pattern in SPELLING_PATTERNS:
        if re.search(uk_pattern, word):
            variants.add(re.sub(uk_pattern, us_pattern[0:-1], word))  # Remove trailing $ for replacement
        if re.search(us_pattern, word):
            variants.add(re.sub(us_pattern, uk_pattern[0:-1], word))
    return variants


def compare_us_uk_words(word1, words):
    if not words:
        return False

    word2 = words[0]

    word1 = word1.lower()
    word2 = word2.lower()

    if word1 == word2:
        return True

    variants1 = generate_variants(word1)
    variants2 = generate_variants(word2)

    if variants1 & variants2:
        return True

    return False


def is_valid_url(word):
    pattern = r'^[\w\-\.]+(\.com|\.net|\.gov|\.edu)$'
    return re.match(pattern, word.lower()) is not None


def check_spelling(checker, string, start=0):
    _range, _count = (
        checker.checkSpellingOfString_startingAt_language_wrap_inSpellDocumentWithTag_wordCount_(
            NSString.stringWithString_(string), start, None, False, 0, None
        )
    )
    if _range.length == 0:
        return True, _count, None, None
    else:
        return (
            False,
            _count,
            _range,
            string[_range.location : _range.location + _range.length],
        )


def guesses(checker, string, _range):
    _words = checker.guessesForWordRange_inString_language_inSpellDocumentWithTag_(
        _range, NSString.stringWithString_(string), None, 0
    )

    return string, _words


def wrapper(term):
    ok, _count, _range, word = check_spelling(NSSpellChecker.sharedSpellChecker(), term)
    if not ok:
        orig, suggestions = guesses(NSSpellChecker.sharedSpellChecker(), word, _range)
        if not compare_us_uk_words(orig, suggestions):
            if not is_valid_url(orig):
                sys.stderr.write(
                    f'Misspelled word: {orig}\t\tGuesses: {", ".join(suggestions) if suggestions else "?"}\n'
                )


if __name__ == "__main__":
    for line in sys.stdin:
        words = line.split()
        for term in words:
            ok, _count, _range, word = check_spelling(
                NSSpellChecker.sharedSpellChecker(), term
            )
            if not ok:
                guesses(NSSpellChecker.sharedSpellChecker(), word, _range)
