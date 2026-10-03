"""Liveness/readiness endpoints for load balancers and orchestrators."""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str


@router.get("/health")
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/ready")
async def ready() -> HealthResponse:
    # Check critical dependencies (database, cache) here before reporting ready.
    return HealthResponse(status="ready")
