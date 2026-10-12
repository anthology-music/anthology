"""Run the tagger: python -m tagger."""

import uvicorn

from tagger.app import create_app
from tagger.config import Settings


def main() -> None:
    settings = Settings()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
