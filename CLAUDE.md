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

### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check (no auth required) |
| `GET` | `/v1/deployments` | List deployments with filters |
| `POST` | `/v1/deployments` | Create a new deployment |
| `PATCH` | `/v1/deployments/{id}` | Update deployment status |
| `POST` | `/v1/deployments/{id}/rollback` | Create rollback deployment from a specific deployment |

### Authentication & Multi-Tenancy

The API supports two authentication methods:

1. **GitHub OIDC (GitHub Actions)**: JWT from GitHub Actions in `Authorization: Bearer <jwt>`. Organisation extracted from token's `repository_owner` claim.

2. **GitHub PAT (CLI)**: Personal Access Token in `Authorization: Bearer <pat>` with `X-Organisation: <org>` header. Organisation verified via GitHub API membership check.

- **auth.py**: Unified authentication supporting both OIDC and PAT. `verify_token()` is the FastAPI dependency that returns a `TokenPayload` with organisation and audit info.
- **Multi-tenancy**: All database queries are automatically filtered by organisation.
- **Tenant isolation**: Users can only access deployments belonging to their organisation.
- **Caching**: JWKS cached for 1 hour, org membership cached for 5 minutes.

### Core Concept: Taxonomy

Deployments are uniquely identified by a "taxonomy" - a combination of: `organisation` + `name` + `provider` + `cloud_account_id` + `region` + `cell`. The `list_deployments` endpoint supports filtering by any combination of these fields (organisation is always from the token).

### Auto-Skip Behavior

When a deployment is marked as `deployed`, scheduled deployments for the same taxonomy with semantically **older versions** are automatically marked as `skipped`. This uses semantic versioning comparison (e.g., `1.2.3 < 1.3.0 < 2.0.0`). Deployments with newer versions remain scheduled. This happens in `_skip_older_version_deployments()`.

### Deployment Lineage

Deployments track their lineage for rollback traceability:
- **trigger**: `manual`, `auto`, or `rollback`
- **source_deployment_id**: For rollbacks, points to the successful deployment being copied from
- **rollback_from_deployment_id**: For rollbacks, points to the failed deployment being rolled back

### Rollback Behavior

When `POST /v1/deployments/{id}/rollback` is called:
1. The deployment with the given ID (the failed one) is marked as `rolled_back`
2. The API finds the latest successful (`deployed`) deployment for the same taxonomy
3. A new deployment is created copying from that successful deployment
4. The new deployment is automatically set to `in_progress` (auto-release)
5. The `_execute_release()` function is called with `operation="rollback"`

### Release Logic

The `_execute_release()` function is a placeholder for type-specific deployment logic. It is called whenever a deployment transitions to `in_progress`:

- **Regular release**: When `PATCH /v1/deployments/{id}` sets `status=in_progress`, called with `operation="release"`
- **Rollback release**: After rollback creates a new deployment, called with `operation="rollback"`

The function receives:
- `deployment_row`: Full deployment data (UPPERCASE keys from Snowflake), including `TYPE`
- `operation`: Either `"release"` or `"rollback"`

This allows implementing type-specific logic (e.g., trigger different pipelines for `k8s`, `terraform`, `data_pipeline`).

### Module Structure

- **main.py**: All FastAPI endpoints. Uses `get_cursor` and `verify_token` as FastAPI dependencies. Key endpoints: `list_deployments` (with taxonomy filters), `create_deployment`, `update_deployment` (with auto-skip logic), and `rollback_deployment`.

- **auth.py**: Unified authentication supporting GitHub OIDC and PAT. Key functions:
  - `verify_token()`: Main FastAPI dependency, auto-detects token type
  - `_verify_github_oidc_token()`: JWT verification against GitHub's JWKS
  - `_verify_github_pat()`: PAT verification via GitHub API with org membership check
  - `_is_jwt_token()`: Detects JWT vs PAT format

- **models.py**: Pydantic models and enums. `row_to_deployment()` converts Snowflake rows (UPPERCASE keys) to Deployment models. Includes `DeploymentTrigger` enum for lineage tracking.

- **database.py**: Snowflake connection handling. `get_cursor()` is a generator that yields a DictCursor and handles commit/rollback.

- **config.py**: Settings via pydantic-settings with lazy loading (`get_settings()` with `@lru_cache`). Includes auth settings: `auth_enabled`, `github_oidc_issuer`, `github_oidc_audience`, `github_api_url`, `allowed_organisations`, `jwks_cache_ttl`, `org_membership_cache_ttl`.

### Database Notes

- Snowflake returns column names in UPPERCASE - use `row["COLUMN_NAME"]` when reading
- Use parameterized queries with `%(param)s` syntax for all user input
- NULL comparisons in SQL require `IS NULL`, not `= NULL`
- All queries must include `organisation = %(organisation)s` for tenant isolation

### Testing Pattern

Tests use FastAPI dependency overrides to mock both database cursor and authentication:

```python
def override_get_cursor():
    yield mock_cursor

app.dependency_overrides[get_cursor] = override_get_cursor
app.dependency_overrides[verify_token] = lambda: mock_token
# ... run test ...
app.dependency_overrides.clear()
```

The `MockCursor` class in conftest.py simulates Snowflake's DictCursor. Mock data uses UPPERCASE keys to match Snowflake behavior. The `mock_token` and `mock_other_org_token` fixtures test multi-tenancy isolation.
