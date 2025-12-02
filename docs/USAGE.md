# Usage Guide

This document provides detailed usage instructions for the Deployment Queue API.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Running the API](#running-the-api)
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

## API Endpoints

### Health Check

```
GET /health
```

Returns `{"status": "healthy"}` when the API is running.

### Basic CRUD Operations

#### List Deployments

```
GET /v1/deployments
```

Query parameters:
- `status` (optional): Filter by status (`scheduled`, `in_progress`, `deployed`, `skipped`, `failed`)
- `environment` (optional): Filter by environment
- `provider` (optional): Filter by provider (`gcp`, `aws`, `azure`)
- `limit` (optional): Maximum results (default: 100, max: 1000)

#### Create Deployment

```
POST /v1/deployments
```

Creates a new deployment with status `scheduled`.

#### Get Deployment by ID

```
GET /v1/deployments/{deployment_id}
```

#### Update Deployment by ID

```
PATCH /v1/deployments/{deployment_id}
```

Updatable fields: `status`, `notes`, `deployment_uri`

### Taxonomy-Based Operations

Taxonomy identifies a unique deployment target using: `name` + `environment` + `provider` + `cloud_account_id` + `region` + `cell`

#### Get Current Deployment

```
GET /v1/deployments/current
```

Required query parameters:
- `name`: Component name
- `environment`: Environment (e.g., `production`, `staging`)
- `provider`: Cloud provider (`gcp`, `aws`, `azure`)
- `cloud_account_id`: GCP project / AWS account / Azure subscription
- `region`: Cloud region

Optional:
- `cell`: Cell identifier (for cell-based deployments)

#### Update Current Deployment Status

```
PATCH /v1/deployments/current/status
```

Same query parameters as above, plus request body with `status`.

#### Get Deployment History

```
GET /v1/deployments/history
```

Same query parameters as above, plus optional `limit` (default: 50, max: 500).

#### Rollback Deployment

```
POST /v1/deployments/rollback
```

Same query parameters as above. Request body:
- `target_version` (optional): Specific version to rollback to. If not provided, rolls back to the second most recent deployment.

Rollback creates a NEW deployment record with:
- `auto` set to `False`
- A rollback note appended to `notes`
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
- `skipped` - Deployment was skipped
- `failed` - Deployment failed

### Deployment Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | Auto | UUID generated on creation |
| `created_at` | datetime | Auto | Timestamp of creation |
| `updated_at` | datetime | Auto | Timestamp of last update |
| `name` | string | Yes | Component/service name |
| `version` | string | Yes | Version being deployed |
| `commit_sha` | string | No | Git commit SHA |
| `pipeline_extra_params` | string | No | JSON string of extra pipeline parameters |
| `provider` | Provider | Yes | Cloud provider |
| `cloud_account_id` | string | No | Cloud account identifier |
| `region` | string | No | Cloud region |
| `environment` | string | Yes | Deployment environment |
| `cell` | string | No | Cell identifier |
| `type` | DeploymentType | Yes | Type of deployment |
| `status` | DeploymentStatus | Auto | Current status (defaults to `scheduled`) |
| `auto` | boolean | No | Auto-deployment flag (default: `true`) |
| `description` | string | No | Deployment description |
| `notes` | string | No | Additional notes |
| `build_uri` | string | No | URI to build artifacts |
| `deployment_uri` | string | No | URI to deployment |
| `resource` | string | No | Cloud resource identifier |

## Examples

### Create a Kubernetes Deployment

```bash
curl -X POST http://localhost:8000/v1/deployments \
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

### List Failed Deployments

```bash
curl "http://localhost:8000/v1/deployments?status=failed&environment=production"
```

### Get Current Production Deployment

```bash
curl "http://localhost:8000/v1/deployments/current?\
name=user-service&\
environment=production&\
provider=gcp&\
cloud_account_id=my-gcp-project&\
region=us-central1"
```

### Update Deployment Status to Deployed

```bash
curl -X PATCH "http://localhost:8000/v1/deployments/current/status?\
name=user-service&\
environment=production&\
provider=gcp&\
cloud_account_id=my-gcp-project&\
region=us-central1" \
  -H "Content-Type: application/json" \
  -d '{"status": "deployed"}'
```

### Get Deployment History

```bash
curl "http://localhost:8000/v1/deployments/history?\
name=user-service&\
environment=production&\
provider=gcp&\
cloud_account_id=my-gcp-project&\
region=us-central1&\
limit=10"
```

### Rollback to Previous Version

```bash
curl -X POST "http://localhost:8000/v1/deployments/rollback?\
name=user-service&\
environment=production&\
provider=gcp&\
cloud_account_id=my-gcp-project&\
region=us-central1" \
  -H "Content-Type: application/json" \
  -d '{}'
```

### Rollback to Specific Version

```bash
curl -X POST "http://localhost:8000/v1/deployments/rollback?\
name=user-service&\
environment=production&\
provider=gcp&\
cloud_account_id=my-gcp-project&\
region=us-central1" \
  -H "Content-Type: application/json" \
  -d '{"target_version": "1.9.5"}'
```

### Update Deployment Notes

```bash
curl -X PATCH http://localhost:8000/v1/deployments/abc-123-def \
  -H "Content-Type: application/json" \
  -d '{
    "notes": "Deployment paused for investigation",
    "status": "skipped"
  }'
```
