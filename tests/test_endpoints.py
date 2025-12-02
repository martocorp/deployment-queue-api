"""Tests for API endpoints."""

from typing import Generator

from fastapi.testclient import TestClient

from deployment_queue.auth import TokenPayload, verify_token
from deployment_queue.database import get_cursor
from deployment_queue.main import app

from .conftest import MockCursor, create_mock_deployment_row


class TestHealthCheck:
    """Tests for health check endpoint."""

    def test_health_check_no_auth(self) -> None:
        """Health check works without authentication."""
        with TestClient(app) as client:
            response = client.get("/health")
            assert response.status_code == 200
            assert response.json() == {"status": "healthy"}


class TestCreateDeployment:
    """Tests for POST /v1/deployments endpoint."""

    def test_create_deployment(
        self, mock_cursor_single: MockCursor, client: TestClient
    ) -> None:
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
        assert data["organisation"] == "test-org"
        assert data["trigger"] == "auto"
        assert data["status"] == "scheduled"

    def test_create_deployment_with_all_fields(
        self, mock_token: TokenPayload
    ) -> None:
        """Create deployment with auto=False sets trigger to manual."""
        mock = MockCursor([
            create_mock_deployment_row(
                trigger="manual",
                auto=False,
            ),
        ])

        def override_get_cursor() -> Generator[MockCursor, None, None]:
            yield mock

        app.dependency_overrides[get_cursor] = override_get_cursor
        app.dependency_overrides[verify_token] = lambda: mock_token

        try:
            with TestClient(app) as client:
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
                        "cell_id": "cell-1",
                        "type": "terraform",
                        "auto": False,
                        "description": "Test deployment",
                        "notes": "Some notes",
                        "build_uri": "https://build.example.com",
                        "deployment_uri": "https://deploy.example.com",
                        "resource": "arn:aws:lambda:us-east-1:123456789:function:test",
                    },
                )
                assert response.status_code == 201
                data = response.json()
                # Verify the INSERT used the correct trigger value
                assert "trigger" in mock.executed_params[0]
                assert mock.executed_params[0]["trigger"] == "manual"
                # Response comes from mock data
                assert data["trigger"] == "manual"
        finally:
            app.dependency_overrides.clear()

    def test_create_deployment_audit_fields(
        self, mock_cursor_single: MockCursor, client: TestClient
    ) -> None:
        """Audit fields are populated from token."""
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
        assert data["created_by_repo"] == "test-org/test-repo"
        assert data["created_by_workflow"] == "deploy.yml"
        assert data["created_by_actor"] == "test-user"

    def test_create_deployment_invalid_provider(
        self, mock_token: TokenPayload
    ) -> None:
        mock = MockCursor([])

        def override_get_cursor() -> Generator[MockCursor, None, None]:
            yield mock

        app.dependency_overrides[get_cursor] = override_get_cursor
        app.dependency_overrides[verify_token] = lambda: mock_token
        try:
            with TestClient(app) as client:
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
        finally:
            app.dependency_overrides.clear()


class TestListDeployments:
    """Tests for GET /v1/deployments endpoint."""

    def test_list_deployments(
        self, mock_cursor_multiple: MockCursor, client: TestClient
    ) -> None:
        response = client.get("/v1/deployments")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3

    def test_list_deployments_with_filters(
        self, mock_cursor_single: MockCursor, client: TestClient
    ) -> None:
        response = client.get(
            "/v1/deployments",
            params={"status": "scheduled", "environment": "production", "provider": "gcp"},
        )
        assert response.status_code == 200
        assert "status = %(status)s" in mock_cursor_single.executed_queries[0]

    def test_list_deployments_empty(
        self, mock_cursor_empty: MockCursor, client: TestClient
    ) -> None:
        response = client.get("/v1/deployments")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_deployments_filter_by_trigger(
        self, mock_cursor_single: MockCursor, client: TestClient
    ) -> None:
        response = client.get("/v1/deployments", params={"trigger": "rollback"})
        assert response.status_code == 200
        assert "trigger = %(trigger)s" in mock_cursor_single.executed_queries[0]

    def test_list_deployments_isolated(
        self,
        mock_token: TokenPayload,
        mock_other_org_token: TokenPayload,
    ) -> None:
        """Deployments from other orgs not visible in list."""
        mock = MockCursor([create_mock_deployment_row(organisation="test-org")])

        def override_get_cursor() -> Generator[MockCursor, None, None]:
            yield mock

        app.dependency_overrides[get_cursor] = override_get_cursor
        app.dependency_overrides[verify_token] = lambda: mock_other_org_token

        try:
            with TestClient(app) as client:
                response = client.get("/v1/deployments")
                assert response.status_code == 200
                assert "organisation = %(organisation)s" in mock.executed_queries[0]
                params = mock.executed_params[0]
                assert params is not None
                assert params["organisation"] == "other-org"
        finally:
            app.dependency_overrides.clear()


