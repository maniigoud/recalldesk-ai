"""Dashboard and analytics endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import CurrentUser, get_analytics_service
from app.schemas.analytics import DashboardResponse
from app.services.analytics_service import AnalyticsService

router = APIRouter(tags=["Dashboard & Analytics"])


@router.get(
    "/api/dashboard",
    response_model=DashboardResponse,
    summary="Workspace dashboard (real database counts)",
)
async def dashboard(
    service: Annotated[AnalyticsService, Depends(get_analytics_service)],
    user: CurrentUser,
    days: int = Query(default=14, ge=1, le=90, description="Memory activity window in days"),
) -> DashboardResponse:
    return await service.dashboard(days=days)
