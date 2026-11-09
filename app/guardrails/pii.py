"""PII / secret masking, applied to everything written to logs and the audit trail."""
from __future__ import annotations

import re

_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("API_KEY", re.compile(r"\b(?:sk|pk|rk)-[A-Za-z0-9_\-]{12,}\b")),
    ("BEARER", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{16,}")),
    ("AWS_KEY", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("EMAIL", re.compile(r"\b[\w.+\-]+@[\w\-]+(?:\.[\w\-]+)+\b")),
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("PHONE", re.compile(r"(?<!\d)(?:\+?1[\s.\-]?)?\(?\d{3}\)?[\s.\-]\d{3}[\s.\-]\d{4}(?!\d)")),
    ("CARD", re.compile(r"\b(?:\d[ \-]?){13,16}\b")),
]


def mask_text(text: str) -> str:
    for label, pat in _PATTERNS:
        text = pat.sub(f"[{label}]", text)
    return text


def mask_obj(obj):
    """Recursively mask strings inside dicts/lists (used for log fields)."""
    if isinstance(obj, str):
        return mask_text(obj)
    if isinstance(obj, dict):
        return {k: mask_obj(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [mask_obj(v) for v in obj]
    return obj
