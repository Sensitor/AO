import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .routers import auth, documents, projects
from .storage import ensure_bucket

logger = logging.getLogger("ao")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Crée le bucket de stockage au démarrage (best effort : ne bloque pas le boot).
    try:
        ensure_bucket()
    except Exception:  # noqa: BLE001
        logger.warning("Bucket S3 non initialisé au démarrage", exc_info=True)
    yield


app = FastAPI(title="AO Copilot API", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(documents.router)


@app.get("/health", tags=["system"])
def health():
    return {"status": "ok"}
