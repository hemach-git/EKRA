"""Pydantic models = the interface contract between services (backend) and the Streamlit UI.

Everything the UI renders comes from these shapes. Do not change field names without telling both sessions.
"""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

Status = Literal["active", "shipped", "paused", "cancelled", "unknown"]
RunStatus = Literal["ok", "partial", "abstained", "blocked", "error"]
DocType = Literal["roadmap", "prd", "report", "meeting", "wiki"]


class User(BaseModel):
    user_id: str
    name: str
    role: str
    groups: list[str]


class ResearchRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    user_id: str
    mode: Literal["quick", "deep"] = "deep"
    source: Literal["app", "eval"] = "app"


class TimeWindow(BaseModel):
    start: Optional[date] = None
    end: Optional[date] = None
    label: str = "all time"


class Citation(BaseModel):
    id: str                      # "c1", "c2", ... stable within one report
    doc_id: str
    title: str
    section: str
    doc_type: DocType
    effective_date: date
    url: str
    chunk_id: str


class Claim(BaseModel):
    text: str
    citations: list[str]         # citation ids
    support: Literal["supported", "partial"] = "supported"
    grounding_score: float = 1.0


class Finding(BaseModel):
    initiative: str
    entity_id: str
    aliases: list[str] = []
    owner_team: str = ""
    period: str = ""
    status: Status = "unknown"
    status_history: list[dict] = []   # [{"status","date","citation"}] oldest -> newest
    claims: list[Claim] = []


class TimelineEvent(BaseModel):
    date: date
    initiative: str
    event: str
    citations: list[str]


class Conflict(BaseModel):
    initiative: str
    description: str
    citations: list[str]


class Report(BaseModel):
    question: str
    summary: str
    time_window: TimeWindow
    findings: list[Finding] = []
    timeline: list[TimelineEvent] = []
    conflicts: list[Conflict] = []
    gaps: list[str] = []
    citations: list[Citation] = []


class PlanStep(BaseModel):
    step: int
    kind: Literal["plan", "act", "observe", "replan", "synthesize", "verify"]
    tool: str = ""
    purpose: str = ""
    args: dict = {}
    status: Literal["ok", "empty", "error", "skipped"] = "ok"
    summary: str = ""
    duration_ms: int = 0


class RunMetrics(BaseModel):
    latency_ms: int = 0
    steps: int = 0
    replans: int = 0
    llm_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    provider: str = ""
    model_fast: str = ""
    model_main: str = ""
    docs_retrieved: int = 0
    docs_cited: int = 0
    claims_total: int = 0
    claims_dropped: int = 0
    degraded: list[str] = []         # e.g. ["llm_plan_fallback"]
    config_snapshot_id: str = ""


class RunResult(BaseModel):
    request_id: str
    run_id: str
    user_id: str
    question: str
    status: RunStatus
    message: str = ""                # human-readable note (why blocked / abstained / partial)
    report: Optional[Report] = None
    plan: list[PlanStep] = []
    metrics: RunMetrics = RunMetrics()
    created_at: str = ""
    is_synthetic_data: bool = True


class RunSummary(BaseModel):
    run_id: str
    request_id: str
    user_id: str
    question: str
    status: RunStatus
    latency_ms: int
    tokens: int
    n_findings: int
    n_citations: int
    created_at: str
    source: str


class DocumentView(BaseModel):
    doc_id: str
    title: str
    doc_type: DocType
    effective_date: date
    owner_team: str
    source_system: str
    url: str
    text: str
    is_synthetic: bool = True


class FeedbackIn(BaseModel):
    run_id: str
    user_id: str
    rating: Literal["up", "down"]
    reason: Optional[Literal["wrong", "outdated", "missing_source", "other"]] = None
    comment: str = Field(default="", max_length=500)
    claim_index: Optional[int] = None

    @field_validator("comment")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()


# ---- internal (backend only) -------------------------------------------------
class ChunkHit(BaseModel):
    chunk_id: str
    doc_id: str
    title: str
    section: str
    doc_type: DocType
    effective_date: date
    text: str
    score: float = 0.0
    url: str = ""
    injection_suspect: bool = False
