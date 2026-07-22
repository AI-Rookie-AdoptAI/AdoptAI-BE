import unittest

from app.domain.chat_workflow import can_generate_platform_drafts


class ChatWorkflowTest(unittest.TestCase):
    def test_draft_ready_session_can_generate_platform_drafts(self) -> None:
        self.assertTrue(can_generate_platform_drafts("draft_ready", has_draft=True))

    def test_editing_session_can_generate_platform_drafts(self) -> None:
        self.assertTrue(can_generate_platform_drafts("editing", has_draft=True))

    def test_session_without_persisted_draft_cannot_generate_variants(self) -> None:
        self.assertFalse(can_generate_platform_drafts("draft_ready", has_draft=False))

    def test_clarifying_session_cannot_generate_variants(self) -> None:
        self.assertFalse(can_generate_platform_drafts("clarifying", has_draft=True))


if __name__ == "__main__":
    unittest.main()
