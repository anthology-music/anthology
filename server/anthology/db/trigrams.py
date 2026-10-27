"""Trigram similarity as PostgreSQL's pg_trgm computes it, registered as the SQL function
``similarity`` on SQLite so that queries using it run on both engines."""


def trigrams(word: str) -> set[str]:
    """Trigrams of one word, padded like pg_trgm (two spaces before, one after)."""
    padded = f"  {word} "
    return {padded[index : index + 3] for index in range(len(padded) - 2)}


def similarity(left: str | None, right: str | None) -> float:
    """Shared trigrams over all trigrams of two words (0 to 1)."""
    if not left or not right:
        return 0.0
    a, b = trigrams(left), trigrams(right)
    return len(a & b) / len(a | b)
