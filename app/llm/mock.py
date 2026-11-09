"""Deterministic mock provider for tests/evals/offline demo.

IMPORTANT: the mock's heuristics were written alongside the golden set, so a passing eval run with the mock checks
the pipeline WIRING (retrieval, ACL, verification, schema), not real LLM quality.
"""
from __future__ import annotations

import json
from typing import Optional

from app.llm.base import LLMError, LLMProvider, LLMResponse


class MockProvider(LLMProvider):
    name = "mock"
    embed_name = "hash-256"
    fail_tasks: set[str] = set()      # tests can force failures: MockProvider.fail_tasks = {"extract"}

    def model_for(self, tier: str) -> str:
        return "mock-main" if tier == "main" else "mock-fast"

    def generate(self, task, system, user, *, tier="fast", json_mode=True, payload: Optional[dict] = None,
                 max_tokens=None):
        from app.agent import heuristics

        if task in self.fail_tasks:
            raise LLMError(f"mock forced failure for task={task}")
        payload = payload or {}
        if task == "plan":
            out = {"intent": payload.get("intent", "enumeration"), "sub_queries": payload.get("default_sub_queries", [])}
        elif task == "extract":
            out = {"claims": heuristics.extract_claims(payload["names"], payload["passages"],
                                                       question=payload.get("question", ""))}
        elif task == "summarize":
            out = {"summary": payload["template_summary"]}
        else:
            raise LLMError(f"mock: unknown task {task}")
        text = json.dumps(out)
        return LLMResponse(text=text, prompt_tokens=len(user) // 4, completion_tokens=len(text) // 4,
                           model=self.model_for(tier), latency_ms=1)
