"""KPIs computed from stored records (never hardcoded). Run metrics are MEASURED; corpus stats are SYNTHETIC."""
from __future__ import annotations

import csv
import io
import json
from typing import Optional

from app.core import db


def _where(source: Optional[str]) -> tuple[str, list]:
    return ("WHERE source=?", [source]) if source else ("", [])


def kpis(source: Optional[str] = None) -> dict:
    w, a = _where(source)
    with db.read() as c:
        r = c.execute(f"""SELECT COUNT(*) n,
            AVG(CASE WHEN status IN ('ok','partial') THEN 1.0 ELSE 0.0 END) success,
            AVG(CASE WHEN status='abstained' THEN 1.0 ELSE 0.0 END) abst,
            AVG(CASE WHEN status NOT IN ('blocked') THEN latency_ms END) lat,
            AVG(CASE WHEN status IN ('ok','partial') THEN n_citations END) cites,
            AVG(CASE WHEN tokens>0 THEN tokens END) tok
            FROM research_runs {w}""", a).fetchone()
        fb = c.execute("SELECT AVG(CASE WHEN rating='up' THEN 1.0 ELSE 0.0 END), COUNT(*) FROM feedback").fetchone()
        denials = c.execute("SELECT COUNT(*) FROM audit_log WHERE action='document_access_denied'").fetchone()[0]
        blocked = c.execute(f"SELECT COUNT(*) FROM research_runs {w + (' AND' if w else 'WHERE')} status='blocked'",
                            a).fetchone()[0]
    n = r["n"] or 0
    return {"runs": n, "success_rate": round(r["success"] or 0.0, 3), "avg_latency_ms": round(r["lat"] or 0.0, 1),
            "avg_citations": round(r["cites"] or 0.0, 1), "abstain_rate": round(r["abst"] or 0.0, 3),
            "thumbs_up_rate": round(fb[0], 3) if fb[1] else None, "feedback_count": fb[1],
            "avg_tokens": round(r["tok"] or 0.0, 0), "acl_denials": denials, "blocked_requests": blocked}


def runs_over_time(source: Optional[str] = None) -> list[dict]:
    w, a = _where(source)
    with db.read() as c:
        rows = c.execute(f"""SELECT substr(created_at,1,10) day, COUNT(*) runs, AVG(latency_ms) avg_latency_ms
                             FROM research_runs {w} GROUP BY day ORDER BY day""", a).fetchall()
    return [{"day": r["day"], "runs": r["runs"], "avg_latency_ms": round(r["avg_latency_ms"] or 0.0, 1)} for r in rows]


def corpus_stats() -> dict:
    """SYNTHETIC corpus statistics computed from the documents table."""
    with db.read() as c:
        by_type = dict(c.execute("SELECT doc_type, COUNT(*) FROM documents GROUP BY 1").fetchall())
        by_q = {}
        for r in c.execute("SELECT effective_date FROM documents"):
            y, m = r[0][:4], int(r[0][5:7])
            key = f"{y}-Q{(m - 1) // 3 + 1}"
            by_q[key] = by_q.get(key, 0) + 1
        by_ini = dict(c.execute("""SELECT e.canonical_name, COUNT(DISTINCT m.doc_id) FROM entities e
                                   LEFT JOIN entity_mentions m ON m.entity_id = e.entity_id
                                   GROUP BY e.entity_id ORDER BY 2 DESC""").fetchall())
        total = c.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    return {"is_synthetic": True, "docs_by_type": by_type, "docs_by_quarter": dict(sorted(by_q.items())),
            "docs_by_initiative": by_ini, "total_docs": total}


def export_runs_csv(source: Optional[str] = None) -> str:
    w, a = _where(source)
    with db.read() as c:
        rows = c.execute(f"""SELECT run_id, request_id, created_at, user_id, source, status, latency_ms, tokens,
                             n_findings, n_citations, question FROM research_runs {w} ORDER BY created_at""", a).fetchall()
    buf = io.StringIO()
    wr = csv.writer(buf)
    wr.writerow(["run_id", "request_id", "created_at", "user_id", "source", "status", "latency_ms", "tokens",
                 "findings", "citations", "question"])
    for r in rows:
        wr.writerow(list(r))
    return buf.getvalue()
