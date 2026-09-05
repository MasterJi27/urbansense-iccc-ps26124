import logging
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import api_router
from app.config import get_settings
from app.database import Base, SessionLocal, enable_postgis, engine
from app.deps import get_current_user
from app.models import *  # noqa: F401,F403
from app.models.user import User
from app.seed import ensure_camera_bays, seed_if_empty
from app.spa import DASHBOARD_DIR, should_serve_spa, spa_index

settings = get_settings()
if settings.app_env != "development" and settings.secret_key in {"dev-only-change-me", "change-me-to-a-long-random-string"}:
    raise RuntimeError("Set SECRET_KEY before running outside development.")
if settings.secret_key in {"dev-only-change-me", "change-me-to-a-long-random-string"}:
    logging.getLogger("urbansense").warning("SECRET_KEY is the demo default. Fine for local jury demo only.")
app = FastAPI(
    title="UrbanSense API",
    description="Distributed urban intelligence platform — observations, fusion, assets, work orders.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list or ["*"],
    allow_origin_regex=r"https://.*\.(azurewebsites\.net|azurestaticapps\.net)|http://(localhost|127\.0\.0\.1):\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.middleware("http")
async def spa_document_navigation(request, call_next):
    """Browser refresh on /events/:id must not hit the JSON API (401)."""
    if should_serve_spa(request):
        return spa_index()
    return await call_next(request)


@app.on_event("startup")
def on_startup():
    global engine, SessionLocal
    from sqlalchemy.exc import OperationalError
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.database import _engine_kwargs
    import app.database as database

    try:
        enable_postgis(engine)
        Base.metadata.create_all(bind=engine)
    except OperationalError:
        url = "sqlite+pysqlite:///./urbansense.db"
        engine = create_engine(url, **_engine_kwargs(url))
        SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        database.engine = engine
        database.SessionLocal = SessionLocal
        Base.metadata.create_all(bind=engine)
    # minimal migration: add checklist JSON field to inspections if missing (existing DB)
    try:
        with engine.begin() as conn:
            try:
                cols = [r[1] for r in conn.exec_driver_sql("PRAGMA table_info(inspections)").fetchall()]
            except Exception:
                cols = []
            if cols and "checklist" not in cols:
                conn.exec_driver_sql("ALTER TABLE inspections ADD COLUMN checklist JSON")
    except Exception:
        try:
            with engine.begin() as conn:
                conn.exec_driver_sql("ALTER TABLE inspections ADD COLUMN checklist JSON")
        except Exception:
            pass
    if settings.demo_seed_on_start:
        db = SessionLocal()
        try:
            seed_if_empty(db)
            ensure_camera_bays(db)
        finally:
            db.close()


@app.get("/")
def root():
    index = DASHBOARD_DIR / "index.html"
    if index.is_file():
        return FileResponse(index)
    return {"service": "urbansense", "docs": "/docs", "health": "/health"}


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "urbansense-backend",
        "azure_vision": bool(settings.azure_vision_endpoint.strip()),
        "azure_blob": bool(settings.azure_storage_account_url.strip()),
        "azure_openai": bool(settings.azure_openai_endpoint.strip()),
        "azure_content_safety": bool(settings.azure_contentsafety_endpoint.strip()),
    }


# DPDP: evidence directory with auth-gated access (no open StaticFiles mount)
evid_path = Path(settings.evidence_dir)
evid_path.mkdir(parents=True, exist_ok=True)


@app.get("/evidence/{file_path:path}")
@app.head("/evidence/{file_path:path}")
def serve_evidence(file_path: str, user: User = Depends(get_current_user)):
    base = Path(settings.evidence_dir).resolve()
    # ensure base exists
    base.mkdir(parents=True, exist_ok=True)
    target = (base / file_path).resolve()
    try:
        target.relative_to(base)
    except ValueError:
        raise HTTPException(status_code=404, detail="Not found")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(str(target))


if DASHBOARD_DIR.is_dir():
    ui = DASHBOARD_DIR / "ui"
    if ui.is_dir():
        app.mount("/ui", StaticFiles(directory=ui), name="dashboard-ui")

    @app.get("/{full_path:path}")
    def dashboard_spa(full_path: str):
        if not full_path:
            return FileResponse(DASHBOARD_DIR / "index.html")
        candidate = (DASHBOARD_DIR / full_path).resolve()
        try:
            candidate.relative_to(DASHBOARD_DIR.resolve())
        except ValueError:
            return FileResponse(DASHBOARD_DIR / "index.html")
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(DASHBOARD_DIR / "index.html")
