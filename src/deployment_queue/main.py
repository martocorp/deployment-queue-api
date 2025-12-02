"""FastAPI application and endpoints for the Deployment Queue API."""

from datetime import UTC, datetime
from typing import Any, Optional
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Query, status
from snowflake.connector import DictCursor

from deployment_queue.auth import TokenPayload, verify_token
from deployment_queue.database import get_cursor
from deployment_queue.models import (
    Deployment,
    DeploymentCreate,
    DeploymentStatus,
    DeploymentTrigger,
    DeploymentUpdate,
    Provider,
    row_to_deployment,
)

app = FastAPI(
    title="Deployment Queue API",
    description="Multi-tenant deployment queue with GitHub OIDC and PAT authentication",
    version="1.0.0",
)


def build_taxonomy_query(
    base_query: str,
    params: dict[str, Any],
    name: str,
    environment: str,
    provider: Provider,
    cloud_account_id: str,
    region: str,
    cell_id: Optional[str],
    organisation: str,
) -> tuple[str, dict[str, Any]]:
    """
    Build query with taxonomy filters.

    SECURITY: Organisation comes from token, never from user input.
    """
    query = base_query + """
        WHERE organisation = %(organisation)s
          AND name = %(name)s
          AND environment = %(environment)s
          AND provider = %(provider)s
          AND cloud_account_id = %(cloud_account_id)s
          AND region = %(region)s
    """  # nosec B608 - query built with hardcoded strings and parameterized values
    params.update({
        "organisation": organisation,
        "name": name,
        "environment": environment,
        "provider": provider.value,
        "cloud_account_id": cloud_account_id,
        "region": region,
    })

    if cell_id:
        query += " AND cell_id = %(cell_id)s"
        params["cell_id"] = cell_id
    else:
        query += " AND cell_id IS NULL"

    return query, params


# -----------------------------------------------------------------------------
# Health check (no auth required)
# -----------------------------------------------------------------------------


@app.get("/health")
def health_check() -> dict[str, str]:
    """Health check endpoint - no authentication required."""
    return {"status": "healthy"}


# -----------------------------------------------------------------------------
# Basic CRUD - all scoped to token.organisation
# -----------------------------------------------------------------------------


@app.get("/v1/deployments", response_model=list[Deployment])
async def list_deployments(
    deployment_status: Optional[DeploymentStatus] = Query(default=None, alias="status"),
    environment: Optional[str] = None,
    provider: Optional[Provider] = None,
    trigger: Optional[DeploymentTrigger] = None,
    limit: int = Query(default=100, le=1000),
    cursor: DictCursor = Depends(get_cursor),
    token: TokenPayload = Depends(verify_token),
) -> list[Deployment]:
    """List deployments for the authenticated organisation."""
    query = "SELECT * FROM deployments WHERE organisation = %(organisation)s"
    params: dict[str, Any] = {"organisation": token.organisation, "limit": limit}

    if deployment_status:
        query += " AND status = %(status)s"
        params["status"] = deployment_status.value
    if environment:
        query += " AND environment = %(environment)s"
        params["environment"] = environment
    if provider:
        query += " AND provider = %(provider)s"
        params["provider"] = provider.value
    if trigger:
        query += " AND trigger = %(trigger)s"
        params["trigger"] = trigger.value

    query += " ORDER BY created_at DESC LIMIT %(limit)s"

    cursor.execute(query, params)
    return [row_to_deployment(row) for row in cursor.fetchall()]


