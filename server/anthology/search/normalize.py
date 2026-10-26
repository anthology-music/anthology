"""Text folding shared by documents and queries (spec: search, Search as you type).

German umlauts are spelled out first, so "Müller", "Mueller" and "MÜLLER" fold to the same
word; other diacritics are dropped ("Dvořák" becomes "dvorak"). Everything that is not a
letter or a digit separates words.
"""

import re
import unicodedata

_GERMAN = str.maketrans(
    {"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue", "ß": "ss", "ẞ": "SS"}
)
_SEPARATORS = re.compile(r"[^0-9a-z]+")


def fold(text: str) -> str:
    """The folded words of ``text``, separated by single spaces."""
    decomposed = unicodedata.normalize("NFKD", text.translate(_GERMAN))
    stripped = "".join(char for char in decomposed if not unicodedata.combining(char))
    return _SEPARATORS.sub(" ", stripped.casefold()).strip()


def words(text: str) -> list[str]:
    folded = fold(text)
    return folded.split(" ") if folded else []
