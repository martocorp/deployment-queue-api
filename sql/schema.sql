-- Snowflake DDL for Deployment Queue API

CREATE DATABASE DEPLOYMENTS_DB;

USE DEPLOYMENTS_DB;

CREATE TABLE IF NOT EXISTS deployments (
  id STRING PRIMARY KEY,
  created_at TIMESTAMP_NTZ NOT NULL,
  updated_at TIMESTAMP_NTZ NOT NULL,
  organisation STRING NOT NULL,
  name STRING NOT NULL,
  version STRING NOT NULL,
  commit_sha STRING,
  provider STRING NOT NULL,
  cloud_account_id STRING,
  region STRING,
  cell STRING,
  type STRING NOT NULL,
  status STRING NOT NULL DEFAULT 'scheduled',
  auto BOOLEAN DEFAULT TRUE,
  description STRING,
  notes STRING,
  "trigger" STRING NOT NULL DEFAULT 'manual',
  source_deployment_id STRING,
  rollback_from_deployment_id STRING,
  pipeline_extra_params STRING,
  build_uri STRING,
  deployment_uri STRING,
  resource STRING,
  created_by_repo STRING,
  created_by_workflow STRING,
  created_by_actor STRING
);