@app.post("/v1/deployments", response_model=Deployment, status_code=status.HTTP_201_CREATED)
async def create_deployment(
    deployment: DeploymentCreate,
    cursor: DictCursor = Depends(get_cursor),
    token: TokenPayload = Depends(verify_token),
) -> Deployment:
    """
    Create a new deployment for the authenticated organisation.

    - Organisation is set from the GitHub token (not user input)
    - Trigger is set based on the 'auto' field
    - Audit fields are populated from the token
    """
    deployment_id = str(uuid4())
    now = datetime.now(UTC)

    # Determine trigger based on auto flag
    trigger = DeploymentTrigger.auto if deployment.auto else DeploymentTrigger.manual

    cursor.execute(
        """
        INSERT INTO deployments (
            id, created_at, updated_at, organisation,
            name, version, commit_sha, pipeline_extra_params,
            provider, cloud_account_id, region, environment, cell_id,
            type, status, auto, description, notes,
            trigger, source_deployment_id, rollback_from_deployment_id,
            build_uri, deployment_uri, resource,
            created_by_repo, created_by_workflow, created_by_actor
        ) VALUES (
            %(id)s, %(created_at)s, %(updated_at)s, %(organisation)s,
            %(name)s, %(version)s, %(commit_sha)s, %(pipeline_extra_params)s,
            %(provider)s, %(cloud_account_id)s, %(region)s, %(environment)s, %(cell_id)s,
            %(type)s, %(status)s, %(auto)s, %(description)s, %(notes)s,
            %(trigger)s, NULL, NULL,
            %(build_uri)s, %(deployment_uri)s, %(resource)s,
            %(created_by_repo)s, %(created_by_workflow)s, %(created_by_actor)s
        )
        """,
        {
            "id": deployment_id,
            "created_at": now,
            "updated_at": now,
            "organisation": token.organisation,
            "name": deployment.name,
            "version": deployment.version,
            "commit_sha": deployment.commit_sha,
            "pipeline_extra_params": deployment.pipeline_extra_params,
            "provider": deployment.provider.value,
            "cloud_account_id": deployment.cloud_account_id,
            "region": deployment.region,
            "environment": deployment.environment,
            "cell_id": deployment.cell_id,
            "type": deployment.type.value,
            "status": DeploymentStatus.scheduled.value,
            "auto": deployment.auto,
            "description": deployment.description,
            "notes": deployment.notes,
            "trigger": trigger.value,
            "build_uri": deployment.build_uri,
            "deployment_uri": deployment.deployment_uri,
            "resource": deployment.resource,
            "created_by_repo": token.repository,
            "created_by_workflow": token.workflow,
            "created_by_actor": token.actor,
        },
    )

    cursor.execute("SELECT * FROM deployments WHERE id = %(id)s", {"id": deployment_id})
    return row_to_deployment(cursor.fetchone())  # type: ignore[arg-type]


@app.get("/v1/deployments/current", response_model=Optional[Deployment])
async def get_current_deployment(
    name: str = Query(...),
    environment: str = Query(...),
    provider: Provider = Query(...),
    cloud_account_id: str = Query(...),
    region: str = Query(...),
    cell_id: Optional[str] = Query(default=None),
    cursor: DictCursor = Depends(get_cursor),
    token: TokenPayload = Depends(verify_token),
) -> Optional[Deployment]:
    """Get the current (most recent) deployment for a component by taxonomy."""
    query, params = build_taxonomy_query(
        "SELECT * FROM deployments",
        {},
        name, environment, provider, cloud_account_id, region, cell_id,
        token.organisation,
    )
    query += " ORDER BY created_at DESC LIMIT 1"

    cursor.execute(query, params)
    row = cursor.fetchone()
    return row_to_deployment(row) if row else None


@app.patch("/v1/deployments/current/status", response_model=Deployment)
async def update_deployment_status_by_taxonomy(
    name: str = Query(...),
    environment: str = Query(...),
    provider: Provider = Query(...),
    cloud_account_id: str = Query(...),
    region: str = Query(...),
    new_status: DeploymentStatus = Query(...),
    cell_id: Optional[str] = Query(default=None),
    notes: Optional[str] = Query(default=None),
    deployment_uri: Optional[str] = Query(default=None),
    cursor: DictCursor = Depends(get_cursor),
    token: TokenPayload = Depends(verify_token),
) -> Deployment:
    """Update the status of the current deployment by taxonomy."""
    query, params = build_taxonomy_query(
        "SELECT id FROM deployments",
        {},
        name, environment, provider, cloud_account_id, region, cell_id,
        token.organisation,
    )
    query += " ORDER BY created_at DESC LIMIT 1"

    cursor.execute(query, params)
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="No deployment found for this taxonomy")

    deployment_id = row["ID"]
    now = datetime.now(UTC)

    update_fields: dict[str, Any] = {"status": new_status.value, "updated_at": now}
    if notes:
        update_fields["notes"] = notes
    if deployment_uri:
        update_fields["deployment_uri"] = deployment_uri

    set_clause = ", ".join(f"{k} = %({k})s" for k in update_fields.keys())
    update_fields["id"] = deployment_id

    cursor.execute(
        f"UPDATE deployments SET {set_clause} WHERE id = %(id)s",  # nosec B608
        update_fields
    )

    cursor.execute("SELECT * FROM deployments WHERE id = %(id)s", {"id": deployment_id})
    return row_to_deployment(cursor.fetchone())  # type: ignore[arg-type]


