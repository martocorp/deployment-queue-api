"""Management server for health checks and Prometheus metrics.

This server runs on a separate port (default 9090) to expose:
- /health - Health check endpoint
- /ready - Readiness check endpoint
- /metrics - Prometheus metrics endpoint
"""

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

management_app = FastAPI(
    title="Deployment Queue Management",
    description="Health checks and metrics endpoints",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
)


@management_app.get("/health")
def health_check() -> dict[str, str]:
    """Health check endpoint - returns healthy if the service is running."""
    return {"status": "healthy"}


@management_app.get("/ready")
def readiness_check() -> dict[str, str]:
    """Readiness check endpoint - returns ready if the service can accept traffic."""
    # In the future, this could check database connectivity
    return {"status": "ready"}


@management_app.get("/metrics")
def metrics() -> PlainTextResponse:
    """Prometheus metrics endpoint."""
    return PlainTextResponse(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )
