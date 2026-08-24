import time

from fastapi import Request, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    REGISTRY,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from starlette.middleware.base import BaseHTTPMiddleware

# Prometheus Metrics Definitions
HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total count of HTTP requests processed by TaskFlow API",
    ["method", "endpoint", "status_code"],
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "http_request_duration_seconds",
    "Histogram of HTTP request latencies in seconds",
    ["method", "endpoint"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

HTTP_REQUESTS_IN_PROGRESS = Gauge(
    "http_requests_in_progress",
    "Number of currently active in-flight HTTP requests",
    ["method", "endpoint"],
)


class PrometheusMiddleware(BaseHTTPMiddleware):
    """Middleware recording HTTP request counts, durations, and status codes for Prometheus."""

    async def dispatch(self, request: Request, call_next) -> Response:
        method = request.method
        # Strip query parameters for endpoint label cardinality control
        endpoint = request.url.path

        # Ignore metrics scraping endpoint itself to prevent metric inflation
        if endpoint in ("/metrics", "/api/v1/metrics"):
            return await call_next(request)

        HTTP_REQUESTS_IN_PROGRESS.labels(method=method, endpoint=endpoint).inc()
        start_time = time.perf_counter()

        try:
            response = await call_next(request)
            duration = time.perf_counter() - start_time
            status_code = str(response.status_code)

            HTTP_REQUESTS_TOTAL.labels(
                method=method, endpoint=endpoint, status_code=status_code
            ).inc()
            HTTP_REQUEST_DURATION_SECONDS.labels(method=method, endpoint=endpoint).observe(duration)

            return response
        except Exception:
            duration = time.perf_counter() - start_time
            HTTP_REQUESTS_TOTAL.labels(method=method, endpoint=endpoint, status_code="500").inc()
            HTTP_REQUEST_DURATION_SECONDS.labels(method=method, endpoint=endpoint).observe(duration)
            raise
        finally:
            HTTP_REQUESTS_IN_PROGRESS.labels(method=method, endpoint=endpoint).dec()


def get_prometheus_metrics() -> Response:
    """Returns exposition-formatted Prometheus metrics payload."""
    return Response(
        content=generate_latest(REGISTRY),
        media_type=CONTENT_TYPE_LATEST,
    )
