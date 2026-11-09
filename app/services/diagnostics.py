"""Operational view: health, recent requests (from the structured JSON log), latest eval, audit trail."""
from __future__ import annotations

import json
from typing import Optional

from app.core import db
from app.core.config import get_config, path_for
from app.core.logging import read_log
from app.llm import get_provider


def health() -> dict:
    cfg = get_config()["llm"]
    out = {"provider": cfg["provider"], "ollama_reachable": False, "db_ok": False, "docs": 0, "chunks": 0,
           "models": {"fast": cfg["models"]["fast"], "main": cfg["models"]["main"], "embed": cfg["embed_model"]},
           "synthetic_data": True}
    try:
        out["ollama_reachable"] = get_provider("ollama").available()
    except Exception:  # noqa: BLE001
        pass
    try:
        with db.read() as c:
            out["docs"] = c.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
            out["chunks"] = c.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
            out["db_ok"] = c.execute("PRAGMA foreign_key_check").fetchall() == []
    except Exception:  # noqa: BLE001
        pass
    return out


def recent_requests(limit: int = 50) -> list[dict]:
    rows = [r for r in read_log(5000) if r.get("event") == "research_run"]
    rows.sort(key=lambda r: r["ts"], reverse=True)
    return [{"request_id": r.get("request_id"), "ts": r["ts"], "user_id": r.get("user_id"), "status": r.get("status"),
             "duration_ms": r.get("duration_ms"), "tokens": r.get("tokens"), "provider": r.get("provider"),
             "steps": r.get("steps"), "error": r.get("error", "")} for r in rows[:limit]]


def latest_eval() -> Optional[dict]:
    d = path_for("eval_results")
    files = sorted(d.glob("eval_*.json"))
    if not files:
        return None
    data = json.loads(files[-1].read_text(encoding="utf-8"))
    return data.get("summary")


def audit_trail(limit: int = 100) -> list[dict]:
    with db.read() as c:
        rows = c.execute("SELECT ts, request_id, user_id, action, detail_json, model FROM audit_log "
                         "ORDER BY audit_id DESC LIMIT ?", (limit,)).fetchall()
    return [{"ts": r["ts"], "request_id": r["request_id"], "user_id": r["user_id"], "action": r["action"],
             "detail": json.loads(r["detail_json"]), "model": r["model"]} for r in rows]