class TestGetDeployment:
    """Tests for GET /v1/deployments/{id} endpoint."""

    def test_get_deployment(
        self, mock_cursor_single: MockCursor, client: TestClient
    ) -> None:
        response = client.get("/v1/deployments/test-uuid")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "test-uuid"

    def test_get_deployment_not_found(
        self, mock_cursor_empty: MockCursor, client: TestClient
    ) -> None:
        response = client.get("/v1/deployments/nonexistent")
        assert response.status_code == 404

    def test_get_deployment_wrong_org(
        self,
        mock_other_org_token: TokenPayload,
    ) -> None:
        """Deployment from other org returns 404."""
        mock = MockCursor([create_mock_deployment_row(organisation="test-org")])

        def override_get_cursor() -> Generator[MockCursor, None, None]:
            yield mock

        app.dependency_overrides[get_cursor] = override_get_cursor
        app.dependency_overrides[verify_token] = lambda: mock_other_org_token

        try:
            with TestClient(app) as client:
                client.get("/v1/deployments/test-uuid")
                assert "organisation = %(organisation)s" in mock.executed_queries[0]
        finally:
            app.dependency_overrides.clear()


class TestUpdateDeployment:
    """Tests for PATCH /v1/deployments/{id} endpoint."""

    def test_update_deployment(
        self, mock_token: TokenPayload
    ) -> None:
        mock = MockCursor([
            create_mock_deployment_row(),
            create_mock_deployment_row(status="deployed"),
        ])

        def override_get_cursor() -> Generator[MockCursor, None, None]:
            yield mock

        app.dependency_overrides[get_cursor] = override_get_cursor
        app.dependency_overrides[verify_token] = lambda: mock_token

        try:
            with TestClient(app) as client:
                response = client.patch(
                    "/v1/deployments/test-uuid",
                    json={"status": "deployed", "notes": "Deployment complete"},
                )
                assert response.status_code == 200
        finally:
            app.dependency_overrides.clear()

    def test_update_deployment_not_found(
        self, mock_cursor_empty: MockCursor, client: TestClient
    ) -> None:
        response = client.patch(
            "/v1/deployments/nonexistent",
            json={"status": "deployed"},
        )
        assert response.status_code == 404

    def test_update_deployment_no_fields(
        self, mock_cursor_single: MockCursor, client: TestClient
    ) -> None:
        response = client.patch("/v1/deployments/test-uuid", json={})
        assert response.status_code == 400
        assert "No fields to update" in response.json()["detail"]


class TestGetCurrentDeployment:
    """Tests for GET /v1/deployments/current endpoint."""

    def test_get_current_deployment(
        self, mock_cursor_single: MockCursor, client: TestClient
    ) -> None:
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

    def test_get_current_deployment_with_cell(
        self, mock_cursor_single: MockCursor, client: TestClient
    ) -> None:
        response = client.get(
            "/v1/deployments/current",
            params={
                "name": "test-service",
                "environment": "production",
                "provider": "gcp",
                "cloud_account_id": "project-123",
                "region": "us-central1",
                "cell_id": "cell-1",
            },
        )
        assert response.status_code == 200
        assert "cell_id = %(cell_id)s" in mock_cursor_single.executed_queries[0]

    def test_get_current_deployment_not_found(
        self, mock_cursor_empty: MockCursor, client: TestClient
    ) -> None:
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
        assert response.json() is None


class TestUpdateStatusByTaxonomy:
    """Tests for PATCH /v1/deployments/current/status endpoint."""

    def test_update_status_by_taxonomy(
        self, mock_token: TokenPayload
    ) -> None:
        mock = MockCursor([
            create_mock_deployment_row(),
            create_mock_deployment_row(status="deployed"),
        ])

        def override_get_cursor() -> Generator[MockCursor, None, None]:
            yield mock

        app.dependency_overrides[get_cursor] = override_get_cursor
        app.dependency_overrides[verify_token] = lambda: mock_token

        try:
            with TestClient(app) as client:
                response = client.patch(
                    "/v1/deployments/current/status",
                    params={
                        "name": "test-service",
                        "environment": "production",
                        "provider": "gcp",
                        "cloud_account_id": "project-123",
                        "region": "us-central1",
                        "new_status": "deployed",
                    },
                )
                assert response.status_code == 200
        finally:
            app.dependency_overrides.clear()

    def test_update_status_not_found(
        self, mock_cursor_empty: MockCursor, client: TestClient
    ) -> None:
        response = client.patch(
            "/v1/deployments/current/status",
            params={
                "name": "test-service",
                "environment": "production",
                "provider": "gcp",
                "cloud_account_id": "project-123",
                "region": "us-central1",
                "new_status": "deployed",
            },
        )
        assert response.status_code == 404


class TestDeploymentHistory:
    """Tests for GET /v1/deployments/history endpoint."""

    def test_deployment_history(
        self, mock_cursor_multiple: MockCursor, client: TestClient
    ) -> None:
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

    def test_deployment_history_empty(
        self, mock_cursor_empty: MockCursor, client: TestClient
    ) -> None:
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
        assert response.json() == []


