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
| STT | 별도 faster-whisper 서비스 (`../STT`) |
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
│       ├── ai.py                # STT 공고·Vision 결과를 채팅 응답으로 변환
│       ├── vision.py            # 대표사진 선택 (../VISION CLIP L/14 + student MLP + SVR 앙상블)
│       ├── stt.py               # 내부 STT/pipeline 서비스 클라이언트
│       └── storage.py           # 스트리밍 파일 저장 (S3 또는 /static 영속 볼륨)
├── alembic/                     # DB 마이그레이션
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
├── alembic.ini
├── bootstrap_database.py        # 부팅 시 Alembic 마이그레이션 적용 (스키마의 유일한 소유자)
├── seed_user.py                 # 개발용 테스트 유저 생성
├── requirements.txt
└── .env.example
```

---

## 로컬 실행

### 1. 환경변수 설정

```bash
cp .env.example .env
# .env 열어서 DATABASE_URL, SECRET_KEY 등을 입력
```

> 대표사진 선택은 `VISION_BASE_URL`의 Vision 서비스에 요청합니다. 서비스가 응답하지 않으면
> 안전하게 첫 번째 사진(confidence 0)을 사용합니다. Docker Compose의 `full` 프로필은
> `../VISION` 이미지를 함께 실행합니다.

> 음성 흐름은 `FE → BE → STT`입니다. Docker Compose에서는 `STT_BASE_URL=http://stt:8000`,
> 각 서버를 직접 실행할 때는 `http://localhost:8001`로 설정하세요. 운영 환경에서는
> BE와 STT에 동일한 `STT_INTERNAL_API_KEY`를 설정해야 합니다.
> Compose의 STT 세션은 Redis AOF 볼륨에 저장되어 재시작과 다중 워커에서도 유지됩니다.

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

스키마는 Alembic만이 소유한다. 모델을 바꿨다면 같은 PR에 마이그레이션을 함께 넣는다.

```bash
alembic upgrade head

# 새 마이그레이션 만들기 (생성된 diff는 반드시 읽고 손볼 것)
alembic revision --autogenerate -m "add something"
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

STT까지 함께 컨테이너로 실행하려면 다음 명령을 사용합니다.

```bash
docker compose --profile full up --build
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
POST   /chat/sessions/{id}/messages          # text, quick_reply
POST   /chat/sessions/{id}/messages/stream   # SSE 스트리밍
POST   /chat/sessions/{id}/images            # 사진 1~10장
POST   /chat/sessions/{id}/voice             # 음성 메모
POST   /chat/sessions/{id}/platform-drafts   # 플랫폼별 공고 생성
POST   /chat/sessions/{id}/publish           # 자동 게시 미연결(501, 직접 등록 안내)

# 슬롯 스키마
GET    /slots/schema
GET    /slots/meta
POST   /slots/validate
GET    /slots/example

# 공고 관리
GET    /announcements
GET    /announcements/{id}
PATCH  /announcements/{id}
POST   /announcements/{id}/duplicate
DELETE /announcements/{id}

# 파일 업로드
POST   /uploads/image
POST   /uploads/audio
```

업로드는 S3 호환 자격증명이 있으면 Supabase Storage로, 없으면
`LOCAL_UPLOAD_DIR`로 스트리밍 저장됩니다. 로컬 파일은 `/static`으로 제공합니다.

---

## Docker Compose

개발 환경에서는 **PostgreSQL만** 컨테이너로 실행하고, 앱 서버는 로컬에서 `--reload`로 띄우는 구성입니다.

```bash
# DB만 실행 (기본)
docker compose up -d db

# 전체 실행 (앱 포함) — api 서비스는 profile "full" 에 속함
docker compose --profile full up
```

`docker-compose.yml` 참고:
- **db**: PostgreSQL 16, 포트 `5432`
- **api**: FastAPI 앱, 포트 `8000` (`--profile full` 로 실행 시)
- **stt / vision / redis**: 음성 파이프라인, 대표사진 추론, STT 세션 저장 (`full` 프로필)
