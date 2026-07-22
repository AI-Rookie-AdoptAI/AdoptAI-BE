"""Chat workflow policies shared by API handlers and tests."""

DRAFT_READY_STAGES = frozenset({"draft_ready", "editing"})


def can_generate_platform_drafts(stage: str, *, has_draft: bool) -> bool:
    """Platform variants are allowed only after a persisted base draft exists."""
    return has_draft and stage in DRAFT_READY_STAGES
