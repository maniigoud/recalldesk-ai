"""Analytics endpoint."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import CurrentUser, get_analytics_service
from app.schemas.analytics import AnalyticsResponse
from app.services.analytics_service import AnalyticsService

router = APIRouter(prefix="/api", tags=["Dashboard & Analytics"])


@router.get(
    "/analytics",
    response_model=AnalyticsResponse,
    summary="Analytics computed from application data",
    description=(
        "Ticket throughput, resolution rate, agent runs, memory operations and recurring "
        "issue categories. Every number is calculated from MySQL - nothing is hardcoded."
    ),
)
async def analytics(
    service: Annotated[AnalyticsService, Depends(get_analytics_service)],
    user: CurrentUser,
) -> AnalyticsResponse:
    return await service.analytics()
