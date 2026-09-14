from fastapi import FastAPI

from app.api.routes.analyses import router as analyses_router
from app.api.routes.auth import router as auth_router
from app.core.errors import register_error_handlers

app = FastAPI(title="Narwal API", version="0.1.0")
register_error_handlers(app)
app.include_router(auth_router)
app.include_router(analyses_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
