# Usage Guide

This document provides detailed usage instructions for the Deployment Queue API.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Running the API](#running-the-api)
- [Authentication](#authentication)
- [Multi-Tenancy](#multi-tenancy)
- [API Endpoints](#api-endpoints)
- [Data Models](#data-models)
- [Examples](#examples)

## Prerequisites

- Python 3.13 or higher
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

### 4. Database Setup

Execute the schema in Snowflake before running the API:

```bash
snowsql -f sql/schema.sql
```

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

This starts both servers:
- **API server**: `http://localhost:8000` - Main API endpoints
- **Management server**: `http://localhost:9090` - Health, readiness, and Prometheus metrics

For development with auto-reload (API only):

```bash
make run-dev
```

### Docker

```bash
docker-compose up --build
```

### API Documentation

Once running, interactive documentation is available at:

- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

### Management Endpoints

The management server runs on port 9090 and exposes:

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Health check (liveness probe) |
| `GET /ready` | Readiness check |
| `GET /metrics` | Prometheus metrics in text format |

Example:
```bash
curl http://localhost:9090/health
# {"status": "healthy"}

curl http://localhost:9090/metrics
# HELP deployment_queue_info Deployment Queue API information
# TYPE deployment_queue_info gauge
# ...
```

## Authentication

The API supports two authentication methods for different use cases:

| Use Case | Auth Method | Headers | Organisation Source |
|----------|-------------|---------|---------------------|
| **GitHub Actions** | OIDC JWT | `Authorization: Bearer <jwt>` | Extracted from JWT `repository_owner` claim |
| **CLI / Terminal** | GitHub PAT | `Authorization: Bearer <pat>` + `X-Organisation: <org>` | `X-Organisation` header (verified via GitHub API) |

### GitHub Actions (OIDC)

For automated deployments from CI/CD pipelines. The organisation is automatically extracted from the JWT token.

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
          curl -X POST https://api.example.com/v1/deployments \
            -H "Authorization: Bearer ${{ steps.token.outputs.token }}" \
            -H "Content-Type: application/json" \
            -d '{
              "name": "my-service",
              "version": "${{ github.sha }}",
              "provider": "gcp",
              "cloud_account_id": "my-project",
              "region": "us-central1",
              "environment": "production",
              "type": "k8s"
            }'
```

### CLI / Terminal (PAT)

For manual operations using `deployment-queue-cli` or direct API calls. Requires a GitHub Personal Access Token and explicit organisation header.

**Requirements:**
- GitHub PAT with `read:org` scope (to verify organisation membership)
- User must be a member of the specified organisation

```bash
# Set environment variables
export GITHUB_TOKEN="ghp_xxxxxxxxxxxxxxxxxxxx"
export ORG="my-organisation"
export API_URL="https://api.example.com"

# Example API call
curl -X GET "$API_URL/v1/deployments" \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "X-Organisation: $ORG"
```

## Multi-Tenancy

The API enforces strict multi-tenant isolation based on GitHub organisations:

- **Data Isolation**: Each organisation's deployments are completely isolated
- **Automatic Filtering**: All database queries include organisation filter
- **No Cross-Org Access**: Users can only access deployments for organisations they belong to

### Taxonomy

Deployments are uniquely identified by a **taxonomy** - a combination of:

| Field | Description |
|-------|-------------|
| `organisation` | GitHub organisation (from authentication) |
| `name` | Component/service name |
| `provider` | Cloud provider (gcp, aws, azure) |
| `cloud_account_id` | Cloud account identifier |
| `region` | Cloud region |
| `cell` | Optional cell identifier |

### Auto-Skip Behavior

When a deployment is marked as `deployed`, all older scheduled deployments for the **same taxonomy** are automatically marked as `skipped`. This ensures:

- The deployment queue stays clean
- Only relevant deployments remain scheduled
- Superseded versions are properly tracked

## API Endpoints

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
- `cell` (optional): Filter by cell
- `trigger` (optional): Filter by trigger (`auto`, `manual`, `rollback`)
- `limit` (optional): Maximum results (default: 100, max: 1000)

**Note**: Results are always filtered by the authenticated organisation.

### Create Deployment

```
POST /v1/deployments
```

Creates a new deployment with status `scheduled`. The `organisation` is set from the authentication token.

### Update Deployment

```
PATCH /v1/deployments/{deployment_id}
```

Updatable fields: `status`, `notes`, `deployment_uri`

**Auto-skip behavior**: When setting status to `deployed`, all older scheduled deployments for the same taxonomy are automatically marked as `skipped`.

### Rollback Deployment

```
POST /v1/deployments/rollback
```

Required query parameters:
- `name`: Component name
- `provider`: Cloud provider (`gcp`, `aws`, `azure`)
- `cloud_account_id`: Cloud account identifier
- `region`: Cloud region

Optional:
- `cell`: Cell identifier
- `target_version`: Specific version to rollback to (defaults to previous deployment)

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
- `manual` - Manual deployment (auto=false)
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
| `cell` | string | No | Cell identifier |
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

### GitHub Actions Examples

These examples are for use in GitHub Actions workflows with OIDC authentication.

#### Create Deployment in GitHub Actions

```yaml
- name: Create Deployment
  run: |
    curl -X POST $API_URL/v1/deployments \
      -H "Authorization: Bearer ${{ steps.token.outputs.token }}" \
      -H "Content-Type: application/json" \
      -d '{
        "name": "user-service",
        "version": "${{ github.sha }}",
        "commit_sha": "${{ github.sha }}",
        "provider": "gcp",
        "cloud_account_id": "my-gcp-project",
        "region": "us-central1",
        "environment": "production",
        "type": "k8s",
        "build_uri": "${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}"
      }'
```

#### Update Status After Deployment

```yaml
- name: Mark Deployment as Deployed
  run: |
    curl -X PATCH $API_URL/v1/deployments/$DEPLOYMENT_ID \
      -H "Authorization: Bearer ${{ steps.token.outputs.token }}" \
      -H "Content-Type: application/json" \
      -d '{"status": "deployed"}'
```

### CLI Examples

These examples are for use in a terminal with GitHub PAT authentication.

#### Setup

```bash
# Set environment variables for CLI usage
export GITHUB_TOKEN="ghp_xxxxxxxxxxxxxxxxxxxx"
export ORG="my-organisation"
export API_URL="https://api.example.com"
```

#### List Scheduled Deployments

```bash
curl -X GET "$API_URL/v1/deployments?status=scheduled" \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "X-Organisation: $ORG"
```

#### List Deployments by Taxonomy

```bash
curl -X GET "$API_URL/v1/deployments?\
name=user-service&\
environment=production&\
provider=gcp&\
cloud_account_id=my-gcp-project&\
region=us-central1" \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "X-Organisation: $ORG"
```

#### Create a Deployment

```bash
curl -X POST "$API_URL/v1/deployments" \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "X-Organisation: $ORG" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "user-service",
    "version": "2.1.0",
    "provider": "gcp",
    "cloud_account_id": "my-gcp-project",
    "region": "us-central1",
    "environment": "production",
    "type": "k8s",
    "auto": false,
    "description": "Manual deployment for hotfix"
  }'
```

#### Update Deployment Status to Deployed

When marked as deployed, older scheduled deployments for the same taxonomy are automatically skipped.

```bash
curl -X PATCH "$API_URL/v1/deployments/abc-123-def" \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "X-Organisation: $ORG" \
  -H "Content-Type: application/json" \
  -d '{"status": "deployed"}'
```

#### Mark Deployment as Failed

```bash
curl -X PATCH "$API_URL/v1/deployments/abc-123-def" \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "X-Organisation: $ORG" \
  -H "Content-Type: application/json" \
  -d '{"status": "failed", "notes": "Database migration failed"}'
```

#### Rollback to Previous Version

```bash
curl -X POST "$API_URL/v1/deployments/rollback?\
name=user-service&\
provider=gcp&\
cloud_account_id=my-gcp-project&\
region=us-central1" \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "X-Organisation: $ORG"
```

#### Rollback to Specific Version

```bash
curl -X POST "$API_URL/v1/deployments/rollback?\
name=user-service&\
provider=gcp&\
cloud_account_id=my-gcp-project&\
region=us-central1&\
target_version=1.9.5" \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "X-Organisation: $ORG"
```