@app.get("/v1/deployments/history", response_model=list[Deployment])
async def get_deployment_history(
    name: str = Query(...),
    environment: str = Query(...),
    provider: Provider = Query(...),
    cloud_account_id: str = Query(...),
    region: str = Query(...),
    cell_id: Optional[str] = Query(default=None),
    limit: int = Query(default=10, le=500),
    cursor: DictCursor = Depends(get_cursor),
    token: TokenPayload = Depends(verify_token),
) -> list[Deployment]:
    """
    Get deployment history for a component by taxonomy.

    Returns deployments in reverse chronological order with full lineage info.
    Use trigger, source_deployment_id, and rollback_from_deployment_id to
    trace the deployment chain.
    """
    query, params = build_taxonomy_query(
        "SELECT * FROM deployments",
        {"limit": limit},
        name, environment, provider, cloud_account_id, region, cell_id,
        token.organisation,
    )
    query += " ORDER BY created_at DESC LIMIT %(limit)s"

    cursor.execute(query, params)
    return [row_to_deployment(row) for row in cursor.fetchall()]


@app.post(
    "/v1/deployments/rollback", response_model=Deployment, status_code=status.HTTP_201_CREATED
)
async def rollback_deployment(
    name: str = Query(...),
    environment: str = Query(...),
    provider: Provider = Query(...),
    cloud_account_id: str = Query(...),
    region: str = Query(...),
    cell_id: Optional[str] = Query(default=None),
    target_version: Optional[str] = Query(default=None),
    cursor: DictCursor = Depends(get_cursor),
    token: TokenPayload = Depends(verify_token),
) -> Deployment:
    """
    Create a rollback deployment for a component.

    Lineage tracking:
    - trigger: Set to 'rollback'
    - source_deployment_id: The deployment we're copying configuration from
    - rollback_from_deployment_id: The current deployment we're replacing

    If target_version is provided, rolls back to that specific version.
    Otherwise, rolls back to the previous deployment.
    """
    # Find current deployment (the one we're rolling back FROM)
    query, params = build_taxonomy_query(
        "SELECT * FROM deployments",
        {},
        name, environment, provider, cloud_account_id, region, cell_id,
        token.organisation,
    )
    query += " ORDER BY created_at DESC LIMIT 1"

    cursor.execute(query, params)
    current_deployment = cursor.fetchone()
    rollback_from_id = current_deployment["ID"] if current_deployment else None

    # Find the deployment to rollback TO (source)
    if target_version:
        query, params = build_taxonomy_query(
            "SELECT * FROM deployments",
            {},
            name, environment, provider, cloud_account_id, region, cell_id,
            token.organisation,
        )
        query += " AND version = %(version)s ORDER BY created_at DESC LIMIT 1"
        params["version"] = target_version

        cursor.execute(query, params)
        rows = cursor.fetchall()

        if not rows:
            raise HTTPException(
                status_code=404,
                detail=f"No deployment found with version {target_version}",
            )
        rollback_source = rows[0]
    else:
        # Get second most recent
        query, params = build_taxonomy_query(
            "SELECT * FROM deployments",
            {},
            name, environment, provider, cloud_account_id, region, cell_id,
            token.organisation,
        )
        query += " ORDER BY created_at DESC LIMIT 2"

        cursor.execute(query, params)
        rows = cursor.fetchall()

        if len(rows) < 2:
            raise HTTPException(
                status_code=404,
                detail="No previous deployment to rollback to",
            )
        rollback_source = rows[1]

    # Create new deployment as rollback
    deployment_id = str(uuid4())
    now = datetime.now(UTC)

    cursor.execute(
        """
        INSERT INTO deployments (
            id, created_at, updated_at, organisation,
            name, version, commit_sha, pipeline_extra_params,
            provider, cloud_account_id, region, environment, cell_id,
            type, status, auto, description, notes,
            trigger, source_deployment_id, rollback_from_deployment_id,
            build_uri, deployment_uri, resource,
            created_by_repo, created_by_workflow, created_by_actor
        ) VALUES (
            %(id)s, %(created_at)s, %(updated_at)s, %(organisation)s,
            %(name)s, %(version)s, %(commit_sha)s, %(pipeline_extra_params)s,
            %(provider)s, %(cloud_account_id)s, %(region)s, %(environment)s, %(cell_id)s,
            %(type)s, %(status)s, %(auto)s, %(description)s, %(notes)s,
            %(trigger)s, %(source_deployment_id)s, %(rollback_from_deployment_id)s,
            %(build_uri)s, NULL, %(resource)s,
            %(created_by_repo)s, %(created_by_workflow)s, %(created_by_actor)s
        )
        """,
        {
            "id": deployment_id,
            "created_at": now,
            "updated_at": now,
            "organisation": token.organisation,
            "name": rollback_source["NAME"],
            "version": rollback_source["VERSION"],
            "commit_sha": rollback_source.get("COMMIT_SHA"),
            "pipeline_extra_params": rollback_source.get("PIPELINE_EXTRA_PARAMS"),
            "provider": rollback_source["PROVIDER"],
            "cloud_account_id": rollback_source.get("CLOUD_ACCOUNT_ID"),
            "region": rollback_source.get("REGION"),
            "environment": rollback_source["ENVIRONMENT"],
            "cell_id": rollback_source.get("CELL_ID"),
            "type": rollback_source["TYPE"],
            "status": DeploymentStatus.scheduled.value,
            "auto": False,
            "description": rollback_source.get("DESCRIPTION"),
            "notes": (
                f"Rollback from {rollback_from_id} to version "
                f"{rollback_source['VERSION']} (source: {rollback_source['ID']})"
            ),
            "trigger": DeploymentTrigger.rollback.value,
            "source_deployment_id": rollback_source["ID"],
            "rollback_from_deployment_id": rollback_from_id,
            "build_uri": rollback_source.get("BUILD_URI"),
            "resource": rollback_source.get("RESOURCE"),
            "created_by_repo": token.repository,
            "created_by_workflow": token.workflow,
            "created_by_actor": token.actor,
        },
    )

    cursor.execute("SELECT * FROM deployments WHERE id = %(id)s", {"id": deployment_id})
    return row_to_deployment(cursor.fetchone())  # type: ignore[arg-type]