class TestRollback:
    """Tests for POST /v1/deployments/rollback endpoint."""

    def test_rollback(self, mock_token: TokenPayload) -> None:
        """Rollback creates new deployment with lineage fields."""
        # Mock data sequence for fetchone/fetchall calls:
        # - Query 1: fetchone() returns data[0], index -> 1
        # - Query 2: fetchall() returns ALL data (used by API as rows[1] for rollback source)
        # - Query 3: INSERT (no fetch)
        # - Query 4: fetchone() returns data[1], index -> 2
        #
        # So data[1] must be the new rollback deployment that gets returned
        mock = MockCursor([
            create_mock_deployment_row(id="uuid-1", version="2.0.0"),  # Current (fetchone q1)
            create_mock_deployment_row(
                id="uuid-3",
                version="1.0.0",
                trigger="rollback",
                source_deployment_id="uuid-2",
                rollback_from_deployment_id="uuid-1",
            ),  # New deployment returned by final fetchone (q4)
            create_mock_deployment_row(id="uuid-2", version="1.0.0"),  # Rollback source
        ])

        def override_get_cursor() -> Generator[MockCursor, None, None]:
            yield mock

        app.dependency_overrides[get_cursor] = override_get_cursor
        app.dependency_overrides[verify_token] = lambda: mock_token

        try:
            with TestClient(app) as client:
                response = client.post(
                    "/v1/deployments/rollback",
                    params={
                        "name": "test-service",
                        "environment": "production",
                        "provider": "gcp",
                        "cloud_account_id": "project-123",
                        "region": "us-central1",
                    },
                )
                assert response.status_code == 201
                # Verify INSERT was called with rollback trigger
                insert_params = mock.executed_params[2]  # Third query is the INSERT
                assert insert_params["trigger"] == "rollback"
                # Response comes from mock data
                data = response.json()
                assert data["trigger"] == "rollback"
                assert data["source_deployment_id"] == "uuid-2"
                assert data["rollback_from_deployment_id"] == "uuid-1"
        finally:
            app.dependency_overrides.clear()

    def test_rollback_to_version(self, mock_token: TokenPayload) -> None:
        """Rollback to specific version works."""
        mock = MockCursor([
            create_mock_deployment_row(id="uuid-1", version="2.0.0"),
            create_mock_deployment_row(id="uuid-2", version="1.5.0"),
            create_mock_deployment_row(
                id="uuid-3",
                version="1.5.0",
                trigger="rollback",
                source_deployment_id="uuid-2",
                rollback_from_deployment_id="uuid-1",
            ),
        ])

        def override_get_cursor() -> Generator[MockCursor, None, None]:
            yield mock

        app.dependency_overrides[get_cursor] = override_get_cursor
        app.dependency_overrides[verify_token] = lambda: mock_token

        try:
            with TestClient(app) as client:
                response = client.post(
                    "/v1/deployments/rollback",
                    params={
                        "name": "test-service",
                        "environment": "production",
                        "provider": "gcp",
                        "cloud_account_id": "project-123",
                        "region": "us-central1",
                        "target_version": "1.5.0",
                    },
                )
                assert response.status_code == 201
        finally:
            app.dependency_overrides.clear()

    def test_rollback_no_previous(self, mock_token: TokenPayload) -> None:
        """Rollback fails when no previous deployment exists."""
        mock = MockCursor([
            create_mock_deployment_row(id="uuid-1", version="1.0.0"),
        ])

        def override_get_cursor() -> Generator[MockCursor, None, None]:
            yield mock

        app.dependency_overrides[get_cursor] = override_get_cursor
        app.dependency_overrides[verify_token] = lambda: mock_token

        try:
            with TestClient(app) as client:
                response = client.post(
                    "/v1/deployments/rollback",
                    params={
                        "name": "test-service",
                        "environment": "production",
                        "provider": "gcp",
                        "cloud_account_id": "project-123",
                        "region": "us-central1",
                    },
                )
                assert response.status_code == 404
                assert "No previous deployment" in response.json()["detail"]
        finally:
            app.dependency_overrides.clear()

    def test_rollback_version_not_found(self, mock_token: TokenPayload) -> None:
        """Rollback to nonexistent version fails."""
        mock = MockCursor([create_mock_deployment_row(id="uuid-1", version="2.0.0")])

        def override_get_cursor() -> Generator[MockCursor, None, None]:
            # First call returns current deployment, second (version search) returns empty
            mock.data = []
            yield mock

        app.dependency_overrides[get_cursor] = override_get_cursor
        app.dependency_overrides[verify_token] = lambda: mock_token

        try:
            with TestClient(app) as client:
                response = client.post(
                    "/v1/deployments/rollback",
                    params={
                        "name": "test-service",
                        "environment": "production",
                        "provider": "gcp",
                        "cloud_account_id": "project-123",
                        "region": "us-central1",
                        "target_version": "0.0.1",
                    },
                )
                assert response.status_code == 404
                assert "No deployment found with version" in response.json()["detail"]
        finally:
            app.dependency_overrides.clear()
