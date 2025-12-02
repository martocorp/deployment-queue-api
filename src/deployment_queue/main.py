"""FastAPI application and endpoints for the Deployment Queue API."""

from datetime import UTC, datetime
from typing import Any, Optional
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Query
from snowflake.connector import DictCursor

from deployment_queue.database import get_cursor
from deployment_queue.models import (
    Deployment,
    DeploymentCreate,
    DeploymentStatus,
    DeploymentUpdate,
    Provider,
    RollbackRequest,
    StatusUpdate,
    row_to_deployment,
)

app = FastAPI(
    title="Deployment Queue API",
    description="REST API to manage a deployment queue across multiple cloud providers",
    version="0.1.0",
)


def build_taxonomy_where_clause(
    name: str,
    environment: str,
    provider: Provider,
    cloud_account_id: str,
    region: str,
    cell: Optional[str],
) -> tuple[str, dict]:
    """Build WHERE clause for taxonomy-based queries."""
    params = {
        "name": name,
        "environment": environment,
        "provider": provider.value,
        "cloud_account_id": cloud_account_id,
        "region": region,
    }

    if cell is None:
        where = """
            name = %(name)s
            AND environment = %(environment)s
            AND provider = %(provider)s
            AND cloud_account_id = %(cloud_account_id)s
            AND region = %(region)s
            AND cell IS NULL
        """
    else:
        where = """
            name = %(name)s
            AND environment = %(environment)s
            AND provider = %(provider)s
            AND cloud_account_id = %(cloud_account_id)s
            AND region = %(region)s
            AND cell = %(cell)s
        """
        params["cell"] = cell

    return where, params


@app.get("/v1/deployments", response_model=list[Deployment])
def list_deployments(
    status: Optional[DeploymentStatus] = None,
    environment: Optional[str] = None,
    provider: Optional[Provider] = None,
    limit: int = Query(default=100, le=1000),
    cursor: DictCursor = Depends(get_cursor),
) -> list[Deployment]:
    """List deployments with optional filters."""
    query = "SELECT * FROM deployments WHERE 1=1"
    params: dict[str, Any] = {}

    if status:
        query += " AND status = %(status)s"
        params["status"] = status.value
    if environment:
        query += " AND environment = %(environment)s"
        params["environment"] = environment
    if provider:
        query += " AND provider = %(provider)s"
        params["provider"] = provider.value

    query += " ORDER BY created_at DESC LIMIT %(limit)s"
    params["limit"] = limit

    cursor.execute(query, params)
    rows = cursor.fetchall()

    return [row_to_deployment(row) for row in rows]


@app.post("/v1/deployments", response_model=Deployment, status_code=201)
def create_deployment(
    deployment: DeploymentCreate,
    cursor: DictCursor = Depends(get_cursor),
) -> Deployment:
    """Create a new deployment."""
    deployment_id = str(uuid4())
    now = datetime.now(UTC)

    query = """
        INSERT INTO deployments (
            id, created_at, updated_at, name, version, commit_sha,
            pipeline_extra_params, provider, cloud_account_id, region,
            environment, cell, type, status, auto, description,
            notes, build_uri, deployment_uri, resource
        ) VALUES (
            %(id)s, %(created_at)s, %(updated_at)s, %(name)s, %(version)s,
            %(commit_sha)s, %(pipeline_extra_params)s, %(provider)s,
            %(cloud_account_id)s, %(region)s, %(environment)s, %(cell)s,
            %(type)s, %(status)s, %(auto)s, %(description)s, %(notes)s,
            %(build_uri)s, %(deployment_uri)s, %(resource)s
        )
    """

    params = {
        "id": deployment_id,
        "created_at": now,
        "updated_at": now,
        "name": deployment.name,
        "version": deployment.version,
        "commit_sha": deployment.commit_sha,
        "pipeline_extra_params": deployment.pipeline_extra_params,
        "provider": deployment.provider.value,
        "cloud_account_id": deployment.cloud_account_id,
        "region": deployment.region,
        "environment": deployment.environment,
        "cell": deployment.cell,
        "type": deployment.type.value,
        "status": DeploymentStatus.scheduled.value,
        "auto": deployment.auto,
        "description": deployment.description,
        "notes": deployment.notes,
        "build_uri": deployment.build_uri,
        "deployment_uri": deployment.deployment_uri,
        "resource": deployment.resource,
    }

    cursor.execute(query, params)

    return Deployment(
        id=deployment_id,
        created_at=now,
        updated_at=now,
        status=DeploymentStatus.scheduled,
        **deployment.model_dump(),
    )


