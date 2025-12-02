"""Pytest fixtures for the Deployment Queue API tests."""

from datetime import UTC, datetime
from typing import Generator

import pytest
from fastapi.testclient import TestClient

from deployment_queue.main import app, get_cursor


class MockCursor:
    """Mock Snowflake cursor for testing."""

    def __init__(self, data: list[dict] = None):
        self.data = data or []
        self.index = 0
        self.executed_queries = []
        self.executed_params = []

    def execute(self, query: str, params: dict = None):
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

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def create_mock_deployment_row(
    id: str = "test-uuid",
    name: str = "test-service",
    version: str = "1.0.0",
    environment: str = "production",
    provider: str = "gcp",
    type: str = "k8s",
    status: str = "scheduled",
    cloud_account_id: str = "project-123",
    region: str = "us-central1",
    cell: str = None,
    auto: bool = True,
    notes: str = None,
) -> dict:
    """Create a mock deployment row with uppercase keys (Snowflake style)."""
    now = datetime.now(UTC)
    return {
        "ID": id,
        "CREATED_AT": now,
        "UPDATED_AT": now,
        "NAME": name,
        "VERSION": version,
        "COMMIT_SHA": "abc123",
        "PIPELINE_EXTRA_PARAMS": None,
        "PROVIDER": provider,
        "CLOUD_ACCOUNT_ID": cloud_account_id,
        "REGION": region,
        "ENVIRONMENT": environment,
        "CELL": cell,
        "TYPE": type,
        "STATUS": status,
        "AUTO": auto,
        "DESCRIPTION": "Test deployment",
        "NOTES": notes,
        "BUILD_URI": "https://build.example.com/123",
        "DEPLOYMENT_URI": None,
        "RESOURCE": None,
    }


@pytest.fixture
def mock_cursor_empty() -> Generator[MockCursor, None, None]:
    """Fixture for mock cursor with no data."""
    mock = MockCursor([])

    def override_get_cursor():
        yield mock

    app.dependency_overrides[get_cursor] = override_get_cursor
    yield mock
    app.dependency_overrides.clear()


@pytest.fixture
def mock_cursor_single() -> Generator[MockCursor, None, None]:
    """Fixture for mock cursor with a single deployment."""
    mock = MockCursor([create_mock_deployment_row()])

    def override_get_cursor():
        yield mock

    app.dependency_overrides[get_cursor] = override_get_cursor
    yield mock
    app.dependency_overrides.clear()


@pytest.fixture
def mock_cursor_multiple() -> Generator[MockCursor, None, None]:
    """Fixture for mock cursor with multiple deployments."""
    mock = MockCursor([
        create_mock_deployment_row(id="uuid-1", version="1.0.0"),
        create_mock_deployment_row(id="uuid-2", version="2.0.0"),
        create_mock_deployment_row(id="uuid-3", version="3.0.0"),
    ])

    def override_get_cursor():
        yield mock

    app.dependency_overrides[get_cursor] = override_get_cursor
    yield mock
    app.dependency_overrides.clear()


@pytest.fixture
def client() -> TestClient:
    """Fixture for FastAPI test client."""
    return TestClient(app)
