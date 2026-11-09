"""Synthesis = MAP (per-initiative claim extraction by the fast LLM) + REDUCE (deterministic status, timeline,
conflicts; LLM-written summary that is number-checked). Statuses are rules-based so they are auditable."""
from __future__ import annotations

import json
import re
from collections import defaultdict
from functools import lru_cache
from typing import Optional

from pydantic import BaseModel, Field, ValidationError

from app.agent import heuristics, prompts
from app.agent.budget import BudgetExceeded
from app.agent.context import RunContext
from app.core.config import get_config
from app.core.models import ChunkHit, TimeWindow
from app.llm.base import LLMError
from app.retrieval.index import SearchIndex


@lru_cache(maxsize=1)
def alias_map() -> dict[str, tuple]:
    from app.core import db
    out: dict[str, list] = {}
    with db.read() as c:
        for r in c.execute("SELECT entity_id, alias FROM entity_aliases"):
            out.setdefault(r[0], []).append(r[1])
    return {k: tuple(v) for k, v in out.items()}


def other_aliases(index: SearchIndex, eid: str, chunk_id: str) -> list[str]:
    am = alias_map()
    return [a for e in index.entities_of_chunk(chunk_id) if e != eid for a in am.get(e, ())]


# ------------------------------------------------------------------ evidence selection
def select_evidence(index: SearchIndex, ctx: RunContext, eid: str, universe: list[dict], cap: int,
                    names: Optional[list[str]] = None) -> list[ChunkHit]:
    """Pick <= cap passages. Priority: (1) earliest + two most recent documents (status history needs both ends),
    (1b) the 2 passages that best match the question,
    (2) every passage that carries a status signal for this initiative (so the status history is complete),
    (3) the rest by relevance score, one passage per document before a second from the same one."""
    cands = [h for h in ctx.ledger.values() if eid in index.entities_of_chunk(h.chunk_id)]

    def has_status(h: ChunkHit) -> bool:
        if not names:
            return False
        p = {"text": h.text, "single_entity": len(index.entities_of_chunk(h.chunk_id)) == 1,
             "other_aliases": other_aliases(index, eid, h.chunk_id)}
        return bool(heuristics.status_observations(names, [{**p, "cid": "x", "date": "0"}]))

    flag = {h.chunk_id: has_status(h) for h in cands}
    by_doc: dict[str, list[ChunkHit]] = defaultdict(list)
    for h in cands:
        by_doc[h.doc_id].append(h)
    for hs in by_doc.values():
        hs.sort(key=lambda h: (not flag[h.chunk_id], -h.score, h.chunk_id))
    chosen: list[ChunkHit] = []

    def add(h: ChunkHit) -> None:
        if h not in chosen and len(chosen) < cap:
            chosen.append(h)

    for doc_id in dict.fromkeys(d["doc_id"] for d in (universe[:1] + universe[-2:])):
        for h in by_doc.get(doc_id, [])[:1]:
            add(h)
    qrel = sorted(cands, key=lambda h: (-index.bm25_for(ctx.question, h.chunk_id), h.chunk_id))[:2]
    for h in qrel:                                              # the passages that best match the actual question
        if index.bm25_for(ctx.question, h.chunk_id) > 0:
            add(h)
    for h in sorted((h for h in cands if flag[h.chunk_id]), key=lambda h: (h.effective_date, h.chunk_id)):
        add(h)
    used = {h.doc_id for h in chosen}
    for h in sorted((hs[0] for d, hs in by_doc.items() if d not in used), key=lambda h: (-h.score, h.chunk_id)):
        add(h)
    for hs in by_doc.values():
        for h in hs[1:]:
            add(h)
    return sorted(chosen, key=lambda h: (h.effective_date, h.chunk_id))


def coverage_gaps(index: SearchIndex, ctx: RunContext, eid: str, universe: list[dict]) -> list[str]:
    """Documents to read next, in priority order: the earliest and two most recent first, then the rest newest-first,
    up to cap+4 documents per initiative. A document counts as covered only when EVERY passage of it that mentions
    this initiative is in the ledger (search can return one passage of a document and miss the one that carries
    the status change), so coverage is checked per passage, not assumed per document."""
    cap = get_config()["agent"]["max_evidence_per_entity"]
    ordered = [d["doc_id"] for d in (universe[:1] + universe[-2:])] + [d["doc_id"] for d in reversed(universe)]
    ordered = list(dict.fromkeys(ordered))[: cap + 4]
    need: dict[str, set] = {d: set() for d in ordered}
    for r in index.recs:
        if r["doc_id"] in need and eid in r["entities"]:
            need[r["doc_id"]].add(r["chunk_id"])
    return [d for d in ordered if need[d] - set(ctx.ledger)]


# ------------------------------------------------------------------ MAP: claim extraction
class ClaimOut(BaseModel):
    text: str = Field(min_length=8, max_length=400)
    citations: list[str] = Field(min_length=1)


