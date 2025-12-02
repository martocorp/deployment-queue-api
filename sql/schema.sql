-- Snowflake DDL for Deployment Queue API

CREATE TABLE IF NOT EXISTS deployments (
    id STRING PRIMARY KEY,
    created_at TIMESTAMP_NTZ NOT NULL,
    updated_at TIMESTAMP_NTZ NOT NULL,
    name STRING NOT NULL,
    version STRING NOT NULL,
    commit_sha STRING,
    pipeline_extra_params STRING,
    provider STRING NOT NULL,
    cloud_account_id STRING,
    region STRING,
    environment STRING NOT NULL,
    cell STRING,
    type STRING NOT NULL,
    status STRING NOT NULL DEFAULT 'scheduled',
    auto BOOLEAN DEFAULT TRUE,
    description STRING,
    notes STRING,
    build_uri STRING,
    deployment_uri STRING,
    resource STRING
);

-- Index for taxonomy-based queries
CREATE INDEX IF NOT EXISTS idx_deployments_taxonomy
ON deployments (name, environment, provider, cloud_account_id, region, cell);

-- Index for status filtering
CREATE INDEX IF NOT EXISTS idx_deployments_status
ON deployments (status);

-- Index for created_at ordering
CREATE INDEX IF NOT EXISTS idx_deployments_created_at
ON deployments (created_at DESC);
