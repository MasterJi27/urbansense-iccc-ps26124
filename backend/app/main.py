import logging
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import api_router
from app.config import get_settings
from app.database import Base, SessionLocal, enable_postgis, ensure_pg_enum_values, ensure_schema_columns, engine
from app.deps import get_current_user
from app.models import *  # noqa: F401,F403
from app.models.user import User
from app.security import decode_token
from app.seed import ensure_camera_bays, seed_if_empty
from app.services.field_acl import field_path_allowed
from app.services.rdd_cloud import rdd_cloud_status, warmup_rdd
from app.services.redact import install_redact_filter
from app.spa import DASHBOARD_DIR, SPA_HEADERS, is_hidden_api_surface, should_serve_spa, spa_index

settings = get_settings()
install_redact_filter()
if not settings.is_development and settings.secret_key in {"dev-only-change-me", "change-me-to-a-long-random-string"}:
    raise RuntimeError("Set SECRET_KEY before running outside development.")
if settings.secret_key in {"dev-only-change-me", "change-me-to-a-long-random-string"}:
    logging.getLogger("urbansense").warning("SECRET_KEY is the demo default. Fine for local jury demo only.")

_docs = "/docs" if settings.is_development else None
app = FastAPI(
    title="SadakSaarthi API",
    description="Distributed urban intelligence platform — observations, fusion, assets, work orders.",
    version="0.1.0",
    docs_url=_docs,
    redoc_url="/redoc" if settings.is_development else None,
    openapi_url="/openapi.json" if settings.is_development else None,
)

_cors_regex = r"http://(localhost|127\.0\.0\.1):\d+" if settings.is_development else None
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list or ["http://127.0.0.1:5173"],
    allow_origin_regex=_cors_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.middleware("http")
async def request_id_and_field_gate(request: Request, call_next):
    request.state.request_id = request.headers.get("x-request-id") or uuid4().hex[:12]
    if not settings.is_development and is_hidden_api_surface(request.url.path):
        return JSONResponse({"detail": "Not found", "request_id": request.state.request_id}, status_code=404)
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        try:
            payload = decode_token(auth.split(" ", 1)[1].strip())
        except ValueError:
            payload = None
        if payload and payload.get("scope") == "field" and not field_path_allowed(request.method, request.url.path):
            return JSONResponse(
                {"detail": "Field booth token cannot open ICCC desks", "request_id": request.state.request_id},
                status_code=403,
            )
    if should_serve_spa(request):
        return spa_index()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    return response


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception):
    if isinstance(exc, (HTTPException, StarletteHTTPException, RequestValidationError)):
        raise exc
    logging.getLogger("urbansense").exception("unhandled %s", getattr(request.state, "request_id", "-"))
    return JSONResponse(
        {"detail": "Internal error", "request_id": getattr(request.state, "request_id", None)},
        status_code=500,
    )


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
        ensure_pg_enum_values(engine)
    except OperationalError:
        url = "sqlite+pysqlite:///./urbansense.db"
        engine = create_engine(url, **_engine_kwargs(url))
        SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        database.engine = engine
        database.SessionLocal = SessionLocal
        Base.metadata.create_all(bind=engine)
    ensure_pg_enum_values(engine)
    try:
        ensure_schema_columns(engine)
    except Exception:
        logging.getLogger("urbansense").exception("schema column migrate skipped")
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
    try:
        warmup_rdd()
    except Exception:
        logging.getLogger("urbansense").exception("rdd warmup skipped")


@app.get("/")
def root():
    index = DASHBOARD_DIR / "index.html"
    if index.is_file():
        return FileResponse(index, headers=SPA_HEADERS)
    payload = {"service": "urbansense", "health": "/health"}
    if settings.is_development:
        payload["docs"] = "/docs"
    return payload


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "urbansense-backend",
        "azure_vision": bool(settings.azure_vision_endpoint.strip()),
        "azure_blob": bool(settings.azure_storage_account_url.strip()),
        "azure_openai": bool(settings.azure_openai_endpoint.strip()),
        "azure_content_safety": bool(settings.azure_contentsafety_endpoint.strip()),
        "azure_maps": bool(settings.azure_maps_subscription_key.strip()),
        "rdd": rdd_cloud_status()["honesty"],
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
        if not settings.is_development and is_hidden_api_surface(full_path):
            raise HTTPException(status_code=404, detail="Not found")
        if not full_path:
            return FileResponse(DASHBOARD_DIR / "index.html", headers=SPA_HEADERS)
        candidate = (DASHBOARD_DIR / full_path).resolve()
        try:
            candidate.relative_to(DASHBOARD_DIR.resolve())
        except ValueError:
            return FileResponse(DASHBOARD_DIR / "index.html", headers=SPA_HEADERS)
        if candidate.is_file():
            headers = dict(SPA_HEADERS)
            if full_path.startswith("weights/") or full_path.startswith("ort/"):
                headers = {"Cache-Control": "public, max-age=31536000, immutable"}
            return FileResponse(candidate, headers=headers)
        return FileResponse(DASHBOARD_DIR / "index.html", headers=SPA_HEADERS)
