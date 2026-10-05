"""FastAPI application factory and composition root."""

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.auth_routes import router as auth_router
from app.config import CORS_ORIGINS, api_docs_enabled, get_database_url
from app.access_control import ensure_rbac_catalog
from app.db import SessionLocal
from app.domains.candidate_imports.router import router as candidate_imports_router
from app.domains.candidate_ingestion.indeed_agent_router import router as indeed_agent_router
from app.domains.candidate_ingestion.router import router as candidate_ingestion_router
from app.domains.candidates.router import assign_router, router as candidates_router
from app.domains.evaluations.router import router as evaluations_router
from app.domains.employee_scores.router import router as employee_scores_router
from app.domains.employees.router import router as employees_router
from app.domains.indeed.router import router as indeed_router
from app.domains.hiring.router import router as hiring_router
from app.domains.odoo_sync.router import router as odoo_sync_router
from app.domains.jobs.router import router as jobs_router
from app.domains.ranking.router import router as ranking_router
from app.domains.recruitment_calendar.router import router as recruitment_calendar_router
from app.domains.talent_id.router import kiosk_router as talent_id_kiosk_router
from app.domains.talent_id.router import router as talent_id_router
from app.domains.training.asiati_media import migrate_latest_published_onboarding_media
from app.domains.training.router import router as training_router
from app.health import router as health_router
from app.observability import configure_logging, install_request_observability

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Build the FastAPI application without changing its public contract."""
    configure_logging()
    expose_docs = api_docs_enabled()
    app = FastAPI(
        title="AI Recruiter API (PostgreSQL)",
        description="Ranking de candidatos con PostgreSQL + advisory locks",
        version="2.0.0",
        docs_url="/docs" if expose_docs else None,
        redoc_url="/redoc" if expose_docs else None,
        openapi_url="/openapi.json" if expose_docs else None,
    )

    install_request_observability(app)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(CORS_ORIGINS),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(jobs_router)
    app.include_router(candidates_router)
    app.include_router(assign_router)
    app.include_router(evaluations_router)
    app.include_router(employee_scores_router)
    app.include_router(employees_router)
    app.include_router(hiring_router)
    app.include_router(odoo_sync_router)
    app.include_router(ranking_router)
    app.include_router(recruitment_calendar_router)
    app.include_router(talent_id_router)
    app.include_router(talent_id_kiosk_router)
    app.include_router(training_router)
    app.include_router(candidate_imports_router)
    app.include_router(candidate_ingestion_router)
    app.include_router(indeed_router)
    app.include_router(indeed_agent_router)

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error(
            "Unhandled error on %s %s: %s",
            request.method,
            request.url.path,
            exc,
            exc_info=True,
            extra={
                "event": "unhandled_exception",
                "http_method": request.method,
                "http_path": request.url.path,
            },
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Error interno del servidor."},
        )

    @app.on_event("startup")
    def on_startup() -> None:
        db_url = get_database_url()
        if "sqlite" in db_url or not db_url:
            logger.info("Skipping production RBAC catalog sync for non-PostgreSQL runtime.")
            return

        # Alembic is the only schema owner. Startup may reconcile seed data,
        # but it must never create/alter tables implicitly.
        db = SessionLocal()
        try:
            ensure_rbac_catalog(db)
            db.commit()
            media_result = migrate_latest_published_onboarding_media(db)
            logger.info("ASIATI onboarding media ready: %s", media_result)
        finally:
            db.close()
        logger.info("RBAC catalog ready.")

    return app
