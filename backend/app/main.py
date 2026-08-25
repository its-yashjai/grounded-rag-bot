from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.agents.ingestion_agent import IngestionAgent
from app.api.v1 import chat, conversations, documents, health, metrics
from app.config import get_settings

settings = get_settings()

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"
FRONTEND_DIST = FRONTEND_DIR / "dist"

def _frontend_root() -> Path:
    # Prefer Vite React build (dist) if present, else legacy frontend folder
    if (FRONTEND_DIST / "index.html").is_file():
        return FRONTEND_DIST
    return FRONTEND_DIR

# Real multi-page app: each slug maps to its own HTML file.
SPA_PAGES = {
    "/": "index.html",
    "/app": "app.html",
    "/documents": "documents.html",
    "/observability": "observability.html",
}


def _restore_persisted_state() -> None:
    """Rebuild in-memory indexes from disk on boot: documents + chunk corpus
    come from the JSON store, BM25 is re-indexed from that corpus, and Chroma
    loads its own persisted vectors. Uploads made before a restart keep working."""
    from app.deps import get_bm25_index, get_doc_repo, get_ingestion_agent

    doc_repo = get_doc_repo()
    docs = doc_repo.list_all()
    chunks = doc_repo.all_chunks()
    if not chunks:
        return

    bm25 = get_bm25_index()
    for chunk_id, text, meta in chunks:
        bm25.add(chunk_id, text, meta)

    ingestion: IngestionAgent = get_ingestion_agent()
    print(f"[startup] restored {len(docs)} documents / {len(chunks)} chunks "
          f"(BM25 rebuilt; vector store: {ingestion.vector_store.health_check()})")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _restore_persisted_state()
    yield


app = FastAPI(
    title="Domain Knowledge Bot",
    description="Upload domain documents and ask grounded, cited questions over them.",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.app_env == "development" else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(documents.router)
app.include_router(chat.router)
app.include_router(conversations.router)
app.include_router(metrics.router)


@app.get("/{full_path:path}", include_in_schema=False)
async def spa(full_path: str):
    """Serve React Vite build (dist) if present, else legacy frontend.
    Handles static assets and SPA fallbacks including deep /app/<id>."""
    root = _frontend_root()
    # Try to serve real static file from root
    candidate = (root / full_path).resolve()
    if (
        full_path
        and candidate.is_file()
        and str(candidate).startswith(str(root.resolve()))
    ):
        return FileResponse(candidate)
    # Also try legacy FRONTEND_DIR for assets during dev transition
    if root != FRONTEND_DIR:
        legacy = (FRONTEND_DIR / full_path).resolve()
        if full_path and legacy.is_file() and str(legacy).startswith(str(FRONTEND_DIR.resolve())):
            return FileResponse(legacy)

    normalised = "/" + full_path.strip("/")
    # If React build, everything is SPA via index.html
    if (root / "index.html").is_file() and root == FRONTEND_DIST:
        # Serve React SPA for all known routes and deep chat URLs
        if normalised in ("/", "/app", "/documents", "/observability") or normalised.startswith("/app/"):
            return FileResponse(root / "index.html")
        # Fallback: also serve index for any other SPA route
        return FileResponse(root / "index.html")

    # Legacy fallback
    page = SPA_PAGES.get(normalised)
    if page and (FRONTEND_DIR / page).is_file():
        return FileResponse(FRONTEND_DIR / page)
    if normalised.startswith("/app/"):
        app_page = FRONTEND_DIR / "app.html"
        if app_page.is_file():
            return FileResponse(app_page)
    legacy_index = FRONTEND_DIR / "index.html"
    if legacy_index.is_file():
        return FileResponse(legacy_index)
    return FileResponse(root / "index.html")
