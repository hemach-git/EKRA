"""Structured JSON logging with request ids, durations and PII masking."""
from __future__ import annotations

import contextvars
import json
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

from app.core.config import path_for
from app.guardrails.pii import mask_obj

_request_id: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")
_lock = threading.Lock()


def new_request_id() -> str:
    rid = "req-" + uuid.uuid4().hex[:12]
    _request_id.set(rid)
    return rid


def set_request_id(rid: str) -> None:
    _request_id.set(rid)


def current_request_id() -> str:
    return _request_id.get()


def log_event(event: str, **fields) -> None:
    rec = {"ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"), "event": event,
           "request_id": current_request_id(), **mask_obj(fields)}
    line = json.dumps(rec, default=str, ensure_ascii=False)
    try:
        with _lock, open(path_for("log_file"), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass  # logging must never break a request


@contextmanager
def timed(event: str, **fields):
    t0 = time.perf_counter()
    state = {"status": "ok"}
    try:
        yield state
    except Exception as e:  # noqa: BLE001
        state["status"] = "error"
        state["error"] = f"{type(e).__name__}: {e}"
        raise
    finally:
        log_event(event, duration_ms=int((time.perf_counter() - t0) * 1000), **fields, **state)


def read_log(limit: int = 500) -> list[dict]:
    p = path_for("log_file")
    if not p.exists():
        return []
    rows = []
    with open(p, encoding="utf-8") as f:
        lines = f.readlines()[-limit:]
    for ln in lines:
        try:
            rows.append(json.loads(ln))
        except json.JSONDecodeError:
            continue
    return rows
