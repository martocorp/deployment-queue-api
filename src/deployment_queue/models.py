"""Pydantic models and enums for the Deployment Queue API."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel


class Provider(str, Enum):
    """Cloud provider options."""

    gcp = "gcp"
    aws = "aws"
    azure = "azure"


class DeploymentType(str, Enum):
    """Deployment type options."""

    k8s = "k8s"
    terraform = "terraform"
    data_pipeline = "data_pipeline"


class DeploymentStatus(str, Enum):
    """Deployment status options."""

    scheduled = "scheduled"
    in_progress = "in_progress"
    deployed = "deployed"
    skipped = "skipped"
    failed = "failed"


class DeploymentCreate(BaseModel):
    """Model for creating a new deployment."""

    name: str
    version: str
    commit_sha: Optional[str] = None
    pipeline_extra_params: Optional[str] = None
    provider: Provider
    cloud_account_id: Optional[str] = None
    region: Optional[str] = None
    environment: str
    cell: Optional[str] = None
    type: DeploymentType
    auto: bool = True
    description: Optional[str] = None
    notes: Optional[str] = None
    build_uri: Optional[str] = None
    deployment_uri: Optional[str] = None
    resource: Optional[str] = None


class DeploymentUpdate(BaseModel):
    """Model for updating an existing deployment."""

    status: Optional[DeploymentStatus] = None
    notes: Optional[str] = None
    deployment_uri: Optional[str] = None


class StatusUpdate(BaseModel):
    """Model for updating deployment status via taxonomy."""

    status: DeploymentStatus


class RollbackRequest(BaseModel):
    """Model for rollback request."""

    target_version: Optional[str] = None


class Deployment(BaseModel):
    """Full deployment model for responses."""

    id: str
    created_at: datetime
    updated_at: datetime
    name: str
    version: str
    commit_sha: Optional[str] = None
    pipeline_extra_params: Optional[str] = None
    provider: Provider
    cloud_account_id: Optional[str] = None
    region: Optional[str] = None
    environment: str
    cell: Optional[str] = None
    type: DeploymentType
    status: DeploymentStatus = DeploymentStatus.scheduled
    auto: bool = True
    description: Optional[str] = None
    notes: Optional[str] = None
    build_uri: Optional[str] = None
    deployment_uri: Optional[str] = None
    resource: Optional[str] = None


class TaxonomyQuery(BaseModel):
    """Query parameters for taxonomy-based operations."""

    name: str
    environment: str
    provider: Provider
    cloud_account_id: str
    region: str
    cell: Optional[str] = None


def row_to_deployment(row: dict) -> Deployment:
    """Convert a Snowflake row (uppercase keys) to a Deployment model."""
    return Deployment(
        id=row["ID"],
        created_at=row["CREATED_AT"],
        updated_at=row["UPDATED_AT"],
        name=row["NAME"],
        version=row["VERSION"],
        commit_sha=row.get("COMMIT_SHA"),
        pipeline_extra_params=row.get("PIPELINE_EXTRA_PARAMS"),
        provider=row["PROVIDER"],
        cloud_account_id=row.get("CLOUD_ACCOUNT_ID"),
        region=row.get("REGION"),
        environment=row["ENVIRONMENT"],
        cell=row.get("CELL"),
        type=row["TYPE"],
        status=row["STATUS"],
        auto=row.get("AUTO", True),
        description=row.get("DESCRIPTION"),
        notes=row.get("NOTES"),
        build_uri=row.get("BUILD_URI"),
        deployment_uri=row.get("DEPLOYMENT_URI"),
        resource=row.get("RESOURCE"),
    )