class ExtractOut(BaseModel):
    claims: list[ClaimOut] = Field(default_factory=list, max_length=12)


def extract_entity(ctx: RunContext, entity: dict, passages: list[dict]) -> list[dict]:
    """Returns [{"text", "chunks": [chunk_id]}]. LLM first (validated, 1 retry); rules-based fallback on failure."""
    names = [entity["name"], *entity["aliases"]]
    local = {p["cid"]: p["chunk_id"] for p in passages}
    payload = {"names": names, "passages": passages, "question": ctx.question}
    system = prompts.EXTRACT_SYSTEM
    user = prompts.extract_user(entity["name"], entity["aliases"], passages, ctx.question)
    for attempt in range(0 if ctx.budget.exhausted() else 2):      # budget gone -> rules-based, no LLM spend
        try:
            resp = ctx.provider.generate("extract", system, user, tier="fast", payload=payload)
            ctx.budget.charge_llm(resp.prompt_tokens, resp.completion_tokens)
            out = ExtractOut(**json.loads(resp.text))
            claims = []
            for c in out.claims:
                ids = [local[i] for i in re.findall(r"s\d+", " ".join(c.citations)) if i in local]
                if ids:
                    claims.append({"text": c.text.strip(), "chunks": list(dict.fromkeys(ids))})
            if claims:
                return claims
            raise ValueError("no valid claims with valid citations")
        except BudgetExceeded:
            ctx.degrade("budget_stop_rules_extraction")
            break
        except (LLMError, ValidationError, json.JSONDecodeError, TypeError, ValueError):
            user += "\nReminder: output ONLY valid JSON, cite passage ids like s1."
    ctx.degrade(f"extract_fallback:{entity['entity_id']}")
    return [{"text": c["text"], "chunks": [local[i] for i in c["citations"] if i in local]}
            for c in heuristics.extract_claims(names, passages, question=ctx.question)]


# ------------------------------------------------------------------ REDUCE
def conflicts_from_observations(obs: list[dict], window_days: int) -> list[tuple[dict, dict]]:
    """Two observations from DIFFERENT documents, close in time, with DIFFERENT statuses = a conflict."""
    from datetime import date as _d
    pairs = []
    for i in range(len(obs)):
        for j in range(i + 1, len(obs)):
            a, b = obs[i], obs[j]
            if a["status"] != b["status"] and a["doc_id"] != b["doc_id"]:
                if abs((_d.fromisoformat(b["date"]) - _d.fromisoformat(a["date"])).days) <= window_days:
                    pairs.append((a, b))
    return pairs


def template_summary(findings: list[dict], n_conflicts: int, window: TimeWindow) -> str:
    n = len(findings)
    if not n:
        return "No initiatives were found."
    parts = [f"{n} initiative{'s' if n != 1 else ''} matched your question ({window.label})."]
    groups: dict[str, list[str]] = defaultdict(list)
    for f in findings:
        groups[f["status"]].append(f["initiative"])
    for st in ("shipped", "active", "paused", "cancelled", "unknown"):
        if groups.get(st):
            parts.append(f"{st.capitalize()}: {', '.join(groups[st])}.")
    if n_conflicts:
        parts.append(f"{n_conflicts} status conflict{'s' if n_conflicts != 1 else ''} between sources need attention.")
    return " ".join(parts)


def make_summary(ctx: RunContext, findings: list[dict], n_conflicts: int, window: TimeWindow) -> str:
    template = template_summary(findings, n_conflicts, window)
    if not findings:
        return template
    if ctx.budget.exhausted():
        ctx.degrade("budget_stop_template_summary")
        return template
    compact = [{"initiative": f["initiative"], "status": f["status"], "period": f["period"],
                "owner_team": f["owner_team"], "key_facts": f["facts"][:2]} for f in findings]
    allowed_nums = set(re.findall(r"\d+(?:[.,]\d+)?", " ".join(
        [json.dumps(compact), window.label, str(len(findings)), str(n_conflicts)])))
    try:
        resp = ctx.provider.generate("summarize", prompts.SUMMARY_SYSTEM,
                                     prompts.summary_user(ctx.question, window.label, compact), tier="main",
                                     payload={"template_summary": template}, max_tokens=500)
        ctx.budget.charge_llm(resp.prompt_tokens, resp.completion_tokens)
        text = str(json.loads(resp.text).get("summary", "")).strip()
        if not (30 <= len(text) <= 1200):
            raise ValueError("summary length out of range")
        if any(n not in allowed_nums for n in re.findall(r"\d+(?:[.,]\d+)?", text)):
            raise ValueError("summary contains a number that is not in the findings")
        return text
    except BudgetExceeded:
        ctx.degrade("budget_stop_template_summary")
    except (LLMError, json.JSONDecodeError, ValueError, TypeError, AttributeError):
        ctx.degrade("summary_fallback")
    return template
