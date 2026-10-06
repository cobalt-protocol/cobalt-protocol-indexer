import sys
import os
import logging
import argparse
from contextlib import asynccontextmanager

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "app"))

from fastapi import FastAPI
from app.configs import settings, create_db_and_tables
from app.utils.indexer import indexer_service
from app.utils.ipfs import check_ipfs_health

logger = logging.getLogger(__name__)


def parse_port(value: str | int | None, fallback: int = 8000) -> int:
    """Parse PORT with validation (1-65535), fallback on invalid."""
    if value is None:
        return fallback
    try:
        parsed = int(str(value).strip())
        if 1 <= parsed <= 65535:
            return parsed
        logger.warning(
            f"Invalid PORT value '{value}' — must be 1-65535, falling back to {fallback}."
        )
    except (ValueError, TypeError, AttributeError):
        logger.warning(f"Invalid PORT value '{value}' — falling back to {fallback}.")
    return fallback


def resolve_host_port(
    cli_host: str | None = None, cli_port: str | int | None = None
) -> tuple[str, int]:
    """
    Priority: CLI --host/--port > env HOST/PORT (via settings) > default 0.0.0.0:8000
    Env PORT/HOST are already loaded into settings via pydantic-settings (.env).
    """
    host = cli_host or os.getenv("HOST") or settings.host
    # CLI port takes precedence, then env PORT, then settings.port
    raw_port = cli_port if cli_port is not None else os.getenv("PORT")
    # settings.port is already parsed from env if PORT exists, but os.getenv covers explicit shell override
    port_source = raw_port if raw_port is not None else settings.port
    port = parse_port(port_source, fallback=8000)
    return host, port


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Performing IPFS health check on startup...")
    is_ipfs_healthy = await check_ipfs_health()
    if not is_ipfs_healthy:
        logger.critical(
            "CRITICAL: IPFS service (Kubo API / Gateway) is offline or unreachable! "
            "Stopping API service..."
        )
        raise RuntimeError(
            "IPFS service (Kubo API / Gateway) is offline or unreachable. API service stopped."
        )

    create_db_and_tables()
    await indexer_service.start()
    try:
        yield
    finally:
        await indexer_service.stop()


app = FastAPI(
    title=settings.app_name,
    debug=settings.debug if settings.is_dev else False,
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
    openapi_url=None if settings.is_production else "/openapi.json",
    lifespan=lifespan,
)


@app.get("/")
async def read_root_endpoint():
    ipfs_healthy = await check_ipfs_health()
    return {
        "message": "Welcome to the Web3 Indexer API!",
        "environment": settings.environment,
        "is_dev": settings.is_dev,
        "is_staging": settings.is_staging,
        "is_production": settings.is_production,
        "ipfs_status": "healthy" if ipfs_healthy else "unhealthy",
        "indexer_status": indexer_service.get_status(),
    }


if __name__ == "__main__":
    import uvicorn

    parser = argparse.ArgumentParser(description="Cobalt Protocol Indexer API")
    parser.add_argument(
        "--host", type=str, default=None, help="Bind host (env: HOST, default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port",
        "-p",
        type=str,
        default=None,
        help="Listen port (env: PORT, default: 8000)",
    )
    parser.add_argument(
        "--reload", action="store_true", help="Enable auto-reload (dev only)"
    )
    args = parser.parse_args()

    host, port = resolve_host_port(cli_host=args.host, cli_port=args.port)

    display_host = "localhost" if host == "0.0.0.0" else host
    logger.info(f"Starting {settings.app_name} on http://{display_host}:{port}/")
    logger.info(f"Bound to {host}:{port} (PORT={port} HOST={host})")

    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=args.reload,
        log_level="info" if settings.is_dev else "warning",
    )
