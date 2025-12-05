"""FastAPI application and endpoints for the Deployment Queue API."""

import time
from datetime import UTC, datetime
from typing import Any, Optional
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.responses import Response
from snowflake.connector import DictCursor

from deployment_queue.auth import TokenPayload, verify_token
from deployment_queue.database import get_cursor
from deployment_queue.metrics import (
    deployments_created_total,
    deployments_skipped_total,
    deployments_updated_total,
    http_request_duration_seconds,
    http_requests_total,
    rollbacks_total,
)
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


# -----------------------------------------------------------------------------
# Metrics Middleware
# -----------------------------------------------------------------------------


@app.middleware("http")
async def metrics_middleware(request: Request, call_next: Any) -> Response:
    """Record HTTP request metrics."""
    start_time = time.perf_counter()

    response = await call_next(request)

    duration = time.perf_counter() - start_time
    endpoint = request.url.path
    method = request.method

    http_requests_total.labels(
        method=method,
        endpoint=endpoint,
        status_code=response.status_code,
    ).inc()

    http_request_duration_seconds.labels(
        method=method,
        endpoint=endpoint,
    ).observe(duration)

    return response


# -----------------------------------------------------------------------------
# Deployments API
# -----------------------------------------------------------------------------


@app.get("/v1/deployments", response_model=list[Deployment])
async def list_deployments(
    deployment_status: Optional[DeploymentStatus] = Query(default=None, alias="status"),
    name: Optional[str] = None,
    provider: Optional[Provider] = None,
    cloud_account_id: Optional[str] = None,
    region: Optional[str] = None,
    cell: Optional[str] = None,
    trigger: Optional[DeploymentTrigger] = None,
    limit: int = Query(default=100, le=1000),
    cursor: DictCursor = Depends(get_cursor),
    token: TokenPayload = Depends(verify_token),
) -> list[Deployment]:
    """
    List deployments for the authenticated organisation.

    Filter by status=scheduled to get the deployment queue.
    """
    query = "SELECT * FROM deployments WHERE organisation = %(organisation)s"
    params: dict[str, Any] = {"organisation": token.organisation, "limit": limit}

    if deployment_status:
        query += " AND status = %(status)s"
        params["status"] = deployment_status.value
    if name:
        query += " AND name = %(name)s"
        params["name"] = name
    if provider:
        query += " AND provider = %(provider)s"
        params["provider"] = provider.value
    if cloud_account_id:
        query += " AND cloud_account_id = %(cloud_account_id)s"
        params["cloud_account_id"] = cloud_account_id
    if region:
        query += " AND region = %(region)s"
        params["region"] = region
    if cell:
        query += " AND cell = %(cell)s"
        params["cell"] = cell
    if trigger:
        query += ' AND "trigger" = %(trigger)s'
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
            provider, cloud_account_id, region, cell,
            type, status, auto, description, notes,
            "trigger", source_deployment_id, rollback_from_deployment_id,
            build_uri, deployment_uri, resource,
            created_by_repo, created_by_workflow, created_by_actor
        ) VALUES (
            %(id)s, %(created_at)s, %(updated_at)s, %(organisation)s,
            %(name)s, %(version)s, %(commit_sha)s, %(pipeline_extra_params)s,
            %(provider)s, %(cloud_account_id)s, %(region)s, %(cell)s,
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
            "cell": deployment.cell,
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

    # Record metric
    deployments_created_total.labels(
        organisation=token.organisation,
        provider=deployment.provider.value,
        trigger=trigger.value,
    ).inc()

    cursor.execute("SELECT * FROM deployments WHERE id = %(id)s", {"id": deployment_id})
    return row_to_deployment(cursor.fetchone())  # type: ignore[arg-type]


@app.patch("/v1/deployments/{deployment_id}", response_model=Deployment)
async def update_deployment(
    deployment_id: str,
    update: DeploymentUpdate,
    cursor: DictCursor = Depends(get_cursor),
    token: TokenPayload = Depends(verify_token),
) -> Deployment:
    """
    Update a deployment by ID (must belong to authenticated organisation).

    When setting status to 'deployed', all older scheduled deployments for the
    same taxonomy (name, provider, cloud_account_id, region, cell)
    will be automatically marked as 'skipped'.
    """
    # Fetch the deployment to update
    cursor.execute(
        "SELECT * FROM deployments WHERE id = %(id)s AND organisation = %(organisation)s",
        {"id": deployment_id, "organisation": token.organisation},
    )
    deployment_row = cursor.fetchone()
    if not deployment_row:
        raise HTTPException(status_code=404, detail="Deployment not found")

    update_data = update.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    now = datetime.now(UTC)

    # Convert status enum to value if present
    new_status = None
    if "status" in update_data and update_data["status"]:
        new_status = update_data["status"]
        update_data["status"] = new_status.value

    update_data["updated_at"] = now
    set_clause = ", ".join(f"{k} = %({k})s" for k in update_data.keys())
    update_data["id"] = deployment_id

    cursor.execute(
        f"UPDATE deployments SET {set_clause} WHERE id = %(id)s",  # nosec B608
        update_data
    )

    # Record metric
    if new_status:
        deployments_updated_total.labels(
            organisation=token.organisation,
            status=new_status.value,
        ).inc()

    # Auto-skip older scheduled deployments when marking as deployed
    if new_status == DeploymentStatus.deployed:
        skipped_count = _skip_scheduled_deployments(cursor, deployment_row, now)
        if skipped_count > 0:
            deployments_skipped_total.labels(
                organisation=token.organisation,
            ).inc(skipped_count)

    cursor.execute("SELECT * FROM deployments WHERE id = %(id)s", {"id": deployment_id})
    return row_to_deployment(cursor.fetchone())  # type: ignore[arg-type]


def _skip_scheduled_deployments(
    cursor: DictCursor,
    deployed_row: dict,
    now: datetime,
) -> int:
    """
    Mark all scheduled deployments for the same taxonomy as skipped.

    When a deployment is marked as 'deployed', all other scheduled deployments
    for the same taxonomy should be skipped (they're now superseded).

    Returns the number of deployments skipped.
    """
    # Build the taxonomy match condition
    # nosec B608 - query built with hardcoded strings and parameterized values
    skip_query = """
        UPDATE deployments
        SET status = 'skipped', updated_at = %(now)s
        WHERE organisation = %(organisation)s
          AND name = %(name)s
          AND provider = %(provider)s
          AND cloud_account_id = %(cloud_account_id)s
          AND region = %(region)s
          AND status = 'scheduled'
          AND id != %(id)s
    """

    params: dict[str, Any] = {
        "now": now,
        "organisation": deployed_row["ORGANISATION"],
        "name": deployed_row["NAME"],
        "provider": deployed_row["PROVIDER"],
        "cloud_account_id": deployed_row["CLOUD_ACCOUNT_ID"],
        "region": deployed_row["REGION"],
        "id": deployed_row["ID"],
    }

    # Handle cell NULL comparison
    cell = deployed_row.get("CELL")
    if cell:
        skip_query += " AND cell = %(cell)s"
        params["cell"] = cell
    else:
        skip_query += " AND cell IS NULL"

    cursor.execute(skip_query, params)
    rowcount = getattr(cursor, "rowcount", None)
    return rowcount if rowcount is not None else 0


@app.post(
    "/v1/deployments/{deployment_id}/rollback",
    response_model=Deployment,
    status_code=status.HTTP_201_CREATED,
)
async def rollback_deployment(
    deployment_id: str,
    cursor: DictCursor = Depends(get_cursor),
    token: TokenPayload = Depends(verify_token),
) -> Deployment:
    """
    Create a rollback deployment from a specific deployment.

    The deployment_id is the deployment to roll back TO (the source).
    A new deployment is created copying the configuration from this deployment.

    Lineage tracking:
    - trigger: Set to 'rollback'
    - source_deployment_id: The deployment we're copying configuration from (deployment_id)
    - rollback_from_deployment_id: The most recent deployment for the same taxonomy
    """
    # Fetch the deployment to rollback TO (source)
    cursor.execute(
        "SELECT * FROM deployments WHERE id = %(id)s AND organisation = %(organisation)s",
        {"id": deployment_id, "organisation": token.organisation},
    )
    rollback_source = cursor.fetchone()

    if not rollback_source:
        raise HTTPException(status_code=404, detail="Deployment not found")

    # Build taxonomy query to find the most recent deployment (rollback FROM)
    # Exclude the source deployment itself
    taxonomy_query = """
        SELECT * FROM deployments
        WHERE organisation = %(organisation)s
          AND name = %(name)s
          AND provider = %(provider)s
          AND cloud_account_id = %(cloud_account_id)s
          AND region = %(region)s
          AND id != %(source_id)s
    """
    taxonomy_params: dict[str, Any] = {
        "organisation": token.organisation,
        "name": rollback_source["NAME"],
        "provider": rollback_source["PROVIDER"],
        "cloud_account_id": rollback_source["CLOUD_ACCOUNT_ID"],
        "region": rollback_source["REGION"],
        "source_id": deployment_id,
    }

    cell = rollback_source.get("CELL")
    if cell:
        taxonomy_query += " AND cell = %(cell)s"
        taxonomy_params["cell"] = cell
    else:
        taxonomy_query += " AND cell IS NULL"

    taxonomy_query += " ORDER BY created_at DESC LIMIT 1"
    cursor.execute(taxonomy_query, taxonomy_params)
    current_deployment = cursor.fetchone()
    rollback_from_id = current_deployment["ID"] if current_deployment else None

    # Create new deployment as rollback
    new_deployment_id = str(uuid4())
    now = datetime.now(UTC)

    cursor.execute(
        """
        INSERT INTO deployments (
            id, created_at, updated_at, organisation,
            name, version, commit_sha, pipeline_extra_params,
            provider, cloud_account_id, region, cell,
            type, status, auto, description, notes,
            "trigger", source_deployment_id, rollback_from_deployment_id,
            build_uri, deployment_uri, resource,
            created_by_repo, created_by_workflow, created_by_actor
        ) VALUES (
            %(id)s, %(created_at)s, %(updated_at)s, %(organisation)s,
            %(name)s, %(version)s, %(commit_sha)s, %(pipeline_extra_params)s,
            %(provider)s, %(cloud_account_id)s, %(region)s, %(cell)s,
            %(type)s, %(status)s, %(auto)s, %(description)s, %(notes)s,
            %(trigger)s, %(source_deployment_id)s, %(rollback_from_deployment_id)s,
            %(build_uri)s, NULL, %(resource)s,
            %(created_by_repo)s, %(created_by_workflow)s, %(created_by_actor)s
        )
        """,
        {
            "id": new_deployment_id,
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
            "cell": rollback_source.get("CELL"),
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

    # Mark the deployment we're rolling back from as 'rolled_back'
    if rollback_from_id:
        cursor.execute(
            """
            UPDATE deployments
            SET status = %(status)s, updated_at = %(updated_at)s
            WHERE id = %(id)s AND organisation = %(organisation)s
            """,
            {
                "status": DeploymentStatus.rolled_back.value,
                "updated_at": now,
                "id": rollback_from_id,
                "organisation": token.organisation,
            },
        )

    # Record metric
    rollbacks_total.labels(
        organisation=token.organisation,
        provider=rollback_source["PROVIDER"],
    ).inc()

    cursor.execute("SELECT * FROM deployments WHERE id = %(id)s", {"id": new_deployment_id})
    return row_to_deployment(cursor.fetchone())  # type: ignore[arg-type]
