import unittest
from datetime import UTC, datetime, timedelta

from app.domain.auth_policy import (
    build_password_reset_link,
    build_placeholder_email,
    can_login_with_password,
    is_password_reset_token_usable,
    is_placeholder_email,
    is_safe_redirect_path,
    is_supported_oauth_provider,
    mask_email,
    resolve_oauth_display_name,
    sanitize_redirect_path,
)

NOW = datetime(2026, 7, 23, 12, 0, tzinfo=UTC)


class PasswordResetTokenTest(unittest.TestCase):
    def test_unused_token_before_expiry_is_usable(self) -> None:
        self.assertTrue(
            is_password_reset_token_usable(
                expires_at=NOW + timedelta(minutes=10), used_at=None, now=NOW
            )
        )

    def test_expired_token_is_not_usable(self) -> None:
        self.assertFalse(
            is_password_reset_token_usable(
                expires_at=NOW - timedelta(seconds=1), used_at=None, now=NOW
            )
        )

    def test_already_used_token_is_not_reusable(self) -> None:
        self.assertFalse(
            is_password_reset_token_usable(
                expires_at=NOW + timedelta(minutes=10),
                used_at=NOW - timedelta(minutes=1),
                now=NOW,
            )
        )

    def test_naive_expiry_from_db_is_treated_as_utc(self) -> None:
        self.assertTrue(
            is_password_reset_token_usable(
                expires_at=datetime(2026, 7, 23, 12, 10), used_at=None, now=NOW
            )
        )


class PasswordLoginTest(unittest.TestCase):
    def test_user_with_password_can_login_with_password(self) -> None:
        self.assertTrue(can_login_with_password("$2b$12$hash"))

    def test_social_only_user_cannot_login_with_password(self) -> None:
        self.assertFalse(can_login_with_password(None))
        self.assertFalse(can_login_with_password(""))


class OAuthProviderTest(unittest.TestCase):
    def test_supported_providers(self) -> None:
        self.assertTrue(is_supported_oauth_provider("google"))
        self.assertTrue(is_supported_oauth_provider("kakao"))

    def test_unknown_provider_is_rejected(self) -> None:
        self.assertFalse(is_supported_oauth_provider("naver"))

    def test_profile_name_is_used_when_present(self) -> None:
        self.assertEqual(resolve_oauth_display_name(" 홍길동 ", "a@b.com"), "홍길동")

    def test_email_local_part_is_used_when_provider_hides_name(self) -> None:
        self.assertEqual(resolve_oauth_display_name(None, "shelter@example.com"), "shelter")

    def test_falls_back_when_provider_gives_neither(self) -> None:
        self.assertEqual(resolve_oauth_display_name("  ", None), "이름 없음")

    def test_placeholder_email_is_stable_per_provider_account(self) -> None:
        first = build_placeholder_email("kakao", "12345")
        self.assertEqual(first, build_placeholder_email("kakao", "12345"))
        self.assertNotEqual(first, build_placeholder_email("google", "12345"))

    def test_placeholder_email_is_recognizable(self) -> None:
        self.assertTrue(is_placeholder_email(build_placeholder_email("kakao", "12345")))
        self.assertFalse(is_placeholder_email("shelter@example.com"))


class RedirectPathTest(unittest.TestCase):
    def test_internal_path_is_safe(self) -> None:
        self.assertTrue(is_safe_redirect_path("/announcements"))

    def test_protocol_relative_url_is_rejected(self) -> None:
        self.assertFalse(is_safe_redirect_path("//evil.example.com"))

    def test_absolute_url_is_rejected(self) -> None:
        self.assertFalse(is_safe_redirect_path("https://evil.example.com"))

    def test_unsafe_path_falls_back_to_root(self) -> None:
        self.assertEqual(sanitize_redirect_path("https://evil.example.com"), "/")
        self.assertEqual(sanitize_redirect_path(None), "/")
        self.assertEqual(sanitize_redirect_path("/chat"), "/chat")


class ResetLinkTest(unittest.TestCase):
    def test_link_does_not_duplicate_slash(self) -> None:
        self.assertEqual(
            build_password_reset_link("http://localhost:3000/", "abc"),
            "http://localhost:3000/reset-password?token=abc",
        )

    def test_email_is_masked_but_domain_stays_visible(self) -> None:
        self.assertEqual(mask_email("shelter@example.com"), "sh*****@example.com")

    def test_short_local_part_still_masked(self) -> None:
        self.assertEqual(mask_email("ab@example.com"), "ab*@example.com")


if __name__ == "__main__":
    unittest.main()
