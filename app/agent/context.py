"""Per-run state shared by the agent and the tools (working memory: discarded when the run ends)."""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Callable, Optional

from app.agent.budget import Budget
from app.core.models import ChunkHit, PlanStep, TimeWindow
from app.llm.base import LLMProvider


@dataclass
class RunContext:
    request_id: str
    user_id: str
    question: str
    mode: str
    provider: LLMProvider
    budget: Budget
    window: TimeWindow = field(default_factory=TimeWindow)
    allowed: set = field(default_factory=set)             # ACL pre-filter for this user
    retrieved_docs: set = field(default_factory=set)      # audit: every doc surfaced to the agent
    degraded: list = field(default_factory=list)
    steps: list = field(default_factory=list)
    ledger: dict = field(default_factory=dict)            # chunk_id -> ChunkHit (evidence ledger)
    injection_docs: set = field(default_factory=set)
    on_event: Optional[Callable[[dict], None]] = None
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def add_step(self, **kw) -> PlanStep:
        with self._lock:
            step = PlanStep(step=len(self.steps) + 1, **kw)
            self.steps.append(step)
        if self.on_event:
            try:
                self.on_event({"type": "step", "step": step.model_dump(mode="json")})
            except Exception:  # noqa: BLE001  (a UI callback must never break the run)
                pass
        return step

    def note(self, hit: ChunkHit) -> None:
        with self._lock:
            self.ledger.setdefault(hit.chunk_id, hit)
            self.retrieved_docs.add(hit.doc_id)
            if hit.injection_suspect:
                self.injection_docs.add(hit.doc_id)

    def degrade(self, flag: str) -> None:
        with self._lock:
            if flag not in self.degraded:
                self.degraded.append(flag)
