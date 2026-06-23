"""
AI service — integrates with Anthropic Claude (or OpenAI) to process
chat messages, voice transcriptions, and image analysis.

Replace the stub implementations with real API calls as needed.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.core.config import settings
from app.schemas.chat import MessageResponse, MessageType


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _msg(type: MessageType, content: str, metadata: dict | None = None) -> MessageResponse:
    return MessageResponse(
        id=str(uuid.uuid4()),
        role="assistant",
        type=type,
        content=content,
        metadata=metadata,
        created_at=_now(),
    )


async def process_text_message(content: str, history: list[dict]) -> MessageResponse:
    """
    Call LLM with conversation history and return a structured assistant message.

    The assistant should:
    - Extract PetInfo from the user's text
    - Return pet_info_card when enough data is collected
    - Return confirmation_question to clarify missing fields
    - Return text for general conversation

    TODO: integrate with Anthropic/OpenAI using tool_use / structured outputs.
    Example with Anthropic:
        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=history,
            tools=[PET_INFO_TOOL],
        )
    """
    return _msg(
        MessageType.PET_INFO_CARD,
        "들은 내용을 정리했어요. 맞나요?",
        metadata={
            "pet_info": {
                "species": "dog",
                "gender": "unknown",
            },
            "confidence": 0.85,
        },
    )


async def transcribe_and_process(audio_path: str, duration: float, history: list[dict]) -> tuple[str, MessageResponse]:
    """
    Transcribe audio with Whisper (OpenAI) then process through LLM.

    TODO:
        client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        with open(audio_path, "rb") as f:
            transcript = await client.audio.transcriptions.create(model="whisper-1", file=f)
        transcribed_text = transcript.text
        assistant = await process_text_message(transcribed_text, history)
        return transcribed_text, assistant
    """
    transcribed = "음성이 텍스트로 변환되었습니다."
    assistant = _msg(
        MessageType.PET_INFO_CARD,
        "음성에서 들은 내용을 정리했어요.",
        metadata={"pet_info": {}, "confidence": 0.9},
    )
    return transcribed, assistant


async def analyze_image(image_path: str, history: list[dict]) -> MessageResponse:
    """
    Analyze a pet photo using a vision model.

    TODO:
        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        with open(image_path, "rb") as f:
            b64 = base64.standard_b64encode(f.read()).decode()
        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=512,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
                {"type": "text", "text": "이 동물 사진을 분석해주세요."},
            ]}],
        )
    """
    return _msg(MessageType.TEXT, "사진을 확인했어요. 귀여운 친구네요!")


async def process_confirmation(question_id: str, answer: bool | str, history: list[dict]) -> MessageResponse:
    """
    Process a yes/no confirmation and return the next question or a completion message.

    TODO: maintain question state in session and advance through the confirmation flow.
    """
    return _msg(MessageType.TEXT, "확인되었습니다. 다음 질문으로 넘어갈게요.")
