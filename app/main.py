import logging
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.routers import announcements, auth, chat, oauth, shelters, slots, uploads, users

logger = logging.getLogger(__name__)

app = FastAPI(
    title="AdoptAI API",
    description=(
        "AI 기반 반려동물 입양 공고 작성 서비스 API.\n\n"
        "채팅(텍스트/음성/사진)을 통해 입양 공고를 손쉽게 작성할 수 있습니다."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs(settings.LOCAL_UPLOAD_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=settings.LOCAL_UPLOAD_DIR), name="static")


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled API error on %s %s", request.method, request.url.path, exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": "서버 내부 오류가 발생했습니다"})


API_PREFIX = "/api/v1"

app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(oauth.router, prefix=API_PREFIX)
app.include_router(users.router, prefix=API_PREFIX)
app.include_router(shelters.router, prefix=API_PREFIX)
app.include_router(announcements.router, prefix=API_PREFIX)
app.include_router(chat.router, prefix=API_PREFIX)
app.include_router(slots.router, prefix=API_PREFIX)
app.include_router(uploads.router, prefix=API_PREFIX)


@app.get("/", include_in_schema=False)
async def root() -> dict:
    return {"message": "AdoptAI API", "docs": "/docs"}
