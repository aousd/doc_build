from __future__ import print_function
import sys

from Cocoa import NSSpellChecker, NSString, NSRange


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
    sys.stderr.write(
        f'Misspelled word: {string} Guesses: {", ".join(_words) if _words else "?"}\n'
    )


def wrapper(term):
    ok, _count, _range, word = check_spelling(NSSpellChecker.sharedSpellChecker(), term)
    if not ok:
        guesses(NSSpellChecker.sharedSpellChecker(), word, _range)


if __name__ == "__main__":
    for line in sys.stdin:
        words = line.split()
        for term in words:
            ok, _count, _range, word = check_spelling(
                NSSpellChecker.sharedSpellChecker(), term
            )
            if not ok:
                guesses(NSSpellChecker.sharedSpellChecker(), word, _range)
