from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.core.config import settings
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.upload import UploadResponse
from app.services.storage import FileTooLargeError, save_file

router = APIRouter(prefix="/uploads", tags=["Uploads"])


@router.post(
    "/image",
    response_model=UploadResponse,
    summary="이미지 업로드",
    description="이미지를 사전 업로드하여 URL을 획득합니다. (image/*)",
)
async def upload_image(
    file: UploadFile = File(..., description="이미지 파일 (jpg, jpeg, png, webp)"),
    current_user: User = Depends(get_current_user),
) -> UploadResponse:
    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(status_code=415, detail="지원하지 않는 이미지 형식입니다")
    try:
        url, key = await save_file(file, "images", max_bytes=settings.MAX_IMAGE_UPLOAD_BYTES)
    except FileTooLargeError as exc:
        raise HTTPException(status_code=413, detail="허용된 이미지 파일 크기를 초과했습니다") from exc
    return UploadResponse(url=url, key=key)


@router.post(
    "/audio",
    response_model=UploadResponse,
    summary="오디오 업로드",
    description="오디오 파일을 사전 업로드하여 URL을 획득합니다. (audio/*)",
)
async def upload_audio(
    file: UploadFile = File(..., description="오디오 파일 (m4a, mp3, wav, webm)"),
    current_user: User = Depends(get_current_user),
) -> UploadResponse:
    if not ((file.content_type or "").startswith("audio/") or file.content_type in {"video/webm", "video/mp4"}):
        raise HTTPException(status_code=415, detail="지원하지 않는 오디오 형식입니다")
    try:
        url, key = await save_file(file, "audio", max_bytes=settings.MAX_AUDIO_UPLOAD_BYTES)
    except FileTooLargeError as exc:
        raise HTTPException(status_code=413, detail="허용된 오디오 파일 크기를 초과했습니다") from exc
    return UploadResponse(url=url, key=key)
