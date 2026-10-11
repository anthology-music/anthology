"""Print the OpenAPI document without starting the app: ``python -m anthology.api.openapi``."""

import json
from typing import Any

from anthology.api.app import create_app
from anthology.core.config import Settings


def openapi_document() -> dict[str, Any]:
    return create_app(Settings()).openapi()


if __name__ == "__main__":
    print(json.dumps(openapi_document(), indent=2, sort_keys=True))
