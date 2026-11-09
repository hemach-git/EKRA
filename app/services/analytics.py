"""STUB v0. Real version computes everything from stored runs/corpus records."""
from typing import Optional


def kpis(source: Optional[str] = None) -> dict:
    """Returns {"runs": int, "success_rate": float, "avg_latency_ms": float, "avg_citations": float,
    "abstain_rate": float, "thumbs_up_rate": float|None, "avg_tokens": float, "acl_denials": int}"""
    return {"runs": 0, "success_rate": 0.0, "avg_latency_ms": 0.0, "avg_citations": 0.0, "abstain_rate": 0.0,
            "thumbs_up_rate": None, "avg_tokens": 0.0, "acl_denials": 0}


def runs_over_time(source: Optional[str] = None) -> list[dict]:
    """[{"day": "2026-11-09", "runs": 3, "avg_latency_ms": 4100.0}]"""
    return []


def corpus_stats() -> dict:
    """{"is_synthetic": True, "docs_by_type": {...}, "docs_by_quarter": {...}, "docs_by_initiative": {...}, "total_docs": int}"""
    return {"is_synthetic": True, "docs_by_type": {}, "docs_by_quarter": {}, "docs_by_initiative": {}, "total_docs": 0}


def export_runs_csv(source: Optional[str] = None) -> str:
    return "run_id,question,status\n"
