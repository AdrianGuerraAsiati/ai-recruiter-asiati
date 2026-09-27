"""Liveness and readiness endpoints for FastAPI."""

import logging
import os

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.db import get_engine

logger = logging.getLogger(__name__)

router = APIRouter()


def _check_db() -> bool:
    """Verify that the configured database accepts a trivial query."""
    if not os.getenv("DATABASE_URL", "").strip():
        logger.error("Readiness failed: DATABASE_URL is not configured.")
        return False

    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.warning("DB readiness check failed: %s", type(exc).__name__)
        return False


@router.get("/live")
@router.get("/api/live")
def liveness_check():
    """Process liveness only; does not depend on external services."""
    return {"status": "ok"}


@router.get("/ready")
@router.get("/api/ready")
@router.get("/health")
@router.get("/api/health")
def readiness_check():
    """Readiness check used before routing production traffic."""
    if _check_db():
        return {"status": "ok", "db": True}

    return JSONResponse(
        status_code=503,
        content={"status": "unhealthy", "db": False},
    )
