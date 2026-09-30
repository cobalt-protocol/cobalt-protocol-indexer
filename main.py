import sys
import os
import logging
from contextlib import asynccontextmanager

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "app"))

from fastapi import FastAPI
from app.configs import settings, create_db_and_tables
from app.utils.indexer import indexer_service
from app.utils.ipfs import check_ipfs_health

logger = logging.getLogger(__name__)


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