@app.get("/v1/deployments/current", response_model=Deployment)
def get_current_deployment(
    name: str = Query(...),
    environment: str = Query(...),
    provider: Provider = Query(...),
    cloud_account_id: str = Query(...),
    region: str = Query(...),
    cell: Optional[str] = Query(default=None),
    cursor: DictCursor = Depends(get_cursor),
) -> Deployment:
    """Get the current (most recent) deployment for a component by taxonomy."""
    where, params = build_taxonomy_where_clause(
        name, environment, provider, cloud_account_id, region, cell
    )

    query = f"""
        SELECT * FROM deployments
        WHERE {where}
        ORDER BY created_at DESC
        LIMIT 1
    """  # nosec B608 - where clause is built with hardcoded strings

    cursor.execute(query, params)
    row = cursor.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="No deployment found for the given taxonomy")

    return row_to_deployment(row)


@app.patch("/v1/deployments/current/status", response_model=Deployment)
def update_current_status(
    status_update: StatusUpdate,
    name: str = Query(...),
    environment: str = Query(...),
    provider: Provider = Query(...),
    cloud_account_id: str = Query(...),
    region: str = Query(...),
    cell: Optional[str] = Query(default=None),
    cursor: DictCursor = Depends(get_cursor),
) -> Deployment:
    """Update the status of the current deployment by taxonomy."""
    where, params = build_taxonomy_where_clause(
        name, environment, provider, cloud_account_id, region, cell
    )

    select_query = f"""
        SELECT id FROM deployments
        WHERE {where}
        ORDER BY created_at DESC
        LIMIT 1
    """  # nosec B608 - where clause is built with hardcoded strings

    cursor.execute(select_query, params)
    row = cursor.fetchone()

    if not row:
        raise HTTPException(
            status_code=404, detail="No deployment found for the given taxonomy"
        )

    deployment_id = row["ID"]
    now = datetime.now(UTC)

    update_query = """
        UPDATE deployments
        SET status = %(status)s, updated_at = %(updated_at)s
        WHERE id = %(id)s
    """

    cursor.execute(
        update_query,
        {"status": status_update.status.value, "updated_at": now, "id": deployment_id},
    )

    cursor.execute("SELECT * FROM deployments WHERE id = %(id)s", {"id": deployment_id})
    updated_row = cursor.fetchone()

    return row_to_deployment(updated_row)  # type: ignore[arg-type]


@app.get("/v1/deployments/history", response_model=list[Deployment])
def get_deployment_history(
    name: str = Query(...),
    environment: str = Query(...),
    provider: Provider = Query(...),
    cloud_account_id: str = Query(...),
    region: str = Query(...),
    cell: Optional[str] = Query(default=None),
    limit: int = Query(default=50, le=500),
    cursor: DictCursor = Depends(get_cursor),
) -> list[Deployment]:
    """Get deployment history for a component by taxonomy."""
    where, params = build_taxonomy_where_clause(
        name, environment, provider, cloud_account_id, region, cell
    )
    params["limit"] = limit

    query = f"""
        SELECT * FROM deployments
        WHERE {where}
        ORDER BY created_at DESC
        LIMIT %(limit)s
    """  # nosec B608 - where clause is built with hardcoded strings

    cursor.execute(query, params)
    rows = cursor.fetchall()

    return [row_to_deployment(row) for row in rows]


