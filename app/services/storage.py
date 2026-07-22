import logging
import os
import uuid
from functools import lru_cache
from typing import Any

import aiofiles
import boto3
from botocore.config import Config
from fastapi import UploadFile
from starlette.concurrency import run_in_threadpool

from app.core.config import settings

logger = logging.getLogger(__name__)


class FileTooLargeError(ValueError):
    pass


@lru_cache(maxsize=1)
def _s3_client() -> Any:
    return boto3.client(
        "s3",
        endpoint_url=settings.S3_ENDPOINT_URL,
        region_name=settings.S3_REGION,
        aws_access_key_id=settings.S3_ACCESS_KEY_ID,
        aws_secret_access_key=settings.S3_SECRET_ACCESS_KEY,
        # Supabase Storage는 virtual-host 방식 주소를 받지 않는다.
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def _public_url(key: str) -> str:
    if settings.SUPABASE_URL:
        base = settings.SUPABASE_URL.rstrip("/")
        return f"{base}/storage/v1/object/public/{settings.S3_BUCKET}/{key}"
    if "supabase.co" in settings.S3_ENDPOINT_URL:
        raise RuntimeError("Supabase Storage 사용 시 SUPABASE_URL 설정이 필요합니다")
    # Supabase 외 S3 호환 저장소(MinIO 등)용 대체 경로.
    return f"{settings.S3_ENDPOINT_URL.rstrip('/')}/{settings.S3_BUCKET}/{key}"


def _remove(path: str) -> None:
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


async def _stream_to_disk(file: UploadFile, dest: str, max_bytes: int | None) -> None:
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    written = 0
    try:
        async with aiofiles.open(dest, "wb") as target:
            while chunk := await file.read(1024 * 1024):
                written += len(chunk)
                if max_bytes is not None and written > max_bytes:
                    raise FileTooLargeError(f"file exceeds {max_bytes} bytes")
                await target.write(chunk)
    except Exception:
        _remove(dest)
        raise


async def save_file(
    file: UploadFile,
    subdir: str,
    *,
    max_bytes: int | None = None,
    keep_local: bool = False,
) -> tuple[str, str]:
    """
    Save an uploaded file and return its (url, key).

    S3(Supabase Storage)가 설정돼 있으면 그쪽에 올리고 public URL을 돌려준다.
    미설정이면 LOCAL_UPLOAD_DIR에 저장하고 /static 상대 URL을 돌려준다.

    업로드는 항상 디스크를 한 번 거친다. 크기 상한을 스트리밍 중에 강제할 수 있고,
    vision 추론이 로컬 경로를 필요로 하기 때문이다. keep_local=True면 S3 백엔드에서도
    그 사본을 남기며, 호출자가 다 쓴 뒤 discard_local(key)로 정리해야 한다.
    """
    clean_subdir = subdir.strip("/")
    if not clean_subdir or "/" in clean_subdir or clean_subdir in {".", ".."}:
        raise ValueError("invalid upload subdirectory")
    ext = os.path.splitext(file.filename or "file")[1].lower()
    key = f"{clean_subdir}/{uuid.uuid4()}{ext}"

    if (
        settings.storage_backend == "s3"
        and "supabase.co" in settings.S3_ENDPOINT_URL
        and not settings.SUPABASE_URL
    ):
        raise RuntimeError("Supabase Storage 사용 시 SUPABASE_URL 설정이 필요합니다")

    dest = local_path(key)
    await _stream_to_disk(file, dest, max_bytes)

    if settings.storage_backend != "s3":
        return f"/static/{key}", key

    try:
        await run_in_threadpool(
            _s3_client().upload_file,
            dest,
            settings.S3_BUCKET,
            key,
            ExtraArgs={"ContentType": file.content_type or "application/octet-stream"},
        )
    except Exception:
        _remove(dest)
        raise

    if not keep_local:
        _remove(dest)
    return _public_url(key), key


def local_path(key: str) -> str:
    """save_file()이 반환한 key로부터 로컬 디스크 경로를 계산 (vision 서비스 등 로컬 추론용)."""
    return os.path.join(settings.LOCAL_UPLOAD_DIR, key)


def discard_local(key: str) -> None:
    """
    S3 백엔드에서 keep_local로 남겨둔 임시 사본을 지운다.

    로컬 백엔드에서는 그 파일이 /static으로 서빙되는 원본이므로 건드리지 않는다.
    """
    if settings.storage_backend != "s3":
        return
    _remove(local_path(key))


async def delete_file(key: str) -> None:
    """Rollback an upload from local disk and, when configured, S3."""
    _remove(local_path(key))
    if settings.storage_backend == "s3":
        try:
            await run_in_threadpool(
                _s3_client().delete_object,
                Bucket=settings.S3_BUCKET,
                Key=key,
            )
        except Exception:
            logger.exception("Failed to roll back S3 upload %s", key)
