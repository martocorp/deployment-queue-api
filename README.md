# Deployment Queue API

A FastAPI-based REST API to manage a deployment queue across multiple cloud providers (GCP, AWS, Azure). The API tracks deployment lifecycle, enables status updates, and supports rollbacks.

## Key Features

- **Dual Authentication**: GitHub OIDC for Actions, GitHub PAT for CLI
- **Multi-Tenant Isolation**: Each GitHub organisation has isolated data
- **Deployment Lineage**: Track rollback chains with source and rollback references
- **Auto-Skip**: When a deployment is marked as deployed, older scheduled deployments are automatically skipped

## Documentation

- [Usage Guide](docs/USAGE.md) - Detailed API reference and examples
- [Code Style Guide](docs/CODESTYLE.md) - Coding standards and conventions

## Quick Start

### Prerequisites

- Python 3.13+
- Snowflake account with key-pair authentication
- Docker (optional)

### Installation

```bash
make init
cp .env.example .env
# Edit .env with your Snowflake credentials
make run
```

The API runs on two ports:
- **API server**: `http://localhost:8000` - Main API endpoints
- **Management server**: `http://localhost:9090` - Health, readiness, and metrics

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/v1/deployments` | List deployments with filters |
| `POST` | `/v1/deployments` | Create a new deployment |
| `PATCH` | `/v1/deployments/{id}` | Update deployment status |
| `POST` | `/v1/deployments/rollback` | Create rollback deployment |

## Management Endpoints (Port 9090)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check (liveness probe) |
| `GET` | `/ready` | Readiness check |
| `GET` | `/metrics` | Prometheus metrics |

## Authentication

The API supports two authentication methods for different use cases:

| Use Case | Auth Method | Headers |
|----------|-------------|---------|
| **GitHub Actions** | OIDC JWT | `Authorization: Bearer <jwt>` |
| **CLI / Terminal** | GitHub PAT | `Authorization: Bearer <pat>` + `X-Organisation: <org>` |

### Multi-Tenancy

- **Organisation Isolation**: Each GitHub organisation has completely isolated data
- **Automatic Filtering**: All queries are scoped to the authenticated organisation
- **OIDC**: Organisation extracted from the JWT's `repository_owner` claim
- **PAT**: Organisation specified via `X-Organisation` header, verified via GitHub API membership

### GitHub Actions (OIDC)

For automated deployments from GitHub Actions workflows:

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
              "version": "1.0.0",
              "provider": "gcp",
              "cloud_account_id": "my-project",
              "region": "us-central1",
              "environment": "production",
              "type": "k8s"
            }'
```

### CLI / Terminal (PAT)

For manual operations using `deployment-queue-cli` or direct API calls:

```bash
# Set your GitHub PAT and organisation
export GITHUB_TOKEN="ghp_xxxxxxxxxxxxxxxxxxxx"
export ORG="my-organisation"

# List scheduled deployments
curl -X GET "https://api.example.com/v1/deployments?status=scheduled" \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "X-Organisation: $ORG"

# Create a deployment
curl -X POST "https://api.example.com/v1/deployments" \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "X-Organisation: $ORG" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my-service",
    "version": "1.0.0",
    "provider": "gcp",
    "cloud_account_id": "my-project",
    "region": "us-central1",
    "environment": "production",
    "type": "k8s"
  }'

# Update deployment status to deployed
# Note: This automatically skips older scheduled deployments for the same taxonomy
curl -X PATCH "https://api.example.com/v1/deployments/{deployment_id}" \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "X-Organisation: $ORG" \
  -H "Content-Type: application/json" \
  -d '{"status": "deployed"}'

# Rollback to previous version
curl -X POST "https://api.example.com/v1/deployments/rollback?\
name=my-service&\
environment=production&\
provider=gcp&\
cloud_account_id=my-project&\
region=us-central1" \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "X-Organisation: $ORG"
```

## Taxonomy & Auto-Skip

Deployments are uniquely identified by a **taxonomy**:
`organisation` + `name` + `environment` + `provider` + `cloud_account_id` + `region` + `cell`

When a deployment is marked as `deployed`, all older scheduled deployments for the same taxonomy are automatically marked as `skipped`. This ensures the deployment queue stays clean and only relevant deployments remain scheduled.

## Development

| Command | Description |
|---------|-------------|
| `make init` | Set up virtual environment and install dependencies |
| `make run` | Start development server |
| `make test` | Run tests with coverage |
| `make build` | Full build: lint, test, security scan, package |

## Project Structure

```
deployment-queue-api/
├── src/deployment_queue/
│   ├── main.py           # FastAPI app and endpoints
│   ├── management.py     # Management server (health, metrics)
│   ├── metrics.py        # Prometheus metrics definitions
│   ├── server.py         # Dual-server runner
│   ├── auth.py           # GitHub OIDC and PAT authentication
│   ├── models.py         # Pydantic models and enums
│   ├── database.py       # Snowflake connection handling
│   └── config.py         # Settings via pydantic-settings
├── tests/                # Test suite
├── docs/                 # Documentation
└── sql/                  # Database schema
```
