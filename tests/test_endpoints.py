"""Tests for API endpoints."""

from typing import Generator

from fastapi.testclient import TestClient

from deployment_queue.auth import TokenPayload, verify_token
from deployment_queue.database import get_cursor
from deployment_queue.main import app

from .conftest import MockCursor, create_mock_deployment_row


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
                        "cell": "cell-1",
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
            params={"status": "scheduled", "provider": "gcp"},
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
        assert '"trigger" = %(trigger)s' in mock_cursor_single.executed_queries[0]

    def test_list_deployments_filter_by_taxonomy(
        self, mock_cursor_single: MockCursor, client: TestClient
    ) -> None:
        """Can filter by full taxonomy fields."""
        response = client.get(
            "/v1/deployments",
            params={
                "name": "test-service",
                "provider": "gcp",
                "cloud_account_id": "project-123",
                "region": "us-central1",
            },
        )
        assert response.status_code == 200
        query = mock_cursor_single.executed_queries[0]
        assert "name = %(name)s" in query
        assert "provider = %(provider)s" in query
        assert "cloud_account_id = %(cloud_account_id)s" in query
        assert "region = %(region)s" in query

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

    def test_update_deployment_skips_all_scheduled_when_deployed(
        self, mock_token: TokenPayload
    ) -> None:
        """When marked as deployed, all scheduled deployments are skipped."""
        mock = MockCursor([
            create_mock_deployment_row(),  # SELECT * to get full row
            create_mock_deployment_row(status="deployed"),  # Final SELECT
        ])

        def override_get_cursor() -> Generator[MockCursor, None, None]:
            yield mock

        app.dependency_overrides[get_cursor] = override_get_cursor
        app.dependency_overrides[verify_token] = lambda: mock_token

        try:
            with TestClient(app) as client:
                response = client.patch(
                    "/v1/deployments/test-uuid",
                    json={"status": "deployed"},
                )
                assert response.status_code == 200
                # Verify skip query was executed (3rd query after SELECT *, UPDATE)
                assert len(mock.executed_queries) >= 3
                skip_query = mock.executed_queries[2]
                assert "UPDATE deployments" in skip_query
                assert "status = 'skipped'" in skip_query
                assert "status = 'scheduled'" in skip_query
                assert "id != %(id)s" in skip_query
        finally:
            app.dependency_overrides.clear()

    def test_update_deployment_no_skip_when_failed(
        self, mock_token: TokenPayload
    ) -> None:
        """When marked as failed, older deployments are NOT skipped."""
        mock = MockCursor([
            create_mock_deployment_row(),
            create_mock_deployment_row(status="failed"),
        ])

        def override_get_cursor() -> Generator[MockCursor, None, None]:
            yield mock

        app.dependency_overrides[get_cursor] = override_get_cursor
        app.dependency_overrides[verify_token] = lambda: mock_token

        try:
            with TestClient(app) as client:
                response = client.patch(
                    "/v1/deployments/test-uuid",
                    json={"status": "failed"},
                )
                assert response.status_code == 200
                # Only 3 queries: SELECT *, UPDATE, SELECT *
                # No skip query because status is not 'deployed'
                assert len(mock.executed_queries) == 3
                # Verify no skip query (UPDATE with 'skipped')
                for query in mock.executed_queries:
                    if "UPDATE" in query and "skipped" in query:
                        raise AssertionError("Skip query should not be executed for failed status")
        finally:
            app.dependency_overrides.clear()


class TestRollback:
    """Tests for POST /v1/deployments/{id}/rollback endpoint."""

    def test_rollback(self, mock_token: TokenPayload) -> None:
        """Rollback creates new deployment with lineage fields."""
        # Mock data sequence for fetchone calls:
        # - Query 1: fetchone() returns source deployment (uuid-source)
        # - Query 2: fetchone() returns most recent deployment (uuid-current)
        # - Query 3: INSERT (no fetch)
        # - Query 4: UPDATE to mark rollback_from as rolled_back (no fetch)
        # - Query 5: fetchone() returns the new rollback deployment
        mock = MockCursor([
            create_mock_deployment_row(id="uuid-source", version="1.0.0"),  # Source deployment
            create_mock_deployment_row(id="uuid-current", version="2.0.0"),  # Current/most recent
            create_mock_deployment_row(
                id="uuid-new",
                version="1.0.0",
                trigger="rollback",
                source_deployment_id="uuid-source",
                rollback_from_deployment_id="uuid-current",
            ),  # New rollback deployment returned
        ])

        def override_get_cursor() -> Generator[MockCursor, None, None]:
            yield mock

        app.dependency_overrides[get_cursor] = override_get_cursor
        app.dependency_overrides[verify_token] = lambda: mock_token

        try:
            with TestClient(app) as client:
                response = client.post("/v1/deployments/uuid-source/rollback")
                assert response.status_code == 201
                # Verify INSERT was called with rollback trigger
                insert_params = mock.executed_params[2]  # Third query is the INSERT
                assert insert_params["trigger"] == "rollback"
                assert insert_params["source_deployment_id"] == "uuid-source"
                # Verify UPDATE was called to mark rollback_from deployment as rolled_back
                update_params = mock.executed_params[3]  # Fourth query is the UPDATE
                assert update_params["status"] == "rolled_back"
                assert update_params["id"] == "uuid-current"
                # Response comes from mock data
                data = response.json()
                assert data["trigger"] == "rollback"
                assert data["source_deployment_id"] == "uuid-source"
                assert data["rollback_from_deployment_id"] == "uuid-current"
        finally:
            app.dependency_overrides.clear()

    def test_rollback_not_found(self, mock_token: TokenPayload) -> None:
        """Rollback fails when deployment ID doesn't exist."""
        mock = MockCursor([])

        def override_get_cursor() -> Generator[MockCursor, None, None]:
            yield mock

        app.dependency_overrides[get_cursor] = override_get_cursor
        app.dependency_overrides[verify_token] = lambda: mock_token

        try:
            with TestClient(app) as client:
                response = client.post("/v1/deployments/nonexistent-uuid/rollback")
                assert response.status_code == 404
                assert "Deployment not found" in response.json()["detail"]
        finally:
            app.dependency_overrides.clear()
