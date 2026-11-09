"""Permission model. ACLs are stored with each document; every retrieval is filtered by the asking user's identity.

Deny by default: unknown user, no ACL entry, or an ACL that was never synced / is older than acl_max_age_days.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.core import db
from app.core.config import get_config


def _cutoff() -> str:
    days = get_config()["retrieval"]["acl_max_age_days"]
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")


def user_groups(user_id: str) -> set[str]:
    with db.read() as c:
        return {r[0] for r in c.execute("SELECT group_id FROM user_groups WHERE user_id=?", (user_id,))}


def user_exists(user_id: str) -> bool:
    with db.read() as c:
        return c.execute("SELECT 1 FROM users WHERE user_id=?", (user_id,)).fetchone() is not None


def allowed_doc_ids(user_id: str) -> set[str]:
    """All documents this user may open right now (used as the PRE-filter for every search)."""
    with db.read() as c:
        rows = c.execute(
            """SELECT DISTINCT d.doc_id FROM documents d
               JOIN acl_entries a ON a.doc_id = d.doc_id
               JOIN user_groups ug ON ug.group_id = a.group_id AND ug.user_id = ?
               WHERE d.acl_synced_at IS NOT NULL AND d.acl_synced_at >= ?""", (user_id, _cutoff())).fetchall()
    return {r[0] for r in rows}


def can_read(user_id: str, doc_id: str) -> bool:
    """Live re-check (not cached) - used by the verifier right before delivery and by open_document."""
    with db.read() as c:
        row = c.execute(
            """SELECT 1 FROM documents d
               JOIN acl_entries a ON a.doc_id = d.doc_id
               JOIN user_groups ug ON ug.group_id = a.group_id AND ug.user_id = ?
               WHERE d.doc_id = ? AND d.acl_synced_at IS NOT NULL AND d.acl_synced_at >= ? LIMIT 1""",
            (user_id, doc_id, _cutoff())).fetchone()
    return row is not None
