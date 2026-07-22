"""메일 발송.

SMTP는 블로킹 I/O라서 이벤트 루프에서 직접 호출하지 않고 `asyncio.to_thread`로 넘긴다.
호출부는 BackgroundTasks로 응답 이후에 실행하므로, 여기서 예외를 밖으로 올리지 않고
로그만 남긴다 — 메일 서버 장애가 "재설정 메일을 보냈어요" 응답을 500으로 만들면 안 된다.
"""

import asyncio
import logging
import smtplib
from email.message import EmailMessage

from app.core.config import settings

logger = logging.getLogger(__name__)

PASSWORD_RESET_SUBJECT = "[AdoptAI] 비밀번호 재설정 안내"


def _render_password_reset_body(reset_link: str, expire_minutes: int) -> tuple[str, str]:
    text = (
        "AdoptAI 비밀번호 재설정 안내\n\n"
        "아래 링크에서 새 비밀번호를 설정해 주세요.\n"
        f"{reset_link}\n\n"
        f"이 링크는 {expire_minutes}분 동안만 유효하고, 한 번 사용하면 만료됩니다.\n"
        "본인이 요청한 것이 아니라면 이 메일을 무시하셔도 됩니다."
    )
    html = (
        '<div style="font-family:system-ui,-apple-system,sans-serif;line-height:1.6;color:#2b2320">'
        '<h2 style="margin:0 0 12px">비밀번호 재설정</h2>'
        "<p>아래 버튼을 눌러 새 비밀번호를 설정해 주세요.</p>"
        f'<p><a href="{reset_link}" '
        'style="display:inline-block;padding:12px 20px;border-radius:12px;'
        'background:#b98b5e;color:#fff;text-decoration:none;font-weight:600">'
        "새 비밀번호 설정하기</a></p>"
        f'<p style="font-size:13px;color:#7a6a5d">이 링크는 {expire_minutes}분 동안만 유효하고, '
        "한 번 사용하면 만료됩니다.<br>본인이 요청한 것이 아니라면 이 메일을 무시하셔도 됩니다.</p>"
        "</div>"
    )
    return text, html


def _send_via_smtp(message: EmailMessage) -> None:
    with smtplib.SMTP(
        settings.SMTP_HOST, settings.SMTP_PORT, timeout=settings.SMTP_TIMEOUT_SECONDS
    ) as smtp:
        if settings.SMTP_STARTTLS:
            smtp.starttls()
        if settings.SMTP_USER:
            smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        smtp.send_message(message)


async def send_password_reset_email(*, to_email: str, reset_link: str) -> None:
    expire_minutes = settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES

    if settings.email_backend == "log":
        # 로컬 개발: SMTP 없이도 재설정 플로우를 끝까지 확인할 수 있어야 한다.
        logger.warning("[mail:log] 비밀번호 재설정 링크 (to=%s): %s", to_email, reset_link)
        return

    text, html = _render_password_reset_body(reset_link, expire_minutes)
    message = EmailMessage()
    message["Subject"] = PASSWORD_RESET_SUBJECT
    message["From"] = settings.MAIL_FROM
    message["To"] = to_email
    message.set_content(text)
    message.add_alternative(html, subtype="html")

    try:
        await asyncio.to_thread(_send_via_smtp, message)
    except (smtplib.SMTPException, OSError):
        logger.exception("비밀번호 재설정 메일 발송 실패 (to=%s)", to_email)
