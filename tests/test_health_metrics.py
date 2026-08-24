import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check_healthy(client: AsyncClient) -> None:
    """Test health check returns 200 OK when both PostgreSQL and Redis are responsive."""
    response = await client.get("/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "healthy"
    assert "timestamp" in data
    assert "version" in data
    assert data["services"]["postgres"]["status"] == "healthy"
    assert "latency_ms" in data["services"]["postgres"]
    assert data["services"]["redis"]["status"] == "healthy"
    assert "latency_ms" in data["services"]["redis"]


@pytest.mark.asyncio
async def test_health_check_api_v1_path(client: AsyncClient) -> None:
    """Test health check under /api/v1/health path."""
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


@pytest.mark.asyncio
async def test_metrics_endpoint_prometheus_format(client: AsyncClient) -> None:
    """Test Prometheus metrics endpoint returns exposition format."""
    # Perform a request first to generate some metrics
    await client.get("/health")

    response = await client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers.get("content-type", "")

    content = response.text
    assert "http_requests_total" in content
    assert "http_request_duration_seconds" in content
