import os
import uuid

import aiofiles
from fastapi import UploadFile

from app.core.config import settings

_LOCAL_DIR = "/tmp/adoptai_uploads"


async def save_file(file: UploadFile, subdir: str) -> tuple[str, str]:
    """
    Save an uploaded file.

    In production: upload to S3 (settings.STORAGE_BUCKET) and return a CDN URL.
    In development: save locally and return a localhost URL.
    """
    ext = os.path.splitext(file.filename or "file")[1].lower()
    key = f"{subdir}/{uuid.uuid4()}{ext}"

    # TODO: replace with S3 upload when STORAGE_BUCKET is configured
    dest = os.path.join(_LOCAL_DIR, key)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    content = await file.read()
    async with aiofiles.open(dest, "wb") as f:
        await f.write(content)

    url = f"http://localhost:8000/static/{key}"
    return url, key
