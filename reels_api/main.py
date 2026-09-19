import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from reels_api import web
from reels_api.jobs import JobManager, JobStore
from reels_api.models import ErrorCode, JobError
from reels_api.pipeline import Pipeline
from reels_api.routes import router
from reels_api.settings import Settings

_JOB_ERROR_STATUS = {
    ErrorCode.UNSUPPORTED_URL: 400,
    ErrorCode.TOO_MANY_JOBS: 429,
}


def create_app(settings: Settings | None = None, pipeline: Pipeline | None = None) -> FastAPI:
    settings = settings or Settings()
    logging.basicConfig(level=settings.log_level.upper())
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    settings.temp_dir.mkdir(parents=True, exist_ok=True)

    store = JobStore()
    manager = JobManager(settings, pipeline or Pipeline(settings=settings), store)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await manager.start()
        try:
            yield
        finally:
            await manager.stop()

    app = FastAPI(title="Reels Download API", version="1.0.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.store = store
    app.state.manager = manager
    app.include_router(router)
    if settings.web_passcode:
        web.install(app)

    @app.exception_handler(JobError)
    async def job_error_handler(request: Request, exc: JobError) -> JSONResponse:
        status = _JOB_ERROR_STATUS.get(exc.code, 500)
        return JSONResponse(status_code=status, content={"error": exc.code.value, "message": exc.message})

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        detail = exc.detail
        content = detail if isinstance(detail, dict) else {"error": "http_error", "message": str(detail)}
        return JSONResponse(status_code=exc.status_code, content=content, headers=exc.headers)

    return app
