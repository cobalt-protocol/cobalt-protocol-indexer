import sys
import os
from contextlib import asynccontextmanager

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "app"))

from fastapi import FastAPI
from app.configs import settings
from app.utils.indexer import indexer_service
from app.indexer import indexer_router


@asynccontextmanager
async def lifespan(app: FastAPI):
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

app.include_router(indexer_router)


@app.get("/")
async def read_root_endpoint():
    return {
        "message": "Welcome to the Web3 Indexer API!",
        "environment": settings.environment,
        "is_dev": settings.is_dev,
        "is_staging": settings.is_staging,
        "is_production": settings.is_production,
        "indexer_status": indexer_service.get_status(),
    }
