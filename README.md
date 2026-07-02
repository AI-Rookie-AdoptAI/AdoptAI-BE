# AdoptAI — Backend

AI 기반 반려동물 입양 공고 자동 작성 서비스의 FastAPI 백엔드입니다.

---

## 기술 스택

| 분류 | 사용 기술 |
|------|-----------|
| 언어 | Python 3.11+ |
| 웹 프레임워크 | FastAPI 0.115 |
| ASGI 서버 | Uvicorn |
| ORM | SQLAlchemy 2.0 (async) |
| DB 드라이버 | asyncpg |
| DB | PostgreSQL 16 |
| 마이그레이션 | Alembic |
| 인증 | JWT (python-jose) + bcrypt (passlib) |
| AI | Anthropic Claude (채팅·이미지 분석) |
| STT | OpenAI Whisper |
| 설정 관리 | pydantic-settings |

---

## 프로젝트 구조

```
be/
├── app/
│   ├── main.py                  # FastAPI 앱 + 라우터 등록
│   ├── dependencies.py          # 공통 Depends (get_current_user)
│   ├── core/
│   │   ├── config.py            # 환경변수 (.env) 로딩
│   │   ├── database.py          # async engine / 세션 팩토리 / Base
│   │   └── security.py          # JWT 발급·검증, 비밀번호 해시
│   ├── models/                  # SQLAlchemy ORM 모델
│   │   ├── user.py
│   │   ├── refresh_token.py
│   │   ├── announcement.py
│   │   ├── chat.py              # ChatSession, Message
│   │   ├── shelter.py
│   │   └── notification_setting.py
│   ├── schemas/                 # Pydantic 요청/응답 스키마
│   │   ├── auth.py
│   │   ├── user.py
│   │   ├── chat.py              # ApiMessage, ApiDraft, Stage, …
│   │   ├── slots.py             # ApiSlots (슬롯 스키마)
│   │   ├── announcement.py
│   │   ├── shelter.py
│   │   └── upload.py
│   ├── routers/                 # 엔드포인트
│   │   ├── auth.py              # /auth/*
│   │   ├── users.py             # /users/me, /users/me/notification-settings
│   │   ├── shelters.py          # /shelters/me
│   │   ├── chat.py              # /chat/sessions/*
│   │   ├── slots.py             # /slots/*
│   │   ├── announcements.py     # /announcements/*
│   │   └── uploads.py           # /uploads/*
│   └── services/
│       ├── ai.py                # Claude 연동 (stub → TODO)
│       ├── stt.py               # Whisper STT (stub → TODO)
│       └── storage.py           # 파일 저장 (로컬 → S3 TODO)
├── alembic/                     # DB 마이그레이션
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
├── alembic.ini
├── create_tables.py             # 개발용 테이블 즉시 생성
├── seed_user.py                 # 개발용 테스트 유저 생성
├── requirements.txt
└── .env.example
```

---

## 로컬 실행

### 1. 환경변수 설정

```bash
cp .env.example .env
# .env 열어서 DATABASE_URL, ANTHROPIC_API_KEY 등 입력
```

### 2. 의존성 설치

```bash
pip install -r requirements.txt
```

### 3. DB 실행 (Docker)

PostgreSQL만 컨테이너로 올립니다.

```bash
docker compose up -d db
```

> Docker 없이 로컬 PostgreSQL을 사용한다면 이 단계를 건너뛰고 `.env`의 `DATABASE_URL`을 맞게 수정하세요.

### 4. DB 테이블 생성

```bash
# 방법 A — 스크립트 (개발 초기 권장)
python create_tables.py

# 방법 B — Alembic 마이그레이션
alembic upgrade head
```

### 5. (선택) 테스트 유저 생성

```bash
python seed_user.py
# email: test@example.com / password: password123
```

### 6. 서버 실행

```bash
uvicorn app.main:app --reload --port 8000
```

---

## Swagger / API 문서

서버 실행 후 브라우저에서 접속:

| 주소 | 설명 |
|------|------|
| http://localhost:8000/docs | Swagger UI (인터랙티브 테스트 가능) |
| http://localhost:8000/redoc | ReDoc (읽기 전용 문서) |
| http://localhost:8000/openapi.json | OpenAPI 스펙 JSON |

---

## 주요 엔드포인트 요약

Base URL: `http://localhost:8000/api/v1`

```
# 인증
POST   /auth/register
POST   /auth/login
POST   /auth/refresh
POST   /auth/logout

# 사용자 / 보호소
GET    /users/me
PATCH  /users/me
GET    /users/me/notification-settings
PATCH  /users/me/notification-settings
GET    /shelters/me
PATCH  /shelters/me

# 채팅 (입양 공고 작성)
POST   /chat/sessions
GET    /chat/sessions/{id}/messages
POST   /chat/sessions/{id}/messages      # text, quick_reply
POST   /chat/sessions/{id}/images        # 사진 1~10장
POST   /chat/sessions/{id}/voice         # 음성 메모
POST   /chat/sessions/{id}/publish       # 공고 게시

# 슬롯 스키마
GET    /slots/schema
GET    /slots/meta
POST   /slots/validate
GET    /slots/example

# 공고 관리
GET    /announcements
POST   /announcements
GET    /announcements/{id}
PATCH  /announcements/{id}
POST   /announcements/{id}/publish

# 파일 업로드
POST   /uploads/image
POST   /uploads/audio
```

---

## Docker Compose

개발 환경에서는 **PostgreSQL만** 컨테이너로 실행하고, 앱 서버는 로컬에서 `--reload`로 띄우는 구성입니다.

```bash
# DB만 실행
docker compose up -d db

# 전체 실행 (앱 포함)
docker compose up
```

`docker-compose.yml` 참고:
- **db**: PostgreSQL 16, 포트 `5432`
- **api**: FastAPI 앱, 포트 `8000` (전체 실행 시)
