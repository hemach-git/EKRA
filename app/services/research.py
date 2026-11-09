"""STUB v0 (canned data). Replaced by the real agent-backed implementation; signatures are the contract."""
from __future__ import annotations

from datetime import date
from typing import Callable, Optional

from app.core.models import (Citation, Claim, Conflict, DocumentView, Finding, PlanStep, Report, ResearchRequest,
                             RunMetrics, RunResult, RunSummary, TimelineEvent, TimeWindow, User)

_USERS = [
    User(user_id="alice", name="Alice Nguyen", role="Product Manager, Growth", groups=["all-employees", "growth"]),
    User(user_id="bob", name="Bob Martins", role="ML Engineer, ML Platform", groups=["all-employees", "ml-platform"]),
    User(user_id="carol", name="Carol Diaz", role="VP Strategy", groups=["all-employees", "exec-confidential"]),
    User(user_id="dave", name="Dave Okafor", role="External Contractor", groups=["contractors"]),
]
_RUNS: dict[str, RunResult] = {}


def list_users() -> list[User]:
    return _USERS


def example_questions() -> list[str]:
    return [
        "Summarize all company initiatives related to personalization and recommendation systems from the last 2 years.",
        "Did we ever try two-tower retrieval for the home feed?",
        "Which personalization initiatives were paused or cancelled, and why?",
        "What is the status of Project Lighthouse?",
    ]


def run_research(req: ResearchRequest, on_event: Optional[Callable[[dict], None]] = None) -> RunResult:
    """on_event receives progress dicts: {"type": "step", "step": PlanStep-as-dict} while the agent runs."""
    cit = Citation(id="c1", doc_id="DOC-001", title="Home Feed Ranking v2 PRD", section="Overview", doc_type="prd",
                   effective_date=date(2025, 1, 20), url="internal://ekra/wiki/DOC-001", chunk_id="DOC-001#0")
    report = Report(
        question=req.question, summary="(stub) Example summary.", time_window=TimeWindow(label="last 2 years"),
        findings=[Finding(initiative="Home Feed Ranking v2", entity_id="ENT-001", aliases=["Project Compass"],
                          owner_team="Growth ML", period="2025-01 to 2025-08", status="paused",
                          claims=[Claim(text="Goal: lift home-feed CTR by 8%.", citations=["c1"])])],
        timeline=[TimelineEvent(date=date(2025, 1, 20), initiative="Home Feed Ranking v2",
                                event="PRD approved.", citations=["c1"])],
        conflicts=[Conflict(initiative="Home Feed Ranking v2", description="(stub)", citations=["c1"])],
        gaps=["(stub) No updates since 2025-09."], citations=[cit])
    res = RunResult(request_id="req-stub", run_id="run-stub", user_id=req.user_id, question=req.question,
                    status="ok", report=report,
                    plan=[PlanStep(step=1, kind="plan", purpose="Resolve window, expand synonyms")],
                    metrics=RunMetrics(latency_ms=1200, steps=1, provider="stub"), created_at="2026-11-09T00:00:00")
    _RUNS[res.run_id] = res
    return res


def get_run(run_id: str) -> Optional[RunResult]:
    return _RUNS.get(run_id)


def list_runs(limit: int = 50, user_id: Optional[str] = None) -> list[RunSummary]:
    return []


def open_document(doc_id: str, user_id: str) -> Optional[DocumentView]:
    """Returns None when the user may not read the document (access attempt is audited)."""
    return None
