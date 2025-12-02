# Deployment Queue API

A FastAPI-based REST API to manage a deployment queue across multiple cloud providers (GCP, AWS, Azure). The API tracks deployment lifecycle, enables status updates via cloud taxonomy, and supports rollbacks.

## Documentation

- [Usage Guide](docs/USAGE.md) - Detailed usage instructions, API reference, and examples
- [Code Style Guide](docs/CODESTYLE.md) - Coding standards and conventions

## Prerequisites

- Python 3.11+
- Snowflake account with key-pair authentication configured
- Docker (optional)

## Local Setup

### 1. Install Dependencies

```bash
make init
```

Or manually:

```bash
python -m venv .venv
source .venv/bin/activate
pip install uv
uv pip install -e ".[dev]"
```

### 2. Configure Environment

Copy the example environment file:

```bash
cp .env.example .env
```

Edit `.env` with your Snowflake connection details:

```bash
SNOWFLAKE_ACCOUNT=xy12345.eu-west-1
SNOWFLAKE_USER=deployment_api_user
SNOWFLAKE_PRIVATE_KEY_PASSPHRASE=your_passphrase_if_key_is_encrypted
SNOWFLAKE_WAREHOUSE=COMPUTE_WH
SNOWFLAKE_DATABASE=DEPLOYMENTS_DB
SNOWFLAKE_SCHEMA=PUBLIC
```

### 3. Place RSA Private Key

Place your Snowflake RSA private key at `secrets/rsa_key.p8`:

```bash
cp /path/to/your/rsa_key.p8 secrets/rsa_key.p8
```

For local development, you can also set `SNOWFLAKE_PRIVATE_KEY_PATH` in your `.env` file.

### 4. Initialize Database

Run the schema SQL in Snowflake:

```bash
snowsql -f sql/schema.sql
```

Or execute the contents of `sql/schema.sql` in your Snowflake worksheet.

### 5. Verify Connection

```bash
python scripts/verify_connection.py
```

### 6. Run the API

```bash
make run
```

Or manually:

```bash
uvicorn src.deployment_queue.main:app --reload
```

The API will be available at `http://localhost:8000`.

## Docker Setup

### 1. Configure Environment

Create `.env` file with your Snowflake credentials (see Local Setup step 2).

### 2. Place RSA Private Key

```bash
cp /path/to/your/rsa_key.p8 secrets/rsa_key.p8
```

### 3. Run with Docker Compose

```bash
docker-compose up --build
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/v1/deployments` | List deployments with optional filters |
| `POST` | `/v1/deployments` | Create a new deployment |
| `GET` | `/v1/deployments/{id}` | Get deployment by ID |
| `PATCH` | `/v1/deployments/{id}` | Update deployment by ID |
| `GET` | `/v1/deployments/current` | Get current deployment by taxonomy |
| `PATCH` | `/v1/deployments/current/status` | Update status by taxonomy |
| `GET` | `/v1/deployments/history` | Get deployment history by taxonomy |
| `POST` | `/v1/deployments/rollback` | Create rollback deployment |
| `GET` | `/health` | Health check |

## API Documentation

Once running, interactive documentation is available at:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## Example Usage

### Create a Deployment

```bash
curl -X POST http://localhost:8000/v1/deployments \
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

### Get Current Deployment by Taxonomy

```bash
curl "http://localhost:8000/v1/deployments/current?\
name=my-service&\
environment=production&\
provider=gcp&\
cloud_account_id=my-project&\
region=us-central1"
```

### Update Deployment Status

```bash
curl -X PATCH "http://localhost:8000/v1/deployments/current/status?\
name=my-service&\
environment=production&\
provider=gcp&\
cloud_account_id=my-project&\
region=us-central1" \
  -H "Content-Type: application/json" \
  -d '{"status": "deployed"}'
```

### Rollback to Previous Version

```bash
curl -X POST "http://localhost:8000/v1/deployments/rollback?\
name=my-service&\
environment=production&\
provider=gcp&\
cloud_account_id=my-project&\
region=us-central1" \
  -H "Content-Type: application/json" \
  -d '{}'
```

## Development

### Available Make Commands

| Command | Description |
|---------|-------------|
| `make init` | Set up virtual environment and install dependencies |
| `make run` | Start development server |
| `make test` | Run tests with coverage |
| `make lint` | Run linter and type checker |
| `make format` | Auto-format code |
| `make security` | Run security scan |
| `make build` | Build package (runs lint, test, security) |
| `make clean` | Remove build artifacts and caches |
| `make docker-build` | Build Docker image |
| `make docker-run` | Run with Docker Compose |

### Running Tests

```bash
make test
```

## Project Structure

```
deployment-queue-api/
├── src/deployment_queue/
│   ├── __init__.py
│   ├── main.py           # FastAPI app and endpoints
│   ├── models.py         # Pydantic models and enums
│   ├── database.py       # Snowflake connection handling
│   └── config.py         # Settings via pydantic-settings
├── tests/                # Test suite
├── scripts/
│   └── verify_connection.py  # Test Snowflake connection
├── sql/                  # Database schema
├── secrets/              # Git-ignored, for local dev keys
├── docs/                 # Documentation
├── Makefile              # Development commands
├── Dockerfile
├── docker-compose.yml
└── pyproject.toml
```
