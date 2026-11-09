"""Research service = the contract the UI calls. Orchestrates guardrails -> agent -> persistence -> audit."""
from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from typing import Callable, Optional

from app.agent.budget import Budget
from app.agent.context import RunContext
from app.agent.loop import run_agent
from app.core import db
from app.core.config import config_snapshot, get_config
from app.core.logging import log_event, new_request_id
from app.core.models import (DocumentView, PlanStep, ResearchRequest, RunMetrics, RunResult, RunSummary, User)
from app.data.seed import ensure_seeded
from app.guardrails.input import check_input
from app.guardrails.pii import mask_text
from app.llm import get_provider
from app.retrieval import acl

_EXAMPLES = [
    "Summarize all company initiatives related to personalization and recommendation systems from the last 2 years.",
    "Did we ever try two-tower retrieval for the home feed?",
    "Which personalization initiatives were paused or cancelled, and why?",
    "What is the status of Project Lighthouse?",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def audit(request_id: str, user_id: str, action: str, detail: dict, model: str = "") -> None:
    with db.tx() as c:
        c.execute("INSERT INTO audit_log (ts, request_id, user_id, action, detail_json, model) VALUES (?,?,?,?,?,?)",
                  (_now(), request_id, user_id, action, mask_text(json.dumps(detail, default=str)), model))


def list_users() -> list[User]:
    ensure_seeded()
    with db.read() as c:
        rows = c.execute("SELECT user_id, name, role FROM users ORDER BY user_id").fetchall()
        groups: dict[str, list[str]] = {}
        for r in c.execute("SELECT user_id, group_id FROM user_groups ORDER BY group_id"):
            groups.setdefault(r[0], []).append(r[1])
    return [User(user_id=r["user_id"], name=r["name"], role=r["role"], groups=groups.get(r["user_id"], []))
            for r in rows]


def example_questions() -> list[str]:
    return list(_EXAMPLES)


def run_research(req: ResearchRequest, on_event: Optional[Callable[[dict], None]] = None) -> RunResult:
    ensure_seeded()
    t0 = time.perf_counter()
    rid = new_request_id()
    run_id = "run-" + uuid.uuid4().hex[:10]
    cfg = get_config()
    snap_id, snap_cfg = config_snapshot()
    provider = get_provider()
    models = {"fast": provider.model_for("fast"), "main": provider.model_for("main")}
    ctx: Optional[RunContext] = None

    def finish(status, message="", report=None, steps=None, agent=None) -> RunResult:
        m = RunMetrics(latency_ms=int((time.perf_counter() - t0) * 1000), steps=len(steps or []),
                       replans=ctx.budget.replans if ctx else 0, llm_calls=ctx.budget.llm_calls if ctx else 0,
                       prompt_tokens=ctx.budget.prompt_tokens if ctx else 0,
                       completion_tokens=ctx.budget.completion_tokens if ctx else 0, provider=provider.name,
                       model_fast=models["fast"], model_main=models["main"],
                       docs_retrieved=len(ctx.retrieved_docs) if ctx else 0,
                       docs_cited=agent.docs_cited if agent else 0, claims_total=agent.claims_total if agent else 0,
                       claims_dropped=agent.claims_dropped if agent else 0, degraded=list(ctx.degraded) if ctx else [],
                       config_snapshot_id=snap_id)
        res = RunResult(request_id=rid, run_id=run_id, user_id=req.user_id, question=req.question, status=status,
                        message=message, report=report, plan=steps or [], metrics=m, created_at=_now())
        _persist(res, req.source, snap_id, snap_cfg)
        audit(rid, req.user_id, "research_run", {
            "run_id": run_id, "status": status, "question": req.question[:200], "source": req.source,
            "docs_retrieved": sorted(ctx.retrieved_docs) if ctx else [],
            "docs_cited": sorted({c.doc_id for c in report.citations}) if report else [],
            "injection_docs": sorted(ctx.injection_docs) if ctx else [], "degraded": m.degraded}, models["main"])
        log_event("research_run", run_id=run_id, user_id=req.user_id, status=status, duration_ms=m.latency_ms,
                  tokens=m.prompt_tokens + m.completion_tokens, provider=provider.name, steps=m.steps,
                  replans=m.replans, docs_cited=m.docs_cited, claims_dropped=m.claims_dropped,
                  degraded=m.degraded, question=req.question[:200])
        return res

    # ---- unknown user: fail closed (no identity -> no documents)
    if not acl.user_exists(req.user_id):
        audit(rid, req.user_id, "blocked_unknown_user", {"question": req.question[:200]})
        log_event("research_run", status="blocked", user_id=req.user_id, error="unknown_user")
        return RunResult(request_id=rid, run_id=run_id, user_id=req.user_id, question=req.question, status="blocked",
                         message="Unknown user. Sign in as one of the demo users.", created_at=_now(),
                         metrics=RunMetrics(provider=provider.name, config_snapshot_id=snap_id))

    # ---- input guardrails
    g = check_input(req.question)
    if not g.ok:
        ctx = None
        audit(rid, req.user_id, "blocked_input", {"code": g.code, "question": req.question[:200]})
        return finish("blocked", g.reason)

    try:
        ctx = RunContext(request_id=rid, user_id=req.user_id, question=g.sanitized, mode=req.mode, provider=provider,
                         budget=Budget(req.mode), allowed=acl.allowed_doc_ids(req.user_id), on_event=on_event)
        log_event("run_start", run_id=run_id, user_id=req.user_id, mode=req.mode, allowed_docs=len(ctx.allowed))
        result = run_agent(ctx)
        return finish(result.status, result.message, result.report, ctx.steps, result)
    except Exception as e:  # noqa: BLE001  never leak a stack trace to the UI; log it, audit it, return a clean error
        log_event("research_error", run_id=run_id, error=f"{type(e).__name__}: {e}")
        return finish("error", "Something went wrong while researching. The error was logged; please try again.",
                      steps=ctx.steps if ctx else [])


def _persist(res: RunResult, source: str, snap_id: str, snap_cfg: dict) -> None:
    rep = res.report
    with db.tx() as c:
        c.execute("INSERT OR IGNORE INTO config_snapshots VALUES (?,?,?)",
                  (snap_id, json.dumps(snap_cfg, default=str), _now()))
        c.execute(
            """INSERT INTO research_runs (run_id, request_id, user_id, question, status, message, source, plan_json,
               report_json, metrics_json, snapshot_id, latency_ms, tokens, n_findings, n_citations, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (res.run_id, res.request_id, res.user_id, mask_text(res.question), res.status, res.message, source,
             json.dumps([s.model_dump(mode="json") for s in res.plan]),
             rep.model_dump_json() if rep else None, res.metrics.model_dump_json(), snap_id, res.metrics.latency_ms,
             res.metrics.prompt_tokens + res.metrics.completion_tokens, len(rep.findings) if rep else 0,
             len(rep.citations) if rep else 0, res.created_at))
        for s in res.plan:
            c.execute("INSERT INTO run_steps (run_id, step_no, kind, tool, status, duration_ms, summary) "
                      "VALUES (?,?,?,?,?,?,?)", (res.run_id, s.step, s.kind, s.tool, s.status, s.duration_ms, s.summary))
        if rep:
            for ct in rep.citations:
                c.execute("INSERT INTO run_citations VALUES (?,?,?,?)", (res.run_id, ct.id, ct.doc_id, ct.chunk_id))


def _row_to_result(r) -> RunResult:
    from app.core.models import Report
    return RunResult(
        request_id=r["request_id"], run_id=r["run_id"], user_id=r["user_id"], question=r["question"],
        status=r["status"], message=r["message"], created_at=r["created_at"],
        report=Report.model_validate_json(r["report_json"]) if r["report_json"] else None,
        plan=[PlanStep(**s) for s in json.loads(r["plan_json"])], metrics=RunMetrics.model_validate_json(r["metrics_json"]))


def get_run(run_id: str) -> Optional[RunResult]:
    with db.read() as c:
        r = c.execute("SELECT * FROM research_runs WHERE run_id=?", (run_id,)).fetchone()
    return _row_to_result(r) if r else None


def list_runs(limit: int = 50, user_id: Optional[str] = None) -> list[RunSummary]:
    q = "SELECT * FROM research_runs" + (" WHERE user_id=?" if user_id else "") + " ORDER BY created_at DESC LIMIT ?"
    args = ([user_id] if user_id else []) + [limit]
    with db.read() as c:
        rows = c.execute(q, args).fetchall()
    return [RunSummary(run_id=r["run_id"], request_id=r["request_id"], user_id=r["user_id"], question=r["question"],
                       status=r["status"], latency_ms=r["latency_ms"], tokens=r["tokens"],
                       n_findings=r["n_findings"], n_citations=r["n_citations"], created_at=r["created_at"],
                       source=r["source"]) for r in rows]


def open_document(doc_id: str, user_id: str) -> Optional[DocumentView]:
    """Open a cited document. The ACL is re-checked live; refusals are audited and look the same as 'not found'."""
    rid = new_request_id()
    if not acl.can_read(user_id, doc_id):
        audit(rid, user_id, "document_access_denied", {"doc_id": doc_id})
        return None
    with db.read() as c:
        d = c.execute("SELECT * FROM documents WHERE doc_id=?", (doc_id,)).fetchone()
    if not d:
        return None
    audit(rid, user_id, "document_opened", {"doc_id": doc_id})
    return DocumentView(doc_id=d["doc_id"], title=d["title"], doc_type=d["doc_type"],
                        effective_date=d["effective_date"], owner_team=d["owner_team"], source_system=d["source_system"],
                        url=d["url"], text=d["text"], is_synthetic=bool(d["is_synthetic"]))
