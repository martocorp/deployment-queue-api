"""Pytest fixtures for the Deployment Queue API tests."""

from datetime import UTC, datetime
from typing import Generator

import pytest
from fastapi.testclient import TestClient

from deployment_queue.auth import TokenPayload, verify_token
from deployment_queue.database import get_cursor
from deployment_queue.main import app


class MockCursor:
    """Mock Snowflake cursor for testing."""

    def __init__(self, data: list[dict] | None = None):
        self.data = data or []
        self.index = 0
        self.executed_queries: list[str] = []
        self.executed_params: list[dict | None] = []

    def execute(self, query: str, params: dict | None = None) -> None:
        self.executed_queries.append(query)
        self.executed_params.append(params)
        # Don't reset index - allows sequential fetchone calls across executes

    def fetchone(self) -> dict | None:
        if self.data and self.index < len(self.data):
            result = self.data[self.index]
            self.index += 1
            return result
        return None

    def fetchall(self) -> list[dict]:
        return self.data

    def close(self) -> None:
        pass

    def __enter__(self) -> "MockCursor":
        return self

    def __exit__(self, *args: object) -> None:
        pass


def create_mock_deployment_row(
    id: str = "test-uuid",
    organisation: str = "test-org",
    name: str = "test-service",
    version: str = "1.0.0",
    environment: str = "production",
    provider: str = "gcp",
    deployment_type: str = "k8s",
    status: str = "scheduled",
    cloud_account_id: str = "project-123",
    region: str = "us-central1",
    cell_id: str | None = None,
    auto: bool = True,
    notes: str | None = None,
    trigger: str = "auto",
    source_deployment_id: str | None = None,
    rollback_from_deployment_id: str | None = None,
    created_by_repo: str = "test-org/test-repo",
    created_by_workflow: str = "deploy.yml",
    created_by_actor: str = "test-user",
) -> dict:
    """Create a mock deployment row with uppercase keys (Snowflake style)."""
    now = datetime.now(UTC)
    return {
        "ID": id,
        "CREATED_AT": now,
        "UPDATED_AT": now,
        "ORGANISATION": organisation,
        "NAME": name,
        "VERSION": version,
        "COMMIT_SHA": "abc123",
        "PIPELINE_EXTRA_PARAMS": None,
        "PROVIDER": provider,
        "CLOUD_ACCOUNT_ID": cloud_account_id,
        "REGION": region,
        "ENVIRONMENT": environment,
        "CELL_ID": cell_id,
        "TYPE": deployment_type,
        "STATUS": status,
        "AUTO": auto,
        "DESCRIPTION": "Test deployment",
        "NOTES": notes,
        "TRIGGER": trigger,
        "SOURCE_DEPLOYMENT_ID": source_deployment_id,
        "ROLLBACK_FROM_DEPLOYMENT_ID": rollback_from_deployment_id,
        "BUILD_URI": "https://build.example.com/123",
        "DEPLOYMENT_URI": None,
        "RESOURCE": None,
        "CREATED_BY_REPO": created_by_repo,
        "CREATED_BY_WORKFLOW": created_by_workflow,
        "CREATED_BY_ACTOR": created_by_actor,
    }


@pytest.fixture
def mock_token() -> TokenPayload:
    """Mock token for testing."""
    return TokenPayload(
        organisation="test-org",
        source="test",
        repository="test-org/test-repo",
        workflow="test.yml",
        actor="test-user",
    )


@pytest.fixture
def mock_other_org_token() -> TokenPayload:
    """Mock token for different organisation (isolation testing)."""
    return TokenPayload(
        organisation="other-org",
        source="test",
        repository="other-org/other-repo",
        workflow="test.yml",
        actor="other-user",
    )


@pytest.fixture
def mock_cursor_empty(mock_token: TokenPayload) -> Generator[MockCursor, None, None]:
    """Fixture for mock cursor with no data."""
    mock = MockCursor([])

    def override_get_cursor() -> Generator[MockCursor, None, None]:
        yield mock

    app.dependency_overrides[get_cursor] = override_get_cursor
    app.dependency_overrides[verify_token] = lambda: mock_token
    yield mock
    app.dependency_overrides.clear()


@pytest.fixture
def mock_cursor_single(mock_token: TokenPayload) -> Generator[MockCursor, None, None]:
    """Fixture for mock cursor with a single deployment."""
    mock = MockCursor([create_mock_deployment_row()])

    def override_get_cursor() -> Generator[MockCursor, None, None]:
        yield mock

    app.dependency_overrides[get_cursor] = override_get_cursor
    app.dependency_overrides[verify_token] = lambda: mock_token
    yield mock
    app.dependency_overrides.clear()


@pytest.fixture
def mock_cursor_multiple(mock_token: TokenPayload) -> Generator[MockCursor, None, None]:
    """Fixture for mock cursor with multiple deployments."""
    mock = MockCursor([
        create_mock_deployment_row(id="uuid-1", version="1.0.0"),
        create_mock_deployment_row(id="uuid-2", version="2.0.0"),
        create_mock_deployment_row(id="uuid-3", version="3.0.0"),
    ])

    def override_get_cursor() -> Generator[MockCursor, None, None]:
        yield mock

    app.dependency_overrides[get_cursor] = override_get_cursor
    app.dependency_overrides[verify_token] = lambda: mock_token
    yield mock
    app.dependency_overrides.clear()


@pytest.fixture
def client(mock_token: TokenPayload) -> Generator[TestClient, None, None]:
    """Test client with mocked auth."""
    app.dependency_overrides[verify_token] = lambda: mock_token
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def client_other_org(
    mock_other_org_token: TokenPayload
) -> Generator[TestClient, None, None]:
    """Test client for different organisation."""
    app.dependency_overrides[verify_token] = lambda: mock_other_org_token
    yield TestClient(app)
    app.dependency_overrides.clear()
