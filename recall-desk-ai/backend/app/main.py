"""RecallDesk AI backend application entrypoint."""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import Any, Dict

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.routes import (
    analytics,
    auth,
    conversations,
    customers,
    dashboard,
    memory,
    support,
    tickets,
)
from app.core.config import settings
from app.core.errors import AppError
from app.core.logging import configure_logging, get_logger
from app.db.database import SessionLocal
from app.services.hindsight_service import get_hindsight_service
from app.services.llm_service import get_llm_service

configure_logging("DEBUG" if settings.debug else "INFO")
logger = get_logger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "app.startup",
        extra={
            "app": settings.app_name,
            "env": settings.app_env,
            "hindsight_configured": settings.hindsight_configured,
            "groq_configured": settings.groq_configured,
        },
    )
    try:
        await get_hindsight_service().ensure_bank()
    except Exception as exc:  # noqa: BLE001 - startup must not crash on memory provider
        logger.warning("app.startup_hindsight_unavailable", extra={"error": str(exc)})
    yield
    try:
        await get_hindsight_service().aclose()
    except Exception:  # noqa: BLE001
        pass
    logger.info("app.shutdown")


TAGS_METADATA = [
    {"name": "Authentication", "description": "Register, log in and inspect the current user."},
    {"name": "Customers", "description": "Customer CRUD, search and memory aware detail view."},
    {"name": "Tickets", "description": "Ticket lifecycle, assignment and resolutions."},
    {"name": "Conversations", "description": "Session scoped conversation and message history."},
    {
        "name": "AI Support",
        "description": "Memory aware AI support agent (Hindsight recall + Groq + tools).",
    },
    {
        "name": "Memory",
        "description": "Direct access to Hindsight: browse, recall, retain and reflect.",
    },
    {"name": "Dashboard & Analytics", "description": "Workspace metrics computed from MySQL."},
    {"name": "System", "description": "Health and service status."},
]

app = FastAPI(
    title=settings.app_name,
    description=(
        "RecallDesk AI - customer support that remembers.\n\n"
        "MySQL stores structured application state, Hindsight stores persistent customer "
        "memory, Groq powers the agent."
    ),
    version="1.0.0",
    openapi_tags=TAGS_METADATA,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------- error handling


def _error_response(status_code: int, code: str, message: str, details: Any = None) -> JSONResponse:
    error: Dict[str, Any] = {"code": code, "message": message}
    if details:
        error["details"] = details
    return JSONResponse(status_code=status_code, content={"error": error})


@app.exception_handler(AppError)
async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
    if exc.status_code >= 500:
        logger.error("request.failed", extra={"path": request.url.path, "code": exc.code})
    else:
        logger.warning(
            "request.rejected",
            extra={"path": request.url.path, "code": exc.code, "status": exc.status_code},
        )
    return JSONResponse(status_code=exc.status_code, content=exc.to_payload())


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    return _error_response(
        422,
        "VALIDATION_ERROR",
        "Request validation failed.",
        [
            {
                "field": ".".join(str(part) for part in error.get("loc", [])[1:]) or "body",
                "message": error.get("msg", "invalid value"),
            }
            for error in exc.errors()
        ],
    )


@app.exception_handler(SQLAlchemyError)
async def handle_database_error(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    logger.error("database.error", extra={"path": request.url.path, "error": str(exc)})
    return _error_response(500, "DATABASE_ERROR", "A database error occurred.")


@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "request.unhandled_error",
        extra={"path": request.url.path, "error": str(exc)},
        exc_info=exc,
    )
    return _error_response(500, "INTERNAL_ERROR", "An unexpected error occurred.")


# ----------------------------------------------------------------- middleware


@app.middleware("http")
async def access_log(request: Request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    duration_ms = int((time.perf_counter() - started) * 1000)
    logger.info(
        "http.request",
        extra={
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
        },
    )
    response.headers["X-Process-Time-Ms"] = str(duration_ms)
    return response


# --------------------------------------------------------------------- routes

app.include_router(auth.router)
app.include_router(customers.router)
app.include_router(tickets.router)
app.include_router(conversations.router)
app.include_router(support.router)
app.include_router(memory.router)
app.include_router(dashboard.router)
app.include_router(analytics.router)


@app.get("/health", tags=["System"], summary="Liveness and dependency status")
async def health() -> Dict[str, Any]:
    services: Dict[str, str] = {}

    try:
        async with SessionLocal() as session:
            await session.execute(text("SELECT 1"))
        services["database"] = "connected"
    except Exception as exc:  # noqa: BLE001
        logger.warning("health.database_failed", extra={"error": str(exc)})
        services["database"] = "unavailable"

    services["hindsight"] = (
        f"configured (bank: {settings.hindsight_bank_id})"
        if settings.hindsight_configured
        else "unconfigured"
    )
    services["groq"] = (
        f"configured (model: {settings.groq_model})" if settings.groq_configured else "unconfigured"
    )
    services["knowledge_base"] = "loaded"

    overall = "ok" if services["database"] == "connected" else "degraded"
    if not settings.hindsight_configured or not settings.groq_configured:
        overall = "degraded" if overall == "ok" else overall

    return {
        "status": overall,
        "app": settings.app_name,
        "environment": settings.app_env,
        "services": services,
    }


@app.get("/health/detailed", tags=["System"], summary="Detailed dependency probe")
async def health_detailed() -> Dict[str, Any]:
    memory = get_hindsight_service()
    llm = get_llm_service()
    return {
        "status": "ok",
        "app": settings.app_name,
        "environment": settings.app_env,
        "services": {
            "database": {"configured": True, "driver": settings.database_url.split("+")[0]},
            "hindsight": {
                "configured": settings.hindsight_configured,
                "bank_id": settings.hindsight_bank_id,
                "provider": memory.provider_name,
                "status": await memory.health(),
            },
            "groq": {
                "configured": settings.groq_configured,
                "model": settings.groq_model,
                "provider": llm.provider_name,
            },
        },
    }
