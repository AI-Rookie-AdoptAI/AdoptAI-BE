from fastapi import APIRouter, Depends, File, UploadFile

from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.upload import UploadResponse
from app.services.storage import save_file

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
    url, key = await save_file(file, "images")
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
    url, key = await save_file(file, "audio")
    return UploadResponse(url=url, key=key)
