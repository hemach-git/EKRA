"""Human review: users rate a report / flag a claim. Recorded in the feedback table AND the audit trail."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.core import db
from app.core.logging import log_event, new_request_id
from app.core.models import FeedbackIn
from app.guardrails.pii import mask_text
from app.retrieval import acl
from app.services.research import audit


def submit_feedback(fb: FeedbackIn) -> dict:
    rid = new_request_id()
    if not acl.user_exists(fb.user_id):
        return {"ok": False, "error": "unknown user"}
    with db.read() as c:
        run = c.execute("SELECT user_id FROM research_runs WHERE run_id=?", (fb.run_id,)).fetchone()
    if run is None:
        return {"ok": False, "error": "unknown run"}
    fid = "fb-" + uuid.uuid4().hex[:10]
    comment = mask_text(fb.comment)
    with db.tx() as c:
        c.execute("INSERT INTO feedback VALUES (?,?,?,?,?,?,?,?)",
                  (fid, fb.run_id, fb.user_id, fb.rating, fb.reason, comment, fb.claim_index,
                   datetime.now(timezone.utc).isoformat(timespec="seconds")))
    audit(rid, fb.user_id, "feedback", {"feedback_id": fid, "run_id": fb.run_id, "rating": fb.rating,
                                        "reason": fb.reason, "claim_index": fb.claim_index})
    log_event("feedback", feedback_id=fid, run_id=fb.run_id, rating=fb.rating, reason=fb.reason)
    return {"ok": True, "feedback_id": fid}


def list_feedback(limit: int = 100) -> list[dict]:
    with db.read() as c:
        rows = c.execute("SELECT * FROM feedback ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]
