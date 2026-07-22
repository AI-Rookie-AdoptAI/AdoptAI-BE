"""Internal client for the dedicated STT/pipeline service."""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import UploadFile

from app.core.config import settings


class SttServiceError(RuntimeError):
    """Raised when the internal STT service cannot satisfy a request."""


def _headers() -> dict[str, str]:
    return {"X-Internal-API-Key": settings.STT_INTERNAL_API_KEY} if settings.STT_INTERNAL_API_KEY else {}


async def _json_or_error(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    if response.is_error:
        detail = payload.get("detail") if isinstance(payload, dict) else None
        raise SttServiceError(detail or "STT 서비스 요청에 실패했습니다.")
    return payload


async def transcribe_and_start(audio: UploadFile) -> dict[str, Any]:
    """Stream an uploaded audio file to STT and start its extraction pipeline."""
    await audio.seek(0)
    files = {
        "file": (
            audio.filename or "voice.webm",
            audio.file,
            audio.content_type or "application/octet-stream",
        )
    }
    timeout = httpx.Timeout(settings.STT_TIMEOUT_SECONDS, connect=10.0)
    try:
        async with httpx.AsyncClient(base_url=settings.STT_BASE_URL, timeout=timeout) as client:
            response = await client.post(
                "/stt/transcribe-and-start",
                params={"use_prompt": "true"},
                files=files,
                headers=_headers(),
            )
    except httpx.RequestError as exc:
        raise SttServiceError("STT 서비스에 연결할 수 없습니다.") from exc
    return await _json_or_error(response)


async def start(stt_text: str) -> dict[str, Any]:
    """Start the same slot-extraction pipeline from a typed message."""
    timeout = httpx.Timeout(settings.STT_TIMEOUT_SECONDS, connect=10.0)
    try:
        async with httpx.AsyncClient(base_url=settings.STT_BASE_URL, timeout=timeout) as client:
            response = await client.post(
                "/pipeline/start",
                json={"stt_text": stt_text},
                headers=_headers(),
            )
    except httpx.RequestError as exc:
        raise SttServiceError("STT 서비스에 연결할 수 없습니다.") from exc
    return await _json_or_error(response)


async def answer(session_id: str, answer_text: str) -> dict[str, Any]:
    timeout = httpx.Timeout(settings.STT_TIMEOUT_SECONDS, connect=10.0)
    try:
        async with httpx.AsyncClient(base_url=settings.STT_BASE_URL, timeout=timeout) as client:
            response = await client.post(
                "/pipeline/answer",
                json={"session_id": session_id, "answer": answer_text},
                headers=_headers(),
            )
    except httpx.RequestError as exc:
        raise SttServiceError("STT 서비스에 연결할 수 없습니다.") from exc
    return await _json_or_error(response)


async def complete(session_id: str) -> dict[str, Any]:
    timeout = httpx.Timeout(settings.STT_TIMEOUT_SECONDS, connect=10.0)
    try:
        async with httpx.AsyncClient(base_url=settings.STT_BASE_URL, timeout=timeout) as client:
            response = await client.post(
                "/pipeline/complete",
                json={"session_id": session_id},
                headers=_headers(),
            )
    except httpx.RequestError as exc:
        raise SttServiceError("STT 서비스에 연결할 수 없습니다.") from exc
    return await _json_or_error(response)


async def generate_all(slots: dict[str, Any]) -> dict[str, Any]:
    """Generate the three supported platform variants from completed slots."""
    timeout = httpx.Timeout(settings.STT_TIMEOUT_SECONDS, connect=10.0)
    try:
        async with httpx.AsyncClient(base_url=settings.STT_BASE_URL, timeout=timeout) as client:
            response = await client.post(
                "/notice/generate-all",
                json=slots,
                headers=_headers(),
            )
    except httpx.RequestError as exc:
        raise SttServiceError("STT 서비스에 연결할 수 없습니다.") from exc
    return await _json_or_error(response)
