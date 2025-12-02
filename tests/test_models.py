"""Tests for Pydantic models."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from deployment_queue.models import (
    Deployment,
    DeploymentCreate,
    DeploymentStatus,
    DeploymentType,
    DeploymentUpdate,
    Provider,
    row_to_deployment,
)


class TestEnums:
    """Tests for enum values."""

    def test_provider_values(self):
        assert Provider.gcp.value == "gcp"
        assert Provider.aws.value == "aws"
        assert Provider.azure.value == "azure"

    def test_deployment_type_values(self):
        assert DeploymentType.k8s.value == "k8s"
        assert DeploymentType.terraform.value == "terraform"
        assert DeploymentType.data_pipeline.value == "data_pipeline"

    def test_deployment_status_values(self):
        assert DeploymentStatus.scheduled.value == "scheduled"
        assert DeploymentStatus.in_progress.value == "in_progress"
        assert DeploymentStatus.deployed.value == "deployed"
        assert DeploymentStatus.skipped.value == "skipped"
        assert DeploymentStatus.failed.value == "failed"


class TestDeploymentCreate:
    """Tests for DeploymentCreate model."""

    def test_valid_deployment_create(self):
        deployment = DeploymentCreate(
            name="test-service",
            version="1.0.0",
            provider=Provider.gcp,
            environment="production",
            type=DeploymentType.k8s,
        )
        assert deployment.name == "test-service"
        assert deployment.version == "1.0.0"
        assert deployment.provider == Provider.gcp
        assert deployment.auto is True

    def test_deployment_create_with_all_fields(self):
        deployment = DeploymentCreate(
            name="test-service",
            version="1.0.0",
            commit_sha="abc123",
            pipeline_extra_params='{"key": "value"}',
            provider=Provider.aws,
            cloud_account_id="123456789",
            region="us-east-1",
            environment="staging",
            cell="cell-1",
            type=DeploymentType.terraform,
            auto=False,
            description="Test deployment",
            notes="Some notes",
            build_uri="https://build.example.com",
            deployment_uri="https://deploy.example.com",
            resource="arn:aws:lambda:us-east-1:123456789:function:test",
        )
        assert deployment.commit_sha == "abc123"
        assert deployment.auto is False

    def test_deployment_create_missing_required_fields(self):
        with pytest.raises(ValidationError):
            DeploymentCreate(
                name="test-service",
                version="1.0.0",
            )

    def test_deployment_create_invalid_provider(self):
        with pytest.raises(ValidationError):
            DeploymentCreate(
                name="test-service",
                version="1.0.0",
                provider="invalid",
                environment="production",
                type=DeploymentType.k8s,
            )


class TestDeploymentUpdate:
    """Tests for DeploymentUpdate model."""

    def test_deployment_update_status_only(self):
        update = DeploymentUpdate(status=DeploymentStatus.deployed)
        assert update.status == DeploymentStatus.deployed
        assert update.notes is None

    def test_deployment_update_notes_only(self):
        update = DeploymentUpdate(notes="Updated notes")
        assert update.status is None
        assert update.notes == "Updated notes"

    def test_deployment_update_all_fields(self):
        update = DeploymentUpdate(
            status=DeploymentStatus.failed,
            notes="Deployment failed",
            deployment_uri="https://deploy.example.com",
        )
        assert update.status == DeploymentStatus.failed
        assert update.notes == "Deployment failed"
        assert update.deployment_uri == "https://deploy.example.com"

    def test_deployment_update_exclude_unset(self):
        update = DeploymentUpdate(status=DeploymentStatus.deployed)
        data = update.model_dump(exclude_unset=True)
        assert "status" in data
        assert "notes" not in data
        assert "deployment_uri" not in data


class TestDeployment:
    """Tests for full Deployment model."""

    def test_valid_deployment(self):
        now = datetime.now(UTC)
        deployment = Deployment(
            id="test-uuid",
            created_at=now,
            updated_at=now,
            name="test-service",
            version="1.0.0",
            provider=Provider.gcp,
            environment="production",
            type=DeploymentType.k8s,
            status=DeploymentStatus.scheduled,
        )
        assert deployment.id == "test-uuid"
        assert deployment.status == DeploymentStatus.scheduled


class TestRowToDeployment:
    """Tests for row_to_deployment function."""

    def test_row_to_deployment_basic(self):
        now = datetime.now(UTC)
        row = {
            "ID": "test-uuid",
            "CREATED_AT": now,
            "UPDATED_AT": now,
            "NAME": "test-service",
            "VERSION": "1.0.0",
            "COMMIT_SHA": "abc123",
            "PIPELINE_EXTRA_PARAMS": None,
            "PROVIDER": "gcp",
            "CLOUD_ACCOUNT_ID": "project-123",
            "REGION": "us-central1",
            "ENVIRONMENT": "production",
            "CELL": None,
            "TYPE": "k8s",
            "STATUS": "scheduled",
            "AUTO": True,
            "DESCRIPTION": "Test",
            "NOTES": None,
            "BUILD_URI": None,
            "DEPLOYMENT_URI": None,
            "RESOURCE": None,
        }

        deployment = row_to_deployment(row)

        assert deployment.id == "test-uuid"
        assert deployment.name == "test-service"
        assert deployment.provider == Provider.gcp
        assert deployment.status == DeploymentStatus.scheduled
        assert deployment.cell is None

    def test_row_to_deployment_with_cell(self):
        now = datetime.now(UTC)
        row = {
            "ID": "test-uuid",
            "CREATED_AT": now,
            "UPDATED_AT": now,
            "NAME": "test-service",
            "VERSION": "1.0.0",
            "COMMIT_SHA": None,
            "PIPELINE_EXTRA_PARAMS": None,
            "PROVIDER": "aws",
            "CLOUD_ACCOUNT_ID": "123456789",
            "REGION": "us-east-1",
            "ENVIRONMENT": "staging",
            "CELL": "cell-1",
            "TYPE": "terraform",
            "STATUS": "deployed",
            "AUTO": False,
            "DESCRIPTION": None,
            "NOTES": "Some notes",
            "BUILD_URI": "https://build.example.com",
            "DEPLOYMENT_URI": "https://deploy.example.com",
            "RESOURCE": "arn:aws:s3:::bucket",
        }

        deployment = row_to_deployment(row)

        assert deployment.cell == "cell-1"
        assert deployment.provider == Provider.aws
        assert deployment.status == DeploymentStatus.deployed
        assert deployment.auto is False
