from fastapi import APIRouter

from app.indexer.service import indexer_service

router = APIRouter(prefix="/indexer", tags=["Web3 Indexer"])


@router.get("/status")
def get_indexer_status():
    return indexer_service.get_status()

