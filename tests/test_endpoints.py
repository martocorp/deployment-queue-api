"""Tests for API endpoints."""

import pytest
from fastapi.testclient import TestClient

from deployment_queue.main import app, get_cursor
from tests.conftest import MockCursor, create_mock_deployment_row


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


class TestHealthCheck:
    """Tests for health check endpoint."""

    def test_health_check(self, client: TestClient):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}


class TestCreateDeployment:
    """Tests for POST /v1/deployments endpoint."""

    def test_create_deployment(self, client: TestClient):
        mock_cursor = MockCursor([create_mock_deployment_row()])

        def override_get_cursor():
            yield mock_cursor

        app.dependency_overrides[get_cursor] = override_get_cursor

        response = client.post(
            "/v1/deployments",
            json={
                "name": "test-service",
                "version": "1.0.0",
                "provider": "gcp",
                "environment": "production",
                "type": "k8s",
                "cloud_account_id": "project-123",
                "region": "us-central1",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "test-service"
        assert data["version"] == "1.0.0"
        assert data["status"] == "scheduled"
        assert "id" in data

        app.dependency_overrides.clear()

    def test_create_deployment_with_all_fields(self, client: TestClient):
        mock_cursor = MockCursor([create_mock_deployment_row()])

        def override_get_cursor():
            yield mock_cursor

        app.dependency_overrides[get_cursor] = override_get_cursor

        response = client.post(
            "/v1/deployments",
            json={
                "name": "test-service",
                "version": "1.0.0",
                "commit_sha": "abc123",
                "pipeline_extra_params": '{"key": "value"}',
                "provider": "aws",
                "cloud_account_id": "123456789",
                "region": "us-east-1",
                "environment": "staging",
                "cell": "cell-1",
                "type": "terraform",
                "auto": False,
                "description": "Test deployment",
                "notes": "Some notes",
                "build_uri": "https://build.example.com",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["auto"] is False

        app.dependency_overrides.clear()

    def test_create_deployment_invalid_provider(self, client: TestClient):
        # Need a mock even for validation tests since TestClient resolves dependencies
        mock_cursor = MockCursor([])

        def override_get_cursor():
            yield mock_cursor

        app.dependency_overrides[get_cursor] = override_get_cursor

        response = client.post(
            "/v1/deployments",
            json={
                "name": "test-service",
                "version": "1.0.0",
                "provider": "invalid",
                "environment": "production",
                "type": "k8s",
            },
        )

        assert response.status_code == 422

        app.dependency_overrides.clear()


class TestListDeployments:
    """Tests for GET /v1/deployments endpoint."""

    def test_list_deployments(self, client: TestClient):
        mock_cursor = MockCursor([
            create_mock_deployment_row(id="uuid-1"),
            create_mock_deployment_row(id="uuid-2"),
        ])

        def override_get_cursor():
            yield mock_cursor

        app.dependency_overrides[get_cursor] = override_get_cursor

        response = client.get("/v1/deployments")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

        app.dependency_overrides.clear()

    def test_list_deployments_with_filters(self, client: TestClient):
        mock_cursor = MockCursor([
            create_mock_deployment_row(id="uuid-1", status="deployed"),
        ])

        def override_get_cursor():
            yield mock_cursor

        app.dependency_overrides[get_cursor] = override_get_cursor

        response = client.get(
            "/v1/deployments",
            params={
                "status": "deployed",
                "environment": "production",
                "provider": "gcp",
                "limit": 10,
            },
        )

        assert response.status_code == 200

        app.dependency_overrides.clear()

    def test_list_deployments_empty(self, client: TestClient):
        mock_cursor = MockCursor([])

        def override_get_cursor():
            yield mock_cursor

        app.dependency_overrides[get_cursor] = override_get_cursor

        response = client.get("/v1/deployments")

        assert response.status_code == 200
        assert response.json() == []

        app.dependency_overrides.clear()


class TestGetDeployment:
    """Tests for GET /v1/deployments/{deployment_id} endpoint."""

    def test_get_deployment(self, client: TestClient):
        mock_cursor = MockCursor([create_mock_deployment_row(id="test-uuid")])

        def override_get_cursor():
            yield mock_cursor

        app.dependency_overrides[get_cursor] = override_get_cursor

        response = client.get("/v1/deployments/test-uuid")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "test-uuid"

        app.dependency_overrides.clear()

    def test_get_deployment_not_found(self, client: TestClient):
        mock_cursor = MockCursor([])

        def override_get_cursor():
            yield mock_cursor

        app.dependency_overrides[get_cursor] = override_get_cursor

        response = client.get("/v1/deployments/non-existent")

        assert response.status_code == 404
        assert response.json()["detail"] == "Deployment not found"

        app.dependency_overrides.clear()


class TestUpdateDeployment:
    """Tests for PATCH /v1/deployments/{deployment_id} endpoint."""

    def test_update_deployment(self, client: TestClient):
        original_row = create_mock_deployment_row(id="test-uuid", status="scheduled")
        updated_row = create_mock_deployment_row(id="test-uuid", status="deployed")
        mock_cursor = MockCursor([original_row, updated_row])

        def override_get_cursor():
            yield mock_cursor

        app.dependency_overrides[get_cursor] = override_get_cursor

        response = client.patch(
            "/v1/deployments/test-uuid",
            json={"status": "deployed", "notes": "Deployment completed"},
        )

        assert response.status_code == 200

        app.dependency_overrides.clear()

    def test_update_deployment_not_found(self, client: TestClient):
        mock_cursor = MockCursor([])

        def override_get_cursor():
            yield mock_cursor

        app.dependency_overrides[get_cursor] = override_get_cursor

        response = client.patch(
            "/v1/deployments/non-existent",
            json={"status": "deployed"},
        )

        assert response.status_code == 404

        app.dependency_overrides.clear()

    def test_update_deployment_no_fields(self, client: TestClient):
        mock_cursor = MockCursor([create_mock_deployment_row(id="test-uuid")])

        def override_get_cursor():
            yield mock_cursor

        app.dependency_overrides[get_cursor] = override_get_cursor

        response = client.patch("/v1/deployments/test-uuid", json={})

        assert response.status_code == 400
        assert response.json()["detail"] == "No fields to update"

        app.dependency_overrides.clear()


class TestGetCurrentDeployment:
    """Tests for GET /v1/deployments/current endpoint."""

    def test_get_current_deployment(self, client: TestClient):
        mock_cursor = MockCursor([create_mock_deployment_row()])

        def override_get_cursor():
            yield mock_cursor

        app.dependency_overrides[get_cursor] = override_get_cursor

        response = client.get(
            "/v1/deployments/current",
            params={
                "name": "test-service",
                "environment": "production",
                "provider": "gcp",
                "cloud_account_id": "project-123",
                "region": "us-central1",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "test-service"

        app.dependency_overrides.clear()

    def test_get_current_deployment_with_cell(self, client: TestClient):
        mock_cursor = MockCursor([create_mock_deployment_row(cell="cell-1")])

        def override_get_cursor():
            yield mock_cursor

        app.dependency_overrides[get_cursor] = override_get_cursor

        response = client.get(
            "/v1/deployments/current",
            params={
                "name": "test-service",
                "environment": "production",
                "provider": "gcp",
                "cloud_account_id": "project-123",
                "region": "us-central1",
                "cell": "cell-1",
            },
        )

        assert response.status_code == 200

        app.dependency_overrides.clear()

    def test_get_current_deployment_not_found(self, client: TestClient):
        mock_cursor = MockCursor([])

        def override_get_cursor():
            yield mock_cursor

        app.dependency_overrides[get_cursor] = override_get_cursor

        response = client.get(
            "/v1/deployments/current",
            params={
                "name": "non-existent",
                "environment": "production",
                "provider": "gcp",
                "cloud_account_id": "project-123",
                "region": "us-central1",
            },
        )

        assert response.status_code == 404

        app.dependency_overrides.clear()


class TestUpdateStatusByTaxonomy:
    """Tests for PATCH /v1/deployments/current/status endpoint."""

    def test_update_status_by_taxonomy(self, client: TestClient):
        mock_cursor = MockCursor([
            {"ID": "test-uuid"},
            create_mock_deployment_row(status="deployed"),
        ])

        def override_get_cursor():
            yield mock_cursor

        app.dependency_overrides[get_cursor] = override_get_cursor

        response = client.patch(
            "/v1/deployments/current/status",
            params={
                "name": "test-service",
                "environment": "production",
                "provider": "gcp",
                "cloud_account_id": "project-123",
                "region": "us-central1",
            },
            json={"status": "deployed"},
        )

        assert response.status_code == 200

        app.dependency_overrides.clear()

    def test_update_status_not_found(self, client: TestClient):
        mock_cursor = MockCursor([])

        def override_get_cursor():
            yield mock_cursor

        app.dependency_overrides[get_cursor] = override_get_cursor

        response = client.patch(
            "/v1/deployments/current/status",
            params={
                "name": "non-existent",
                "environment": "production",
                "provider": "gcp",
                "cloud_account_id": "project-123",
                "region": "us-central1",
            },
            json={"status": "deployed"},
        )

        assert response.status_code == 404

        app.dependency_overrides.clear()


class TestDeploymentHistory:
    """Tests for GET /v1/deployments/history endpoint."""

    def test_deployment_history(self, client: TestClient):
        mock_cursor = MockCursor([
            create_mock_deployment_row(id="uuid-1", version="3.0.0"),
            create_mock_deployment_row(id="uuid-2", version="2.0.0"),
            create_mock_deployment_row(id="uuid-3", version="1.0.0"),
        ])

        def override_get_cursor():
            yield mock_cursor

        app.dependency_overrides[get_cursor] = override_get_cursor

        response = client.get(
            "/v1/deployments/history",
            params={
                "name": "test-service",
                "environment": "production",
                "provider": "gcp",
                "cloud_account_id": "project-123",
                "region": "us-central1",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3

        app.dependency_overrides.clear()

    def test_deployment_history_empty(self, client: TestClient):
        mock_cursor = MockCursor([])

        def override_get_cursor():
            yield mock_cursor

        app.dependency_overrides[get_cursor] = override_get_cursor

        response = client.get(
            "/v1/deployments/history",
            params={
                "name": "non-existent",
                "environment": "production",
                "provider": "gcp",
                "cloud_account_id": "project-123",
                "region": "us-central1",
            },
        )

        assert response.status_code == 200
        assert response.json() == []

        app.dependency_overrides.clear()


class TestRollback:
    """Tests for POST /v1/deployments/rollback endpoint."""

    def test_rollback(self, client: TestClient):
        mock_rows = [
            create_mock_deployment_row(id="uuid-1", version="2.0.0"),
            create_mock_deployment_row(id="uuid-2", version="1.0.0"),
        ]
        new_deployment = create_mock_deployment_row(
            id="uuid-3", version="1.0.0", auto=False, notes="Rollback to version 1.0.0"
        )
        mock_cursor = MockCursor(mock_rows + [new_deployment])

        def override_get_cursor():
            yield mock_cursor

        app.dependency_overrides[get_cursor] = override_get_cursor

        response = client.post(
            "/v1/deployments/rollback",
            params={
                "name": "test-service",
                "environment": "production",
                "provider": "gcp",
                "cloud_account_id": "project-123",
                "region": "us-central1",
            },
            json={},
        )

        assert response.status_code == 201

        app.dependency_overrides.clear()

    def test_rollback_to_version(self, client: TestClient):
        target_deployment = create_mock_deployment_row(id="uuid-old", version="1.5.0")
        new_deployment = create_mock_deployment_row(
            id="uuid-new", version="1.5.0", auto=False, notes="Rollback to version 1.5.0"
        )
        mock_cursor = MockCursor([target_deployment, new_deployment])

        def override_get_cursor():
            yield mock_cursor

        app.dependency_overrides[get_cursor] = override_get_cursor

        response = client.post(
            "/v1/deployments/rollback",
            params={
                "name": "test-service",
                "environment": "production",
                "provider": "gcp",
                "cloud_account_id": "project-123",
                "region": "us-central1",
            },
            json={"target_version": "1.5.0"},
        )

        assert response.status_code == 201

        app.dependency_overrides.clear()

    def test_rollback_no_previous(self, client: TestClient):
        mock_cursor = MockCursor([
            create_mock_deployment_row(id="uuid-1", version="1.0.0"),
        ])

        def override_get_cursor():
            yield mock_cursor

        app.dependency_overrides[get_cursor] = override_get_cursor

        response = client.post(
            "/v1/deployments/rollback",
            params={
                "name": "test-service",
                "environment": "production",
                "provider": "gcp",
                "cloud_account_id": "project-123",
                "region": "us-central1",
            },
            json={},
        )

        assert response.status_code == 404
        assert "No previous deployment found" in response.json()["detail"]

        app.dependency_overrides.clear()

    def test_rollback_version_not_found(self, client: TestClient):
        mock_cursor = MockCursor([])

        def override_get_cursor():
            yield mock_cursor

        app.dependency_overrides[get_cursor] = override_get_cursor

        response = client.post(
            "/v1/deployments/rollback",
            params={
                "name": "test-service",
                "environment": "production",
                "provider": "gcp",
                "cloud_account_id": "project-123",
                "region": "us-central1",
            },
            json={"target_version": "0.0.1"},
        )

        assert response.status_code == 404
        assert "No deployment found with version" in response.json()["detail"]

        app.dependency_overrides.clear()