@app.post("/v1/deployments/rollback", response_model=Deployment, status_code=201)
def rollback_deployment(
    rollback: RollbackRequest,
    name: str = Query(...),
    environment: str = Query(...),
    provider: Provider = Query(...),
    cloud_account_id: str = Query(...),
    region: str = Query(...),
    cell: Optional[str] = Query(default=None),
    cursor: DictCursor = Depends(get_cursor),
) -> Deployment:
    """Create a rollback deployment based on a previous deployment."""
    where, params = build_taxonomy_where_clause(
        name, environment, provider, cloud_account_id, region, cell
    )

    if rollback.target_version:
        params["target_version"] = rollback.target_version
        query = f"""
            SELECT * FROM deployments
            WHERE {where} AND version = %(target_version)s
            ORDER BY created_at DESC
            LIMIT 1
        """  # nosec B608 - where clause is built with hardcoded strings
    else:
        query = f"""
            SELECT * FROM deployments
            WHERE {where}
            ORDER BY created_at DESC
            LIMIT 2
        """  # nosec B608 - where clause is built with hardcoded strings

    cursor.execute(query, params)
    rows = cursor.fetchall()

    if rollback.target_version:
        if not rows:
            raise HTTPException(
                status_code=404,
                detail=f"No deployment found with version {rollback.target_version}",
            )
        source_deployment = rows[0]
    else:
        if len(rows) < 2:
            raise HTTPException(
                status_code=404, detail="No previous deployment found to rollback to"
            )
        source_deployment = rows[1]

    deployment_id = str(uuid4())
    now = datetime.now(UTC)
    rollback_note = f"Rollback to version {source_deployment['VERSION']}"
    existing_notes = source_deployment.get("NOTES") or ""
    notes = f"{existing_notes}\n{rollback_note}".strip() if existing_notes else rollback_note

    insert_query = """
        INSERT INTO deployments (
            id, created_at, updated_at, name, version, commit_sha,
            pipeline_extra_params, provider, cloud_account_id, region,
            environment, cell, type, status, auto, description,
            notes, build_uri, deployment_uri, resource
        ) VALUES (
            %(id)s, %(created_at)s, %(updated_at)s, %(name)s, %(version)s,
            %(commit_sha)s, %(pipeline_extra_params)s, %(provider)s,
            %(cloud_account_id)s, %(region)s, %(environment)s, %(cell)s,
            %(type)s, %(status)s, %(auto)s, %(description)s, %(notes)s,
            %(build_uri)s, %(deployment_uri)s, %(resource)s
        )
    """

    insert_params = {
        "id": deployment_id,
        "created_at": now,
        "updated_at": now,
        "name": source_deployment["NAME"],
        "version": source_deployment["VERSION"],
        "commit_sha": source_deployment.get("COMMIT_SHA"),
        "pipeline_extra_params": source_deployment.get("PIPELINE_EXTRA_PARAMS"),
        "provider": source_deployment["PROVIDER"],
        "cloud_account_id": source_deployment.get("CLOUD_ACCOUNT_ID"),
        "region": source_deployment.get("REGION"),
        "environment": source_deployment["ENVIRONMENT"],
        "cell": source_deployment.get("CELL"),
        "type": source_deployment["TYPE"],
        "status": DeploymentStatus.scheduled.value,
        "auto": False,
        "description": source_deployment.get("DESCRIPTION"),
        "notes": notes,
        "build_uri": source_deployment.get("BUILD_URI"),
        "deployment_uri": source_deployment.get("DEPLOYMENT_URI"),
        "resource": source_deployment.get("RESOURCE"),
    }

    cursor.execute(insert_query, insert_params)

    cursor.execute("SELECT * FROM deployments WHERE id = %(id)s", {"id": deployment_id})
    new_row = cursor.fetchone()

    return row_to_deployment(new_row)  # type: ignore[arg-type]


@app.get("/v1/deployments/{deployment_id}", response_model=Deployment)
def get_deployment(
    deployment_id: str,
    cursor: DictCursor = Depends(get_cursor),
) -> Deployment:
    """Get a deployment by ID."""
    query = "SELECT * FROM deployments WHERE id = %(id)s"

    cursor.execute(query, {"id": deployment_id})
    row = cursor.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Deployment not found")

    return row_to_deployment(row)


@app.patch("/v1/deployments/{deployment_id}", response_model=Deployment)
def update_deployment(
    deployment_id: str,
    update: DeploymentUpdate,
    cursor: DictCursor = Depends(get_cursor),
) -> Deployment:
    """Update a deployment by ID."""
    update_data = update.model_dump(exclude_unset=True)

    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    cursor.execute(
        "SELECT * FROM deployments WHERE id = %(id)s", {"id": deployment_id}
    )
    row = cursor.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Deployment not found")

    set_clauses = []
    params = {"id": deployment_id, "updated_at": datetime.now(UTC)}

    for field, value in update_data.items():
        if field == "status" and value:
            params[field] = value.value
        else:
            params[field] = value
        set_clauses.append(f"{field} = %({field})s")

    set_clauses.append("updated_at = %(updated_at)s")

    query = f"UPDATE deployments SET {', '.join(set_clauses)} WHERE id = %(id)s"  # nosec B608
    cursor.execute(query, params)

    cursor.execute("SELECT * FROM deployments WHERE id = %(id)s", {"id": deployment_id})
    updated_row = cursor.fetchone()

    return row_to_deployment(updated_row)  # type: ignore[arg-type]


@app.get("/health")
def health_check() -> dict:
    """Health check endpoint."""
    return {"status": "healthy"}
