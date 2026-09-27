import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.concurrency import run_in_threadpool

from app.api.deps import get_model_gateway
from app.api.routes.analyses import router as analyses_router
from app.api.routes.auth import router as auth_router
from app.bootstrap.seed import run_seed
from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.repositories.s3_store import S3ObjectStore

logger = logging.getLogger(__name__)


def bootstrap() -> None:
    """Best-effort startup bootstrap: the API must still serve when a backing store lags."""
    store = S3ObjectStore()
    try:
        store.ensure_bucket()
    except Exception:
        logger.warning("Could not ensure the object storage bucket", exc_info=True)
    try:
        settings = get_settings()
        local_model_path = settings.detector_local_path
        if local_model_path and store.seed_model_if_missing(local_model_path):
            logger.info("Uploaded local detector artifact to object storage")
    except Exception:
        logger.warning("Could not seed model artifact to object storage", exc_info=True)
    try:
        run_seed()
    except Exception:
        logger.warning("Could not seed organizations and users", exc_info=True)
    try:
        get_model_gateway().ensure_model_loaded()
    except Exception:
        logger.warning("Model not preloaded; the first analyze request will retry", exc_info=True)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    await run_in_threadpool(bootstrap)
    yield


app = FastAPI(title="Narwal API", version="0.1.0", lifespan=lifespan)
register_error_handlers(app)
app.include_router(auth_router)
app.include_router(analyses_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
