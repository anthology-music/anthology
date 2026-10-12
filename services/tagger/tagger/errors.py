"""Per-file error codes of the interface (docs/architecture/tagger-api.md)."""


class TaggerError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code
        self.message = message or code


NOT_FOUND = "not_found"
FORBIDDEN_PATH = "forbidden_path"
UNSUPPORTED_FORMAT = "unsupported_format"
CORRUPT = "corrupt"
HARDLINKED = "hardlinked"
INVALID_IMAGE = "invalid_image"
WRITE_FAILED = "write_failed"
