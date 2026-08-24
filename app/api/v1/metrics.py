from fastapi import APIRouter, Response

from app.core.metrics import get_prometheus_metrics

router = APIRouter(tags=["Operational"])


@router.get(
    "/metrics",
    summary="Prometheus metrics exposition endpoint",
)
async def metrics() -> Response:
    """Returns Prometheus exposition format metrics for Prometheus scraper."""
    return get_prometheus_metrics()
