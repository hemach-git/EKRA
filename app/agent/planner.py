"""Plan step: query understanding (window, topic terms, sub-queries). The LLM only PROPOSES sub-queries; if it
fails or returns junk, a rule-based plan is used (mitigates cascading errors)."""
from __future__ import annotations

import json
import re

from pydantic import BaseModel, Field, ValidationError

from app.agent import prompts
from app.agent.budget import BudgetExceeded
from app.agent.context import RunContext
from app.guardrails.input import is_suspicious
from app.llm.base import LLMError

# topic -> trigger words (domain synonym table; in production this is learned from query logs + owner feedback)
SYNONYMS: dict[str, list[str]] = {
    "personalization": ["personalization", "personalisation", "personalized", "personalised", "personalizing"],
    "recommendation": ["recommendation", "recommendations", "recommender", "recommenders", "recsys",
                       "recommendation systems", "recommending"],
    "ranking": ["ranking", "ranker", "rankers"],
    "home feed": ["home feed", "feed ranking"],
    "two-tower retrieval": ["two-tower", "two tower"],
    "next best action": ["next best action", "next-best-action", "nba"],
    "embeddings": ["embedding", "embeddings", "user vectors"],
    "search": ["search ranking", "personalized search"],
    "feature store": ["feature store"],
    "explainability": ["explainability", "explainable"],
    "cold start": ["cold start", "cold-start"],
}


class PlanOut(BaseModel):
    intent: str = "enumeration"
    sub_queries: list[str] = Field(default_factory=list, max_length=8)


def topic_terms(question: str) -> list[str]:
    q = question.lower()
    return [t for t, trig in SYNONYMS.items() if any(re.search(rf"\b{re.escape(x)}\b", q) for x in trig)]


def default_sub_queries(question: str, topics: list[str]) -> list[str]:
    qs = [re.sub(r"\s+", " ", re.sub(r"[^\w\s\-]", " ", question)).strip()[:200]]
    if topics:
        qs.append(" ".join(topics[:4]) + " initiative roadmap")
        qs.append(" ".join(topics[:4]) + " project status report")
        qs.append(" ".join(topics[:4]) + " meeting decision")
    return [q for q in qs if q]


def _intent(question: str) -> str:
    q = question.lower()
    if re.search(r"\b(all|every|which|list|enumerate)\b", q):
        return "enumeration"
    if re.search(r"\b(compare|versus|vs)\b", q):
        return "comparison"
    if re.search(r"\b(timeline|history|when)\b", q):
        return "timeline"
    return "lookup"


def llm_sub_queries(ctx: RunContext, topics: list[str], defaults: list[str]) -> list[str]:
    """Ask the fast model for extra sub-queries; fall back silently to the rule-based ones."""
    payload = {"intent": _intent(ctx.question), "default_sub_queries": defaults}
    try:
        resp = ctx.provider.generate("plan", prompts.PLAN_SYSTEM,
                                     prompts.plan_user(ctx.question, ctx.window.label, topics),
                                     tier="fast", payload=payload, max_tokens=300)
        ctx.budget.charge_llm(resp.prompt_tokens, resp.completion_tokens)
        plan = PlanOut(**json.loads(resp.text))
    except BudgetExceeded:
        raise
    except (LLMError, ValidationError, json.JSONDecodeError, TypeError, ValueError):
        ctx.degrade("llm_plan_fallback")
        return defaults
    merged, seen = [], set()
    for q in [*defaults, *plan.sub_queries]:
        q = q.strip()[:200]
        key = q.lower()
        if q and key not in seen and not is_suspicious(q):
            seen.add(key)
            merged.append(q)
    return merged[:5]