@app.get("/v1/deployments/{deployment_id}", response_model=Deployment)
async def get_deployment(
    deployment_id: str,
    cursor: DictCursor = Depends(get_cursor),
    token: TokenPayload = Depends(verify_token),
) -> Deployment:
    """Get a deployment by ID (must belong to authenticated organisation)."""
    cursor.execute(
        "SELECT * FROM deployments WHERE id = %(id)s AND organisation = %(organisation)s",
        {"id": deployment_id, "organisation": token.organisation},
    )
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Deployment not found")
    return row_to_deployment(row)


@app.patch("/v1/deployments/{deployment_id}", response_model=Deployment)
async def update_deployment(
    deployment_id: str,
    update: DeploymentUpdate,
    cursor: DictCursor = Depends(get_cursor),
    token: TokenPayload = Depends(verify_token),
) -> Deployment:
    """Update a deployment by ID (must belong to authenticated organisation)."""
    cursor.execute(
        "SELECT id FROM deployments WHERE id = %(id)s AND organisation = %(organisation)s",
        {"id": deployment_id, "organisation": token.organisation},
    )
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="Deployment not found")

    update_data = update.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    # Convert status enum to value if present
    if "status" in update_data and update_data["status"]:
        update_data["status"] = update_data["status"].value

    update_data["updated_at"] = datetime.now(UTC)
    set_clause = ", ".join(f"{k} = %({k})s" for k in update_data.keys())
    update_data["id"] = deployment_id

    cursor.execute(
        f"UPDATE deployments SET {set_clause} WHERE id = %(id)s",  # nosec B608
        update_data
    )

    cursor.execute("SELECT * FROM deployments WHERE id = %(id)s", {"id": deployment_id})
    return row_to_deployment(cursor.fetchone())  # type: ignore[arg-type]
