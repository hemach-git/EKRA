"""STUB v0."""
from app.core.models import FeedbackIn


def submit_feedback(fb: FeedbackIn) -> dict:
    return {"ok": True, "feedback_id": "fb-stub"}


def list_feedback(limit: int = 100) -> list[dict]:
    return []
