# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build and Development Commands

```bash
make init          # Set up venv and install dependencies (run first)
make test          # Run tests with coverage report
make lint          # Run ruff linter and mypy type checker
make format        # Auto-format code with ruff
make build         # Full build: lint, test, security scan, package
make run           # Start dev server (uvicorn with reload)
make security      # Run bandit security scan
make clean         # Remove build artifacts and caches
```

**Run a single test:**
```bash
. .venv/bin/activate && PYTHONPATH=src/ pytest tests/test_endpoints.py::TestCreateDeployment::test_create_deployment -v
```

## Architecture Overview

This is a FastAPI REST API for tracking deployment lifecycle across cloud providers (GCP, AWS, Azure), using Snowflake as the database.

### Core Concept: Taxonomy

Deployments are uniquely identified by a "taxonomy" - a combination of: `name` + `environment` + `provider` + `cloud_account_id` + `region` + `cell`. The taxonomy-based endpoints (`/current`, `/history`, `/rollback`) use this to find deployments without needing the deployment ID.

### Module Structure

- **main.py**: All FastAPI endpoints. Uses `get_cursor` as a FastAPI dependency for database access. The `build_taxonomy_where_clause()` helper constructs SQL WHERE clauses for taxonomy queries.

- **models.py**: Pydantic models and enums. `row_to_deployment()` converts Snowflake rows (UPPERCASE keys) to Deployment models.

- **database.py**: Snowflake connection handling. `get_cursor()` is a generator that yields a DictCursor and handles commit/rollback.

- **config.py**: Settings via pydantic-settings with lazy loading (`get_settings()` with `@lru_cache`).

### Database Notes

- Snowflake returns column names in UPPERCASE - use `row["COLUMN_NAME"]` when reading
- Use parameterized queries with `%(param)s` syntax for all user input
- NULL comparisons in SQL require `IS NULL`, not `= NULL` (see `build_taxonomy_where_clause`)

### Testing Pattern

Tests use FastAPI dependency overrides to mock the database cursor:

```python
def override_get_cursor():
    yield mock_cursor

app.dependency_overrides[get_cursor] = override_get_cursor
# ... run test ...
app.dependency_overrides.clear()
```

The `MockCursor` class in conftest.py simulates Snowflake's DictCursor. Mock data uses UPPERCASE keys to match Snowflake behavior.
