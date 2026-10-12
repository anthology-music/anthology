"""Path restriction: every path must resolve (symlinks followed) below a configured root."""

from pathlib import Path

from tagger.errors import FORBIDDEN_PATH, NOT_FOUND, TaggerError


def resolve(path: str, roots: list[Path], *, must_exist: bool = True) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        raise TaggerError(FORBIDDEN_PATH, "path must be absolute")
    real = candidate.resolve(strict=False)
    if not any(real == root or real.is_relative_to(root) for root in roots):
        raise TaggerError(FORBIDDEN_PATH, "path outside the allowed roots")
    if must_exist and not real.is_file():
        raise TaggerError(NOT_FOUND, "file not found")
    return real
