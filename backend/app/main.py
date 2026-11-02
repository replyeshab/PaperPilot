import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError

from . import repository
from .config import get_settings
from .routers_auth import router as auth_router
from .routers_chat import router as chat_router
from .routers_library import resume_pending_uploads, router as library_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("paperpilot")
settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        repository.ensure_schema()
        resume_pending_uploads()
    except Exception:
        # The database may still be waking up (Neon scales to zero). Requests retry the setup.
        logger.exception("Database setup failed at startup; it will be retried on the next request")
    yield


app = FastAPI(
    title=settings.app_name,
    version="2.0.0",
    description="Question answering over PDFs with accounts, saved history and a shared request budget.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)
app.include_router(auth_router)
app.include_router(library_router)
app.include_router(chat_router)


@app.exception_handler(OperationalError)
async def database_unavailable(request: Request, exc: OperationalError) -> JSONResponse:
    logger.error("Database error on %s %s: %s", request.method, request.url.path, exc.__class__.__name__)
    return JSONResponse(status_code=503, content={"detail": "The database is unavailable right now. Please try again shortly."})


@app.exception_handler(Exception)
async def unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Unexpected server error. Please try again."})
