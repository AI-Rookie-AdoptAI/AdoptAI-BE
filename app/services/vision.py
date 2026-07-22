"""HTTP client for the dedicated Vision inference service."""

from __future__ import annotations

import logging
from pathlib import Path

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


async def select_representative(image_paths: list[str]) -> tuple[int, int]:
    if len(image_paths) == 1:
        return 0, 100

    files = []
    handles = []
    try:
        for path in image_paths:
            handle = Path(path).open("rb")
            handles.append(handle)
            files.append(("images", (Path(path).name, handle, "application/octet-stream")))

        timeout = httpx.Timeout(settings.VISION_TIMEOUT_SECONDS, connect=10.0)
        async with httpx.AsyncClient(base_url=settings.VISION_BASE_URL, timeout=timeout) as client:
            response = await client.post("/select-best-photo", files=files)
            response.raise_for_status()
            payload = response.json()
    except (OSError, httpx.HTTPError, ValueError, KeyError, TypeError):
        logger.exception("Vision service failed; falling back to the first photo")
        return 0, 0
    finally:
        for handle in handles:
            handle.close()

    scores = payload.get("scores") or []
    best_index = int(payload["best_index"])
    if not 0 <= best_index < len(image_paths):
        return 0, 0

    if len(scores) <= 1:
        return best_index, 100
    ordered = sorted((float(item["score"]) for item in scores), reverse=True)
    margin = max(0.0, ordered[0] - ordered[1])
    confidence = min(100, max(0, round(50 + margin / 2)))
    return best_index, confidence
