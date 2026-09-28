"""Customer CRUD endpoints (organization scoped)."""

from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.deps import CurrentUser, get_customer_service
from app.schemas.customer import (
    CustomerCreate,
    CustomerDetail,
    CustomerListResponse,
    CustomerRead,
    CustomerUpdate,
)
from app.services.customer_service import CustomerService

router = APIRouter(prefix="/api/customers", tags=["Customers"])


@router.get("", response_model=CustomerListResponse, summary="List customers")
async def list_customers(
    service: Annotated[CustomerService, Depends(get_customer_service)],
    user: CurrentUser,
    search: Optional[str] = Query(default=None, description="Name, email or company fragment"),
    status_filter: Optional[str] = Query(default=None, alias="status", description="Customer status"),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    sort_by: str = Query(default="created_at"),
    sort_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
) -> CustomerListResponse:
    return await service.list(
        search=search,
        status=status_filter,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )


@router.post(
    "",
    response_model=CustomerRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a customer",
)
async def create_customer(
    payload: CustomerCreate,
    service: Annotated[CustomerService, Depends(get_customer_service)],
    user: CurrentUser,
) -> CustomerRead:
    customer = await service.create(payload)
    return CustomerRead.model_validate(customer)


@router.get("/{customer_id}", response_model=CustomerDetail, summary="Customer detail with summary")
async def get_customer(
    customer_id: int,
    service: Annotated[CustomerService, Depends(get_customer_service)],
    user: CurrentUser,
) -> CustomerDetail:
    return await service.detail(customer_id)


@router.put("/{customer_id}", response_model=CustomerRead, summary="Update a customer")
async def update_customer(
    customer_id: int,
    payload: CustomerUpdate,
    service: Annotated[CustomerService, Depends(get_customer_service)],
    user: CurrentUser,
) -> CustomerRead:
    customer = await service.update(customer_id, payload)
    return CustomerRead.model_validate(customer)


@router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a customer")
async def delete_customer(
    customer_id: int,
    service: Annotated[CustomerService, Depends(get_customer_service)],
    user: CurrentUser,
) -> Response:
    await service.delete(customer_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
