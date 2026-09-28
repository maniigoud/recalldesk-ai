"""Ticket endpoints."""

from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.deps import CurrentUser, get_ticket_service
from app.schemas.ticket import (
    TicketCreate,
    TicketDetail,
    TicketListResponse,
    TicketRead,
    TicketUpdateRequest,
)
from app.services.ticket_service import TicketService

router = APIRouter(prefix="/api/tickets", tags=["Tickets"])


@router.get("", response_model=TicketListResponse, summary="List tickets with filters")
async def list_tickets(
    service: Annotated[TicketService, Depends(get_ticket_service)],
    user: CurrentUser,
    status_filter: Optional[str] = Query(default=None, alias="status"),
    priority: Optional[str] = Query(default=None),
    customer_id: Optional[int] = Query(default=None),
    assigned_to: Optional[int] = Query(default=None),
    search: Optional[str] = Query(default=None),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    sort_by: str = Query(default="created_at"),
    sort_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
) -> TicketListResponse:
    return await service.list(
        status=status_filter,
        priority=priority,
        customer_id=customer_id,
        assigned_to=assigned_to,
        search=search,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )


@router.post(
    "", response_model=TicketRead, status_code=status.HTTP_201_CREATED, summary="Create a ticket"
)
async def create_ticket(
    payload: TicketCreate,
    service: Annotated[TicketService, Depends(get_ticket_service)],
    user: CurrentUser,
) -> TicketRead:
    ticket = await service.create(payload)
    return TicketRead.model_validate(ticket)


@router.get("/{ticket_id}", response_model=TicketDetail, summary="Ticket detail")
async def get_ticket(
    ticket_id: int,
    service: Annotated[TicketService, Depends(get_ticket_service)],
    user: CurrentUser,
) -> TicketDetail:
    return await service.detail(ticket_id)


@router.put("/{ticket_id}", response_model=TicketDetail, summary="Update a ticket")
async def update_ticket(
    ticket_id: int,
    payload: TicketUpdateRequest,
    service: Annotated[TicketService, Depends(get_ticket_service)],
    user: CurrentUser,
) -> TicketDetail:
    ticket = await service.update(ticket_id, payload.ticket, resolution=payload.resolution)
    return await service.detail(ticket.id)


@router.delete("/{ticket_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a ticket")
async def delete_ticket(
    ticket_id: int,
    service: Annotated[TicketService, Depends(get_ticket_service)],
    user: CurrentUser,
) -> Response:
    await service.delete(ticket_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
