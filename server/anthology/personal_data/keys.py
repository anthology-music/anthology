"""Fractional position keys (design of change personal-data, Ordering with fractional keys).

A key is a fraction in base 62 written without the leading "0." and without trailing zeros;
the digits are ``0-9A-Za-z``, whose ASCII order is their value, so keys sort as plain strings
(byte order: the column uses the "C" collation on PostgreSQL). A key between two others never
changes them, so concurrent inserts at the same place both succeed; equal keys are ordered by
entry ID.
"""

DIGITS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
BASE = len(DIGITS)
# Keys longer than this make the playlist rebalance its keys.
MAX_LENGTH = 32


def _value(digit: str) -> int:
    return DIGITS.index(digit)


def between(a: str | None, b: str | None) -> str:
    """A key strictly between ``a`` and ``b`` (None: the start or the end)."""
    low = a or ""
    if b is not None and low >= b:
        raise ValueError(f"{a!r} is not before {b!r}")
    if low.endswith("0") or (b is not None and b.endswith("0")):
        raise ValueError("keys have no trailing zeros")
    return _midpoint(low, b)


def _midpoint(a: str, b: str | None) -> str:
    if b is not None:
        # The common prefix stays; the midpoint is found in the digits after it.
        n = 0
        while n < len(b) and (a[n] if n < len(a) else "0") == b[n]:
            n += 1
        if n > 0:
            return b[:n] + _midpoint(a[n:], b[n:])
    low = _value(a[0]) if a else 0
    high = _value(b[0]) if b else BASE
    if high - low > 1:
        return DIGITS[(low + high) // 2]
    if b is not None and len(b) > 1:
        return b[0]
    return DIGITS[low] + _midpoint(a[1:], None)


def spread(a: str | None, b: str | None, count: int) -> list[str]:
    """``count`` ascending keys between ``a`` and ``b``, spread evenly (short keys)."""
    if count <= 0:
        return []
    middle = between(a, b)
    left = count // 2
    return [*spread(a, middle, left), middle, *spread(middle, b, count - left - 1)]
