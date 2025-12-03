"""Tests for management endpoints (health, readiness, metrics)."""

from fastapi.testclient import TestClient

from deployment_queue.management import management_app


class TestHealthCheck:
    """Tests for health check endpoint."""

    def test_health_check(self) -> None:
        """Health check returns healthy status."""
        with TestClient(management_app) as client:
            response = client.get("/health")
            assert response.status_code == 200
            assert response.json() == {"status": "healthy"}


class TestReadinessCheck:
    """Tests for readiness check endpoint."""

    def test_readiness_check(self) -> None:
        """Readiness check returns ready status."""
        with TestClient(management_app) as client:
            response = client.get("/ready")
            assert response.status_code == 200
            assert response.json() == {"status": "ready"}


class TestMetrics:
    """Tests for Prometheus metrics endpoint."""

    def test_metrics_endpoint(self) -> None:
        """Metrics endpoint returns Prometheus format."""
        with TestClient(management_app) as client:
            response = client.get("/metrics")
            assert response.status_code == 200
            assert "text/plain" in response.headers["content-type"]
            # Check for some expected metrics
            content = response.text
            assert "deployment_queue_info" in content
            assert "http_requests_total" in content
            assert "http_request_duration_seconds" in content

    def test_metrics_contains_deployment_metrics(self) -> None:
        """Metrics endpoint includes deployment-specific metrics."""
        with TestClient(management_app) as client:
            response = client.get("/metrics")
            content = response.text
            assert "deployments_created_total" in content
            assert "deployments_updated_total" in content
            assert "rollbacks_total" in content
