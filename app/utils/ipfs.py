import logging
import httpx
from app.configs import settings

logger = logging.getLogger(__name__)


async def check_ipfs_health(timeout: float = 3.0) -> bool:
    candidates = [
        ("POST", settings.kubo_api_url),
        ("GET", settings.kubo_gateway_url),
    ]

    async with httpx.AsyncClient() as client:
        for method, url in candidates:
            try:
                if method == "POST":
                    res = await client.post(url, timeout=timeout)
                else:
                    res = await client.get(url, timeout=timeout)

                if res.status_code in (200, 404, 405):
                    logger.info(
                        f"IPFS health check passed via {url} (status: {res.status_code})"
                    )
                    return True
            except Exception as e:
                logger.debug(f"IPFS health check attempt to {url} failed: {e}")

    logger.warning("IPFS health check failed: No configured IPFS endpoint responded.")
    return False
