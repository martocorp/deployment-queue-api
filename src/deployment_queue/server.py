"""Server runner for the Deployment Queue API.

Runs both the main API server and the management server (metrics/health) on separate ports.
"""

import asyncio
import signal
import sys

import uvicorn

from deployment_queue.config import get_settings


async def run_servers() -> None:
    """Run both API and management servers concurrently."""
    settings = get_settings()

    api_config = uvicorn.Config(
        "deployment_queue.main:app",
        host="0.0.0.0",  # nosec B104 - intentionally bind to all interfaces for container use
        port=settings.api_port,
        log_level="info",
    )
    api_server = uvicorn.Server(api_config)

    management_config = uvicorn.Config(
        "deployment_queue.management:management_app",
        host="0.0.0.0",  # nosec B104 - intentionally bind to all interfaces for container use
        port=settings.management_port,
        log_level="info",
    )
    management_server = uvicorn.Server(management_config)

    # Handle shutdown signals
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(
            sig,
            lambda: asyncio.create_task(shutdown(api_server, management_server)),
        )

    print(f"Starting API server on port {settings.api_port}")
    print(f"Starting management server on port {settings.management_port}")
    print(f"  - Health check: http://localhost:{settings.management_port}/health")
    print(f"  - Readiness: http://localhost:{settings.management_port}/ready")
    print(f"  - Metrics: http://localhost:{settings.management_port}/metrics")

    await asyncio.gather(
        api_server.serve(),
        management_server.serve(),
    )


async def shutdown(api_server: uvicorn.Server, management_server: uvicorn.Server) -> None:
    """Gracefully shutdown both servers."""
    print("\nShutting down servers...")
    api_server.should_exit = True
    management_server.should_exit = True


def main() -> None:
    """Entry point for the server."""
    try:
        asyncio.run(run_servers())
    except KeyboardInterrupt:
        print("\nShutdown complete.")
        sys.exit(0)


if __name__ == "__main__":
    main()
