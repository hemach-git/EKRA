"""Repeatable golden-set evaluation.   python -m evals.run [--provider mock|ollama] [--only P01,P03]

Checks per item: status, expected/excluded initiatives, final statuses, conflicts, required citations, forbidden
documents (ACL), injection text. Global invariants on EVERY answer: each claim cites a source, every cited document is
readable by the asking user, and no document outside the user's allow-list was even retrieved (ACL leak = 0).

With provider=mock the pass rate verifies pipeline WIRING, not language-model accuracy.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _parse():
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default=os.getenv("LLM_PROVIDER", "mock"))
    ap.add_argument("--only", default="")
    ap.add_argument("--golden", default=str(ROOT / "evals" / "golden.jsonl"))
    return ap.parse_args()


def check_item(item: dict, res, retrieved: set, allowed: set) -> list[str]:
    """Return a list of failure reasons (empty = pass)."""
    exp, fails = item["expect"], []
    rep = res.report
    names = [f.initiative for f in rep.findings] if rep else []
    if "status" in exp and res.status not in exp["status"]:
        fails.append(f"status {res.status!r} not in {exp['status']}")
    for n in exp.get("findings_include", []):
        if n not in names:
            fails.append(f"missing initiative: {n}")
    for n in exp.get("findings_exclude", []):
        if n in names:
            fails.append(f"unexpected initiative: {n}")
    if "max_findings" in exp and len(names) > exp["max_findings"]:
        fails.append(f"{len(names)} findings > max {exp['max_findings']}")
    if rep:
        got = {f.initiative: f.status for f in rep.findings}
        for n, st in exp.get("status_of", {}).items():
            if got.get(n) != st:
                fails.append(f"status of {n}: {got.get(n)!r} != {st!r}")
        if len(rep.conflicts) < exp.get("conflicts_min", 0):
            fails.append(f"conflicts {len(rep.conflicts)} < {exp['conflicts_min']}")
        cited = {c.doc_id for c in rep.citations}
        for d in exp.get("cite_docs_include", []):
            if d not in cited:
                fails.append(f"missing citation to {d}")
        blob = (rep.summary + " " + " ".join(c.text for f in rep.findings for c in f.claims)).lower()
        for t in exp.get("text_must_not_contain", []):
            if t.lower() in blob:
                fails.append(f"forbidden text present: {t!r}")
    else:
        for d in exp.get("cite_docs_include", []):
            fails.append(f"missing citation to {d} (no report)")
    if "message_contains" in exp and exp["message_contains"].lower() not in res.message.lower():
        fails.append(f"message lacks {exp['message_contains']!r}")
    cited_docs = {c.doc_id for c in rep.citations} if rep else set()
    for d in exp.get("forbidden_docs", []):
        if d in retrieved or d in cited_docs:
            fails.append(f"FORBIDDEN DOC REACHED THE AGENT: {d}")
    # ---- global invariants (every answer)
    if rep:
        for f in rep.findings:
            for c in f.claims:
                if not c.citations:
                    fails.append(f"uncited claim in {f.initiative}")
        valid_ids = {c.id for c in rep.citations}
        for f in rep.findings:
            for c in f.claims:
                if any(x not in valid_ids for x in c.citations):
                    fails.append(f"dangling citation id in {f.initiative}")
    return fails


def main() -> int:
    args = _parse()
    os.environ["LLM_PROVIDER"] = args.provider
    os.environ.setdefault("EKRA_REFERENCE_DATE", "2026-11-09")     # repeatable relative time windows
    sys.path.insert(0, str(ROOT))
    from app.core import db
    from app.core.config import get_config, path_for
    from app.core.models import ResearchRequest
    from app.retrieval import acl
    from app.services import research

    items = [json.loads(ln) for ln in open(args.golden, encoding="utf-8") if ln.strip()]
    if args.only:
        keep = set(args.only.split(","))
        items = [i for i in items if i["id"] in keep]
    cfg = get_config()
    print(f"EKRA golden eval | provider={args.provider} | reference_date={cfg['reference_date']} | {len(items)} items")
    rows, leaks, cit_total, cit_valid = [], 0, 0, 0
    for it in items:
        t0 = time.perf_counter()
        res = research.run_research(ResearchRequest(question=it["question"], user_id=it["user_id"], source="eval"))
        retrieved: set = set()
        with db.read() as c:
            row = c.execute("SELECT detail_json FROM audit_log WHERE request_id=? AND action='research_run'",
                            (res.request_id,)).fetchone()
        if row:
            retrieved = set(json.loads(row[0]).get("docs_retrieved", []))
        allowed = acl.allowed_doc_ids(it["user_id"])
        cited = {c.doc_id for c in res.report.citations} if res.report else set()
        leaked = sorted((retrieved | cited) - allowed)
        leaks += len(leaked)
        for c in (res.report.citations if res.report else []):
            cit_total += 1
            cit_valid += int(acl.can_read(it["user_id"], c.doc_id))
        fails = check_item(it, res, retrieved, allowed)
        if leaked:
            fails.append(f"ACL LEAK: {leaked}")
        ok = not fails
        rows.append({"id": it["id"], "category": it["category"], "user": it["user_id"], "passed": ok, "fails": fails,
                     "status": res.status, "latency_ms": res.metrics.latency_ms, "steps": res.metrics.steps,
                     "replans": res.metrics.replans,
                     "tokens": res.metrics.prompt_tokens + res.metrics.completion_tokens,
                     "n_findings": len(res.report.findings) if res.report else 0,
                     "degraded": res.metrics.degraded, "question": it["question"][:90]})
        print(f"  [{'PASS' if ok else 'FAIL'}] {it['id']:<4} {it['category']:<8} {res.status:<9} "
              f"{res.metrics.latency_ms:>6} ms  {'; '.join(fails)[:140]}")
    passed = sum(r["passed"] for r in rows)
    by_cat: dict = {}
    for r in rows:
        d = by_cat.setdefault(r["category"], {"passed": 0, "total": 0})
        d["total"] += 1
        d["passed"] += int(r["passed"])
    p01 = next((r for r in rows if r["id"] == "P01"), None)
    summary = {
        "timestamp": datetime.now().isoformat(timespec="seconds"), "provider": args.provider,
        "models": {"fast": cfg["llm"]["models"]["fast"], "main": cfg["llm"]["models"]["main"]}
        if args.provider == "ollama" else {"fast": "mock-fast", "main": "mock-main"},
        "reference_date": cfg["reference_date"], "total": len(rows), "passed": passed,
        "pass_rate": round(passed / len(rows), 3) if rows else 0.0, "acl_leaks": leaks,
        "citation_validity": round(cit_valid / cit_total, 3) if cit_total else None, "citations_checked": cit_total,
        "by_category": by_cat, "avg_latency_ms": round(sum(r["latency_ms"] for r in rows) / max(len(rows), 1)),
        "total_tokens": sum(r["tokens"] for r in rows),
        "note": ("Mock provider: pass rate checks pipeline WIRING (retrieval, ACL, verification, schema), NOT real LLM "
                 "accuracy; the mock heuristics were written alongside this golden set.")
        if args.provider == "mock" else
        "Real local LLM run (Ollama). Statuses are rules-based; claims/summary come from the model and are verified.",
        "p01_enumeration": {"found_all_expected": p01["passed"] if p01 else None},
    }
    out = path_for("eval_results")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    (out / f"eval_{stamp}_{args.provider}.json").write_text(
        json.dumps({"summary": summary, "items": rows}, indent=2), encoding="utf-8")
    md = [f"# Eval results ({args.provider}) - {summary['timestamp']}", "",
          f"**Pass rate: {passed}/{len(rows)} ({summary['pass_rate']:.0%})** | ACL leaks: **{leaks}** | "
          f"citation validity: {summary['citation_validity']} ({cit_total} checked) | avg latency: "
          f"{summary['avg_latency_ms']} ms | tokens: {summary['total_tokens']}", "", f"> {summary['note']}", "",
          "| Category | Passed | Total |", "|---|---|---|"]
    md += [f"| {k} | {v['passed']} | {v['total']} |" for k, v in by_cat.items()]
    md += ["", "| ID | Category | User | Result | Status | Latency ms | Failures |", "|---|---|---|---|---|---|---|"]
    md += [f"| {r['id']} | {r['category']} | {r['user']} | {'PASS' if r['passed'] else 'FAIL'} | {r['status']} | "
           f"{r['latency_ms']} | {'; '.join(r['fails'])} |" for r in rows]
    (out / f"latest_{args.provider}.md").write_text("\n".join(md), encoding="utf-8")
    print(f"\nRESULT: {passed}/{len(rows)} passed ({summary['pass_rate']:.0%}) | ACL leaks: {leaks} | "
          f"citation validity: {summary['citation_validity']}")
    return 0 if passed == len(rows) and leaks == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
