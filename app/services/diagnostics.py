"""STUB v0."""
from typing import Optional


def health() -> dict:
    """{"provider": str, "ollama_reachable": bool, "models": {"fast","main","embed"}, "docs": int, "chunks": int, "db_ok": bool}"""
    return {"provider": "stub", "ollama_reachable": False, "models": {}, "docs": 0, "chunks": 0, "db_ok": True}


def recent_requests(limit: int = 50) -> list[dict]:
    """[{"request_id","ts","user_id","status","duration_ms","tokens","provider","steps","error"}]"""
    return []


def latest_eval() -> Optional[dict]:
    """{"timestamp","provider","pass_rate","passed","total","acl_leaks","by_category": {...}, "note": str}"""
    return None


def audit_trail(limit: int = 100) -> list[dict]:
    """[{"ts","request_id","user_id","action","detail"}]"""
    return []
