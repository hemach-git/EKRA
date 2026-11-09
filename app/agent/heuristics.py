"""Deterministic rules shared by (a) the mock LLM, (b) the fallback when a real LLM returns bad output, and
(c) status detection. Initiative STATUS is always derived here, never trusted from a model: auditable by design."""
from __future__ import annotations

import re
from typing import Optional

from app.data.seed import alias_regex

_LABEL = re.compile(r"status:\s*([a-z0-9 ,\-]+)", re.I)
_SENT = re.compile(r"(?<=[.!?])\s+")


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT.split(text.replace("\n", " ")) if s.strip()]


def map_status(label: str) -> Optional[str]:
    s = label.lower()
    if re.search(r"cancel|canceled|terminated", s):
        return "cancelled"
    if re.search(r"\bpaus|on hold", s):
        return "paused"
    if re.search(r"\bship|\blaunched|\blive\b|\bcompleted?\b|reached general availability|\bga\b", s):
        return "shipped"
    if re.search(r"beta|progress|pilot|\bbuild|discovery|\bactive|on track|kicks? off|kicked off|piloting|expands", s):
        return "active"
    return None


def infer_status(scope_text: str) -> Optional[str]:
    m = _LABEL.search(scope_text)
    if m:
        st = map_status(m.group(1))
        if st:
            return st
    for st in ("cancelled", "paused", "shipped", "active"):   # priority order
        probe = {"cancelled": r"\bcancel|\bcanceled", "paused": r"\bpaused\b|on hold",
                 "shipped": r"\bshipped\b|\blaunched\b|reached general availability|\bis live\b",
                 "active": r"in progress|\bbeta\b|\bpilot|in build|discovery|\bis active\b|kicks off|started with"}[st]
        if re.search(probe, scope_text, re.I):
            return st
    return None


def _first_pos(pats, sentence: str):
    pos = [m.start() for p in pats if (m := p.search(sentence))]
    return min(pos) if pos else None


def scope_sentences(names: list[str], passage: dict, exclusive: bool = False) -> list[str]:
    """Sentences about this initiative. With exclusive=True (status inference), a sentence that also names OTHER
    initiatives is credited to the one named FIRST: "UVec v1 is in progress; consumers are Compass and Lantern" is
    about UVec, so it says nothing about the status of Compass or Lantern."""
    pats = [alias_regex(n) for n in names]
    others = [alias_regex(a) for a in passage.get("other_aliases", [])] if exclusive else []
    single = passage.get("single_entity")
    out = []
    for s in split_sentences(passage["text"]):
        mine, theirs = _first_pos(pats, s), _first_pos(others, s)
        if mine is None and not single:
            continue                                   # multi-initiative passage: only sentences naming this one
        if theirs is not None and (mine is None or theirs <= mine):
            continue                                   # another initiative is the subject of this sentence
        out.append(s)
    return out


def status_observations(names: list[str], passages: list[dict]) -> list[dict]:
    out = []
    for p in passages:
        scope = " ".join(scope_sentences(names, p, exclusive=True))
        st = infer_status(scope) if scope else None
        if st:
            out.append({"status": st, "date": p["date"], "citation": p["cid"]})
    return sorted(out, key=lambda o: o["date"])


_SIGNAL = re.compile(r"\b(goal|target|metric|risk|decid|agreed|rolled back|rollback|approved|recommend|"
                     r"launched|shipped|paused|cancel|reached|expands?|complete|started|kicks? off)", re.I)


_GENERIC = {"ever", "try", "tried", "company", "initiative", "initiatives", "summarize", "related", "systems",
            "system", "years", "last", "status", "tell", "about", "what", "which", "give", "happened", "project",
            "projects"}


def _q_tokens(question: str) -> set:
    from app.retrieval.index import tokenize
    return {t for t in tokenize(question) if len(t) > 3 and t not in _GENERIC}


def extract_claims(names: list[str], passages: list[dict], max_claims: int = 8, question: str = "") -> list[dict]:
    """Rules-based extraction: best sentence per passage first (so every source is represented), then the next best.
    Sentences that overlap with the user's question rank higher, so the claims answer what was actually asked."""
    from app.retrieval.index import tokenize
    firsts, seconds, seen = [], [], set()
    qt = _q_tokens(question) if question else set()
    for pi, p in enumerate(passages):
        cands = []
        for i, s in enumerate(scope_sentences(names, p)):
            if len(s.split()) < 5 or s.lower().startswith("status:"):
                continue
            overlap = len(qt & set(tokenize(s)))
            score = (2 if re.search(r"\d", s) else 0) + (1 if _SIGNAL.search(s) else 0) + 2 * min(overlap, 3)
            cands.append((-score, i, s))
        for rank, (neg, _, s) in enumerate(sorted(cands)[:2]):
            key = re.sub(r"\W+", " ", s.lower()).strip()
            if key in seen:
                continue
            seen.add(key)
            (firsts if rank == 0 else seconds).append((neg, pi, {"text": s[:300], "citations": [p["cid"]]}))
    chosen = sorted(firsts)[:max_claims]
    chosen += sorted(seconds)[: max(0, max_claims - len(chosen))]
    return [c for _, _, c in sorted(chosen, key=lambda t: t[1])]
