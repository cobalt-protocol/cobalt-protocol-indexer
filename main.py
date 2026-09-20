import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "app"))

from fastapi import FastAPI
from app.configs import Settings

app = FastAPI(
    title=Settings.app_name,
    debug=Settings.debug if Settings.is_dev else False,
    docs_url=None if Settings.is_production else "/docs",
    redoc_url=None if Settings.is_production else "/redoc",
    openapi_url=None if Settings.is_production else "/openapi.json",
)


@app.get("/")
async def read_root_endpoint():
    return {
        "message": "Welcome to the API!",
        "environment": Settings.environment,
        "is_dev": Settings.is_dev,
        "is_staging": Settings.is_staging,
        "is_production": Settings.is_production,
    }
