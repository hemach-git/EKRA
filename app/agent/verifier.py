"""Grounding verifier: every claim must be supported by the passage(s) it cites, and the user must be able to open
those documents RIGHT NOW (live ACL re-check, not the cached allow-list). Unsupported claims are dropped."""
from __future__ import annotations

import re

from app.core.config import get_config
from app.retrieval.index import tokenize

_NUM = re.compile(r"\d+(?:[.,]\d+)?")


def grounding_score(claim: str, cited_texts: list[str]) -> float:
    """Fraction of the claim's content words found in the cited passages; any number that is NOT in the sources
    caps the score (catches invented figures)."""
    src = " ".join(cited_texts)
    src_tokens = set(tokenize(src))
    toks = [t for t in tokenize(claim) if len(t) > 2]
    if not toks:
        return 0.0
    score = sum(t in src_tokens for t in toks) / len(toks)
    src_nums = set(_NUM.findall(src))
    if any(n not in src_nums for n in _NUM.findall(claim)):
        score = min(score, 0.2)
    return round(score, 3)


def classify(score: float) -> str:
    g = get_config()["guardrails"]
    if score >= g["grounding_min_overlap"]:
        return "supported"
    if score >= g["grounding_drop_below"]:
        return "partial"
    return "drop"
