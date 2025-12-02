# Code Style Guide

This document outlines the coding standards and conventions used in the Deployment Queue API project.

## Table of Contents

- [General Principles](#general-principles)
- [Python Version](#python-version)
- [Code Formatting](#code-formatting)
- [Linting](#linting)
- [Type Hints](#type-hints)
- [Naming Conventions](#naming-conventions)
- [Project Structure](#project-structure)
- [Imports](#imports)
- [Documentation](#documentation)
- [Testing](#testing)
- [Error Handling](#error-handling)
- [Database](#database)

## General Principles

1. **Readability**: Code should be easy to read and understand
2. **Simplicity**: Prefer simple solutions over complex ones
3. **Consistency**: Follow established patterns throughout the codebase
4. **Explicit over implicit**: Be explicit about types, return values, and behavior

## Python Version

This project requires **Python 3.11+**. Use features available in Python 3.11 including:

- Type hint improvements (`list[T]` instead of `List[T]`)
- Union types with `|` operator
- `match` statements where appropriate

## Code Formatting

### Tools

- **Ruff**: Used for both linting and formatting
- Configuration is in `pyproject.toml`

### Line Length

Maximum line length is **100 characters**.

```toml
[tool.ruff]
line-length = 100
target-version = "py311"
```

### Running Formatters

```bash
make format
```

Or manually:

```bash
ruff check --fix src/ tests/
ruff format src/ tests/
```

## Linting

### Enabled Rules

The following Ruff rule sets are enabled:

- `E` - pycodestyle errors
- `F` - Pyflakes
- `I` - isort (import sorting)
- `W` - pycodestyle warnings

```toml
[tool.ruff.lint]
select = ["E", "F", "I", "W"]
```

### Running Linter

```bash
make lint
```

Or manually:

```bash
ruff check src/ tests/
mypy src/ --python-version 3.11 --ignore-missing-imports
```

## Type Hints

### Requirements

- All function parameters must have type hints
- All function return types must be annotated
- Use `Optional[T]` or `T | None` for nullable types

### Examples

```python
# Good
def get_deployment(deployment_id: str) -> Deployment:
    ...

def list_deployments(
    status: Optional[DeploymentStatus] = None,
    limit: int = 100,
) -> list[Deployment]:
    ...

# Bad - missing type hints
def get_deployment(deployment_id):
    ...
```

### Optional vs None Union

Prefer `Optional[T]` for consistency with the existing codebase:

```python
from typing import Optional

# Preferred in this project
def func(param: Optional[str] = None) -> Optional[str]:
    ...
```

## Naming Conventions

### Variables and Functions

- Use `snake_case` for variables and functions
- Use descriptive names that indicate purpose

```python
# Good
deployment_id = "abc-123"
cloud_account_id = "project-123"

def get_current_deployment() -> Deployment:
    ...

# Bad
id = "abc-123"  # Too generic, shadows builtin
d = "abc-123"   # Not descriptive

def get() -> Deployment:  # Not descriptive
    ...
```

### Classes

- Use `PascalCase` for class names
- Pydantic models should be nouns describing the data

```python
# Good
class Deployment(BaseModel):
    ...

class DeploymentCreate(BaseModel):
    ...

class DeploymentStatus(str, Enum):
    ...
```

### Constants

- Use `UPPER_SNAKE_CASE` for constants
- Define at module level

```python
DEFAULT_LIMIT = 100
MAX_LIMIT = 1000
```

### Enums

- Enum class names use `PascalCase`
- Enum values use `snake_case`

```python
class DeploymentStatus(str, Enum):
    scheduled = "scheduled"
    in_progress = "in_progress"
    deployed = "deployed"
```

## Project Structure

```
deployment-queue-api/
├── src/
│   └── deployment_queue/      # Main package
│       ├── __init__.py        # Package init with version
│       ├── main.py            # FastAPI app and endpoints
│       ├── models.py          # Pydantic models and enums
│       ├── database.py        # Database connection handling
│       └── config.py          # Settings via pydantic-settings
├── tests/
│   ├── __init__.py
│   ├── conftest.py            # Pytest fixtures
│   ├── test_endpoints.py      # API endpoint tests
│   └── test_models.py         # Model validation tests
├── scripts/
│   └── verify_connection.py   # Test Snowflake connection
├── sql/
│   └── schema.sql             # Database DDL
├── secrets/                   # Git-ignored, for local dev keys
│   └── .gitkeep
└── docs/
    ├── USAGE.md               # Usage documentation
    └── CODESTYLE.md           # This file
```

### Module Organization

- `main.py`: FastAPI app instance, endpoint definitions, dependency injection
- `models.py`: All Pydantic models, enums, and data conversion functions
- `database.py`: Database connection management and cursor handling
- `config.py`: Application settings using pydantic-settings

## Imports

### Order

Imports should be sorted in the following order (handled by Ruff):

1. Standard library imports
2. Third-party imports
3. Local application imports

```python
# Standard library
from datetime import datetime
from typing import Optional
from uuid import uuid4

# Third-party
from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel

# Local
from deployment_queue.database import get_cursor, get_db_connection
from deployment_queue.models import Deployment, DeploymentCreate
```

### Import Style

- Import specific items, not entire modules
- Group related imports on the same line when reasonable

```python
# Good
from deployment_queue.models import (
    Deployment,
    DeploymentCreate,
    DeploymentStatus,
    Provider,
)

# Avoid
from deployment_queue import models
# Then using: models.Deployment, models.DeploymentCreate
```

## Documentation

### Module Docstrings

Every module should have a docstring explaining its purpose:

```python
"""FastAPI application and endpoints for the Deployment Queue API."""
```

### Function Docstrings

Use docstrings for public functions. Keep them concise:

```python
def get_current_deployment(...) -> Deployment:
    """Get the current (most recent) deployment for a component by taxonomy."""
    ...
```

### Inline Comments

- Use sparingly and only when the code isn't self-explanatory
- Explain "why", not "what"

```python
# Handle NULL comparison for cell (SQL requires IS NULL, not = NULL)
if cell is None:
    where = "... AND cell IS NULL"
```

## Testing

### Test Structure

- Test files mirror source structure with `test_` prefix
- Test classes group related tests
- Test methods use descriptive names

```python
class TestCreateDeployment:
    """Tests for POST /v1/deployments endpoint."""

    def test_create_deployment(self, client: TestClient):
        ...

    def test_create_deployment_invalid_provider(self, client: TestClient):
        ...
```

### Fixtures

- Define reusable fixtures in `conftest.py`
- Use dependency override pattern for FastAPI testing

```python
@pytest.fixture
def client() -> TestClient:
    """Fixture for FastAPI test client."""
    return TestClient(app)
```

### Running Tests

```bash
make test
```

Or manually:

```bash
PYTHONPATH=src/ coverage run -m pytest tests/ -v
coverage report
coverage html --directory target/coverage
```

## Error Handling

### HTTP Exceptions

Use FastAPI's `HTTPException` with appropriate status codes:

```python
from fastapi import HTTPException

# 404 for not found
if not row:
    raise HTTPException(status_code=404, detail="Deployment not found")

# 400 for bad request
if not update_data:
    raise HTTPException(status_code=400, detail="No fields to update")
```

### Status Codes

- `200`: Success (GET, PATCH)
- `201`: Created (POST)
- `400`: Bad request (invalid input)
- `404`: Not found
- `422`: Validation error (automatic from Pydantic)

## Database

### Snowflake Conventions

- Snowflake returns column names in UPPERCASE
- Use a row mapper function to convert to Pydantic models:

```python
def row_to_deployment(row: dict) -> Deployment:
    """Convert a Snowflake row (uppercase keys) to a Deployment model."""
    return Deployment(
        id=row["ID"],
        name=row["NAME"],
        ...
    )
```

### NULL Handling

When comparing with NULL in SQL, use `IS NULL` not `= NULL`:

```python
if cell is None:
    where = "... AND cell IS NULL"
else:
    where = "... AND cell = %(cell)s"
```

### Parameterized Queries

Always use parameterized queries to prevent SQL injection:

```python
# Good
query = "SELECT * FROM deployments WHERE id = %(id)s"
cursor.execute(query, {"id": deployment_id})

# Bad - SQL injection risk
query = f"SELECT * FROM deployments WHERE id = '{deployment_id}'"
```

### Context Managers

Use context managers for database connections and cursors:

```python
with get_db_connection() as conn:
    with get_cursor(conn) as cursor:
        cursor.execute(query, params)
        row = cursor.fetchone()
```

## Security

### Security Scanning

Run Bandit for security analysis:

```bash
make security
```

### Sensitive Data

- Never commit `.env` files (they're in `.gitignore`)
- Use environment variables for all credentials
- Support both password and key-pair authentication for Snowflake
