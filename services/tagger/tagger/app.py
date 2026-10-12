"""HTTP interface v1 (docs/architecture/tagger-api.md)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from tagger import INTERFACE_VERSION, __version__
from tagger.config import Settings
from tagger.errors import TaggerError
from tagger.models import (
    CopyRequest,
    Health,
    ReadRequest,
    ReadResponse,
    WriteRequest,
    WriteResponse,
)
from tagger.service import Tagger
from tagger.tags import FORMATS


def create_app(settings: Settings | None = None) -> FastAPI:
    tagger = Tagger(settings or Settings())

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        tagger.recover()
        yield

    app = FastAPI(title="Anthology tagger", version=__version__, lifespan=lifespan)
    app.state.tagger = tagger

    @app.exception_handler(TaggerError)
    async def request_error(_: Request, error: TaggerError) -> JSONResponse:
        # Errors of the request as a whole (e.g. a forbidden extraction directory).
        return JSONResponse({"detail": error.code, "message": error.message}, status_code=400)

    def check_batch(size: int) -> None:
        if size > tagger.settings.max_batch:
            raise HTTPException(413, "batch_too_large")

    # Synchronous handlers: mutagen does blocking file I/O; FastAPI runs them in a thread pool.

    @app.get("/v1/health", response_model=Health)
    def health() -> Health:
        return Health(version=__version__, interface=INTERFACE_VERSION, formats=FORMATS)

    @app.post("/v1/tags/read", response_model=ReadResponse, response_model_exclude_none=True)
    def read(request: ReadRequest) -> ReadResponse:
        check_batch(len(request.paths))
        return ReadResponse(results=tagger.read(request))

    @app.post("/v1/tags/write", response_model=WriteResponse, response_model_exclude_none=True)
    def write(request: WriteRequest) -> WriteResponse:
        check_batch(len(request.files))
        return WriteResponse(results=tagger.write(request))

    @app.post("/v1/tags/copy", response_model=WriteResponse, response_model_exclude_none=True)
    def copy(request: CopyRequest) -> WriteResponse:
        check_batch(len(request.files))
        return WriteResponse(results=tagger.copy(request))

    return app
