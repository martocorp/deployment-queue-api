"""Prometheus metrics for the Deployment Queue API."""

from prometheus_client import Counter, Histogram, Info

# Application info
app_info = Info("deployment_queue", "Deployment Queue API information")
app_info.info({"version": "0.1.0"})

# HTTP request metrics
http_requests_total = Counter(
    "http_requests_total",
    "Total number of HTTP requests",
    ["method", "endpoint", "status_code"],
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

# Deployment-specific metrics
deployments_created_total = Counter(
    "deployments_created_total",
    "Total number of deployments created",
    ["organisation", "provider", "trigger"],
)

deployments_updated_total = Counter(
    "deployments_updated_total",
    "Total number of deployment status updates",
    ["organisation", "status"],
)

deployments_skipped_total = Counter(
    "deployments_skipped_total",
    "Total number of deployments auto-skipped",
    ["organisation"],
)

rollbacks_total = Counter(
    "rollbacks_total",
    "Total number of rollback deployments created",
    ["organisation", "provider"],
)

# Database metrics
db_query_duration_seconds = Histogram(
    "db_query_duration_seconds",
    "Database query duration in seconds",
    ["operation"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
)

# Authentication metrics
auth_requests_total = Counter(
    "auth_requests_total",
    "Total number of authentication attempts",
    ["method", "success"],
)
