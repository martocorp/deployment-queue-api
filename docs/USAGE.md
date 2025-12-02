# Usage Guide

This document provides detailed usage instructions for the Deployment Queue API.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Running the API](#running-the-api)
- [Authentication](#authentication)
- [API Endpoints](#api-endpoints)
- [Data Models](#data-models)
- [Examples](#examples)

## Prerequisites

- Python 3.11 or higher
- Snowflake account with key-pair authentication configured
- Docker (optional, for containerized deployment)

## Installation

### Using Make (Recommended)

```bash
make init
```

### Manual Installation

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install uv
uv pip install -e ".[dev]"
```

## Configuration

### 1. Create Environment File

```bash
cp .env.example .env
```

### 2. Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SNOWFLAKE_ACCOUNT` | Yes | - | Snowflake account identifier (e.g., `xy12345.eu-west-1`) |
| `SNOWFLAKE_USER` | Yes | - | Snowflake username |
| `SNOWFLAKE_PRIVATE_KEY_PATH` | No* | - | Path to RSA private key file |
| `SNOWFLAKE_PRIVATE_KEY_PASSPHRASE` | No | - | Passphrase for encrypted private key |
| `SNOWFLAKE_PASSWORD` | No* | - | Snowflake password (alternative to key-pair) |
| `SNOWFLAKE_WAREHOUSE` | No | `COMPUTE_WH` | Snowflake warehouse name |
| `SNOWFLAKE_DATABASE` | No | `DEPLOYMENTS_DB` | Snowflake database name |
| `SNOWFLAKE_SCHEMA` | No | `PUBLIC` | Snowflake schema name |
| `AUTH_ENABLED` | No | `true` | Enable/disable authentication |
| `GITHUB_OIDC_ISSUER` | No | `https://token.actions.githubusercontent.com` | GitHub OIDC issuer URL |
| `GITHUB_OIDC_AUDIENCE` | No | `deployment-queue-api` | Expected audience in OIDC token |
| `ALLOWED_ORGANISATIONS` | No | - | Comma-separated list of allowed orgs (empty = all allowed) |

*Either `SNOWFLAKE_PRIVATE_KEY_PATH` or `SNOWFLAKE_PASSWORD` must be provided.

### 3. Place RSA Private Key

For key-pair authentication, place your private key at `secrets/rsa_key.p8`:

```bash
cp /path/to/your/rsa_key.p8 secrets/rsa_key.p8
```

For local development, you can also set `SNOWFLAKE_PRIVATE_KEY_PATH` in your `.env` file to point to the key location.

### 4. Database Setup

Execute the schema in Snowflake before running the API:

```bash
snowsql -f sql/schema.sql
```

Or run the contents of `sql/schema.sql` in your Snowflake worksheet.

### 5. Verify Connection

Test your Snowflake connection:

```bash
python scripts/verify_connection.py
```

## Running the API

### Local Development

```bash
make run
```

Or manually:

```bash
uvicorn src.deployment_queue.main:app --reload
```

The API will be available at `http://localhost:8000`.

### Docker

```bash
docker-compose up --build
```

### API Documentation

Once running, interactive documentation is available at:

- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

## Authentication

The API supports two authentication methods:

| Source | Auth Method | Headers |
|--------|-------------|---------|
| **GitHub Actions** | OIDC JWT | `Authorization: Bearer <jwt>` |
| **CLI** | GitHub PAT | `Authorization: Bearer <pat>` + `X-Organisation: <org>` |

### GitHub Actions (OIDC)

```yaml
jobs:
  deploy:
    runs-on: ubuntu-latest
    permissions:
      id-token: write  # Required for OIDC
    steps:
      - name: Get OIDC Token
        id: token
        run: |
          TOKEN=$(curl -s -H "Authorization: bearer $ACTIONS_ID_TOKEN_REQUEST_TOKEN" \
            "$ACTIONS_ID_TOKEN_REQUEST_URL&audience=deployment-queue-api" | jq -r '.value')
          echo "token=$TOKEN" >> $GITHUB_OUTPUT

      - name: Create Deployment
        run: |
          curl -X POST https://your-api/v1/deployments \
            -H "Authorization: Bearer ${{ steps.token.outputs.token }}" \
            -H "Content-Type: application/json" \
            -d '{"name": "my-service", "version": "1.0.0", ...}'
```

### CLI (PAT)

```bash
curl -X GET "https://api.example.com/v1/deployments" \
  -H "Authorization: Bearer ghp_xxxxxxxxxxxx" \
  -H "X-Organisation: my-org"
```

## API Endpoints

### Health Check

```
GET /health
```

Returns `{"status": "healthy"}` when the API is running. No authentication required.

### List Deployments

```
GET /v1/deployments
```

Query parameters:
- `status` (optional): Filter by status (`scheduled`, `in_progress`, `deployed`, `skipped`, `failed`)
- `name` (optional): Filter by component name
- `environment` (optional): Filter by environment
- `provider` (optional): Filter by provider (`gcp`, `aws`, `azure`)
- `cloud_account_id` (optional): Filter by cloud account
- `region` (optional): Filter by region
- `cell_id` (optional): Filter by cell
- `trigger` (optional): Filter by trigger (`auto`, `manual`, `rollback`)
- `limit` (optional): Maximum results (default: 100, max: 1000)

### Create Deployment

```
POST /v1/deployments
```

Creates a new deployment with status `scheduled`.

### Update Deployment

```
PATCH /v1/deployments/{deployment_id}
```

Updatable fields: `status`, `notes`, `deployment_uri`

**Auto-skip behavior**: When setting status to `deployed`, all older scheduled deployments for the same taxonomy (organisation, name, environment, provider, cloud_account_id, region, cell_id) are automatically marked as `skipped`.

### Rollback Deployment

```
POST /v1/deployments/rollback
```

Required query parameters:
- `name`: Component name
- `environment`: Environment (e.g., `production`, `staging`)
- `provider`: Cloud provider (`gcp`, `aws`, `azure`)
- `cloud_account_id`: Cloud account identifier
- `region`: Cloud region

Optional:
- `cell_id`: Cell identifier (for cell-based deployments)
- `target_version`: Specific version to rollback to. If not provided, rolls back to the previous deployment.

Rollback creates a NEW deployment record with:
- `trigger` set to `rollback`
- `source_deployment_id` referencing the deployment being copied
- `rollback_from_deployment_id` referencing the current deployment being replaced
- Status set to `scheduled`

## Data Models

### Enums

#### Provider
- `gcp` - Google Cloud Platform
- `aws` - Amazon Web Services
- `azure` - Microsoft Azure

#### DeploymentType
- `k8s` - Kubernetes deployment
- `terraform` - Terraform infrastructure
- `data_pipeline` - Data pipeline deployment

#### DeploymentStatus
- `scheduled` - Deployment is queued
- `in_progress` - Deployment is running
- `deployed` - Deployment completed successfully
- `skipped` - Deployment was skipped (superseded or manually skipped)
- `failed` - Deployment failed

#### DeploymentTrigger
- `auto` - Automatic deployment (from CI/CD pipeline)
- `manual` - Manual deployment
- `rollback` - Rollback deployment

### Deployment Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | Auto | UUID generated on creation |
| `created_at` | datetime | Auto | Timestamp of creation |
| `updated_at` | datetime | Auto | Timestamp of last update |
| `organisation` | string | Auto | Organisation from token |
| `name` | string | Yes | Component/service name |
| `version` | string | Yes | Version being deployed |
| `commit_sha` | string | No | Git commit SHA |
| `pipeline_extra_params` | string | No | JSON string of extra pipeline parameters |
| `provider` | Provider | Yes | Cloud provider |
| `cloud_account_id` | string | Yes | Cloud account identifier |
| `region` | string | Yes | Cloud region |
| `environment` | string | Yes | Deployment environment |
| `cell_id` | string | No | Cell identifier |
| `type` | DeploymentType | Yes | Type of deployment |
| `status` | DeploymentStatus | Auto | Current status (defaults to `scheduled`) |
| `auto` | boolean | No | Auto-deployment flag (default: `true`) |
| `trigger` | DeploymentTrigger | Auto | How deployment was triggered |
| `description` | string | No | Deployment description |
| `notes` | string | No | Additional notes |
| `build_uri` | string | No | URI to build artifacts |
| `deployment_uri` | string | No | URI to deployment |
| `resource` | string | No | Cloud resource identifier |
| `source_deployment_id` | string | No | For rollback: deployment being copied |
| `rollback_from_deployment_id` | string | No | For rollback: deployment being replaced |
| `created_by_repo` | string | Auto | Repository from token |
| `created_by_workflow` | string | Auto | Workflow from token |
| `created_by_actor` | string | Auto | Actor from token |

## Examples

All examples require authentication headers as described in the [Authentication](#authentication) section.

### Create a Kubernetes Deployment

```bash
curl -X POST http://localhost:8000/v1/deployments \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "user-service",
    "version": "2.1.0",
    "commit_sha": "abc123def456",
    "provider": "gcp",
    "cloud_account_id": "my-gcp-project",
    "region": "us-central1",
    "environment": "production",
    "type": "k8s",
    "description": "User service v2.1.0 with new auth flow"
  }'
```

### List Scheduled Deployments

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/v1/deployments?status=scheduled"
```

### List Deployments by Taxonomy

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/v1/deployments?\
name=user-service&\
environment=production&\
provider=gcp&\
cloud_account_id=my-gcp-project&\
region=us-central1"
```

### Update Deployment Status to Deployed

When marked as deployed, older scheduled deployments for the same taxonomy are automatically skipped.

```bash
curl -X PATCH http://localhost:8000/v1/deployments/abc-123-def \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"status": "deployed"}'
```

### Mark Deployment as Failed

```bash
curl -X PATCH http://localhost:8000/v1/deployments/abc-123-def \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"status": "failed", "notes": "Database migration failed"}'
```

### Rollback to Previous Version

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/v1/deployments/rollback?\
name=user-service&\
environment=production&\
provider=gcp&\
cloud_account_id=my-gcp-project&\
region=us-central1"
```

### Rollback to Specific Version

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/v1/deployments/rollback?\
name=user-service&\
environment=production&\
provider=gcp&\
cloud_account_id=my-gcp-project&\
region=us-central1&\
target_version=1.9.5"
```
