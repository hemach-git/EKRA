"""The agent: PLAN -> ACT -> OBSERVE -> (REPLAN) -> SYNTHESIZE -> VERIFY.

Single planner + deterministic parallel fan-out (design decision: fewer hand-offs = fewer cascading errors).
Every retrieval is scoped by the user's ACL; every claim is verified against its cited passage before delivery.
"""
from __future__ import annotations

import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from app.agent import heuristics
from app.agent.budget import BudgetExceeded
from app.agent.context import RunContext
from app.agent.planner import default_sub_queries, llm_sub_queries, topic_terms
from app.agent.synthesizer import (conflicts_from_observations, coverage_gaps, extract_entity, make_summary,
                                   other_aliases, select_evidence)
from app.agent.timewin import parse_window
from app.agent.verifier import classify, grounding_score
from app.core.config import get_config, today
from app.core.logging import log_event
from app.core.models import Citation, Claim, Conflict, Finding, Report, TimelineEvent
from app.retrieval import acl
from app.retrieval.index import get_index
from app.tools.tools import call_many, call_tool

NO_ACCESS_MSG = ("No accessible sources were found for this question in your time window. Either nothing relevant "
                 "exists, or the relevant documents are not visible to your account.")


@dataclass
class AgentResult:
    status: str
    message: str = ""
    report: Optional[Report] = None
    docs_cited: int = 0
    claims_total: int = 0
    claims_dropped: int = 0


def _rec(ctx: RunContext, kind, tool, purpose, args, status, summary, t0):
    ctx.add_step(kind=kind, tool=tool, purpose=purpose, args=args, status=status, summary=summary,
                 duration_ms=int((time.perf_counter() - t0) * 1000))


def run_agent(ctx: RunContext) -> AgentResult:
    cfg = get_config()["agent"]
    index = get_index(ctx.provider)
    partial: Optional[str] = None
    entities: dict[str, dict] = {}
    universe: dict[str, list[dict]] = {}
    global_hits: list = []
    try:
        # ---------------------------------------------------------------- PLAN
        ctx.budget.start_step()
        t0 = time.perf_counter()
        ctx.window = parse_window(ctx.question, today())
        topics = topic_terms(ctx.question)
        subq = llm_sub_queries(ctx, topics, default_sub_queries(ctx.question, topics))
        _rec(ctx, "plan", "planner", "Resolve the time window and expand search terms",
             {"window": ctx.window.label, "topics": topics, "sub_queries": subq}, "ok",
             f"Window: {ctx.window.label}. {len(subq)} search queries planned.", t0)

        # ---------------------------------------------------------------- ACT: which initiatives?
        ctx.budget.start_step()
        t0 = time.perf_counter()
        r = call_tool(ctx, "entity_lookup", {"terms": [ctx.question, *topics]})
        entities = {e["entity_id"]: e for e in (r.data or [])} if r.status == "ok" else {}
        named = {k: v for k, v in entities.items() if v.get("named")}
        narrowed = bool(named) and len(named) < len(entities)
        if named:                                     # the question names specific initiatives -> stay on them
            entities = named
        _rec(ctx, "act", "entity_lookup", "Find known initiatives that match the question", {"terms": topics},
             r.status, f"{len(entities)} candidate initiatives" + (": " + ", ".join(e["name"] for e in entities.values())
                                                                  if entities else "")
             + (" (question names them explicitly, so broader topic matches were set aside)" if narrowed else ""), t0)
        if not entities:
            return AgentResult("abstained", NO_ACCESS_MSG)

        # ---------------------------------------------------------------- ACT: scan documents (coverage universe)
        ctx.budget.start_step()
        t0 = time.perf_counter()
        r = call_tool(ctx, "list_documents", {"entity_ids": list(entities), "date_from": ctx.window.start,
                                              "date_to": ctx.window.end})
        for d in (r.data or []):
            for eid in d["entity_ids"]:
                universe.setdefault(eid, []).append(d)
        entities = {k: v for k, v in entities.items() if universe.get(k)}
        _rec(ctx, "act", "list_documents", "Scan which accessible documents mention each initiative in the window",
             {"entities": len(entities)}, r.status, f"{len(r.data or [])} documents across {len(entities)} initiatives", t0)
        if not entities:
            return AgentResult("abstained", NO_ACCESS_MSG)

        win = {"date_from": ctx.window.start, "date_to": ctx.window.end}

        # ---------------------------------------------------------------- ACT: parallel sub-query search
        ctx.budget.start_step()
        t0 = time.perf_counter()
        results = call_many(ctx, [("hybrid_search", {"query": q, "top_k": cfg["top_k"], **win}) for q in subq])
        for res in results:
            global_hits += res.data or []
        _rec(ctx, "act", "hybrid_search", f"Search {len(subq)} query variants in parallel (ACL pre-filtered)",
             {"queries": subq}, "ok" if global_hits else "empty",
             f"{len(global_hits)} passages from {len({h.doc_id for h in global_hits})} documents", t0)

        # ---------------------------------------------------------------- ACT: parallel evidence per initiative
        ctx.budget.start_step()
        t0 = time.perf_counter()
        calls = [("hybrid_search", {"query": f"{e['name']} {' '.join(e['aliases'][:3])} status goal decision",
                                    "entity_ids": [eid], "top_k": cfg["max_evidence_per_entity"] + 2, **win})
                 for eid, e in entities.items()]
        results = call_many(ctx, calls)
        _rec(ctx, "act", "hybrid_search", "Gather evidence for each initiative in parallel",
             {"initiatives": len(calls)}, "ok", f"{sum(res.n for res in results)} passages collected", t0)

        # ---------------------------------------------------------------- OBSERVE / REPLAN
        while True:
            t0 = time.perf_counter()
            gaps = {eid: coverage_gaps(index, ctx, eid, universe[eid]) for eid in entities}
            gaps = {k: v for k, v in gaps.items() if v}
            n_missing = sum(len(v) for v in gaps.values())
            _rec(ctx, "observe", "coverage_check",
                 "Check that each initiative's earliest and latest documents have been read",
                 {"initiatives": len(entities)}, "ok" if not gaps else "empty",
                 "Coverage complete." if not gaps else
                 f"{n_missing} key documents not yet read for {len(gaps)} initiatives: "
                 + ", ".join(entities[k]["name"] for k in gaps), t0)
            if not gaps or not ctx.budget.can_replan():
                break
            ctx.budget.start_step()
            ctx.budget.replans += 1
            t0 = time.perf_counter()
            ranked = [d for rank in range(max(len(v) for v in gaps.values()))      # round-robin: every initiative's
                      for v in gaps.values() for d in v[rank:rank + 1]]            # top-priority document first
            todo = list(dict.fromkeys(ranked))[:cfg["max_fetch_per_replan"]]
            results = call_many(ctx, [("fetch_document", {"doc_id": d}) for d in todo])
            _rec(ctx, "replan", "fetch_document", "Replan: read the key documents that search did not surface",
                 {"doc_ids": todo}, "ok" if any(x.status == "ok" for x in results) else "empty",
                 f"Fetched {sum(1 for x in results if x.status == 'ok')} of {len(todo)} documents", t0)
    except BudgetExceeded as e:
        partial = e.reason
        log_event("budget_exceeded", reason=e.reason)

    # -------------------------------------------------------------------- SYNTHESIZE
    if not entities or not ctx.ledger:
        return AgentResult("partial" if partial else "abstained",
                           f"Stopped early: {partial}." if partial else NO_ACCESS_MSG)
    t0 = time.perf_counter()
    evidence = {eid: select_evidence(index, ctx, eid, universe[eid], cfg["max_evidence_per_entity"],
                                     [entities[eid]["name"], *entities[eid]["aliases"]])
                for eid in entities}
    evidence = {k: v for k, v in evidence.items() if v}
    passages: dict[str, list[dict]] = {}
    for eid, hits in evidence.items():
        passages[eid] = [{"cid": f"s{i + 1}", "chunk_id": h.chunk_id, "doc_id": h.doc_id, "text": h.text,
                          "date": h.effective_date.isoformat(), "doc_type": h.doc_type, "title": h.title,
                          "section": h.section, "single_entity": len(index.entities_of_chunk(h.chunk_id)) == 1,
                          "other_aliases": other_aliases(index, eid, h.chunk_id)}
                         for i, h in enumerate(hits)]

    def work(eid: str):
        try:
            return eid, extract_entity(ctx, entities[eid], passages[eid])
        except Exception as e:  # noqa: BLE001  one initiative failing must not sink the report
            ctx.degrade(f"extract_error:{eid}")
            log_event("extract_error", entity=eid, error=f"{type(e).__name__}: {e}")
            names = [entities[eid]["name"], *entities[eid]["aliases"]]
            local = {p["cid"]: p["chunk_id"] for p in passages[eid]}
            return eid, [{"text": c["text"], "chunks": [local[i] for i in c["citations"]]}
                         for c in heuristics.extract_claims(names, passages[eid], question=ctx.question)]

    with ThreadPoolExecutor(max_workers=cfg["extract_workers"]) as ex:
        claims_by_ent = dict(ex.map(work, list(passages)))
    obs_by_ent = {}
    for eid in passages:
        names = [entities[eid]["name"], *entities[eid]["aliases"]]
        local = {p["cid"]: p for p in passages[eid]}
        obs_by_ent[eid] = [{"status": o["status"], "date": o["date"], "chunk_id": local[o["citation"]]["chunk_id"],
                            "doc_id": local[o["citation"]]["doc_id"], "title": local[o["citation"]]["title"]}
                           for o in heuristics.status_observations(names, passages[eid])]
    _rec(ctx, "synthesize", "extract_claims", "Extract cited claims per initiative (parallel) and derive status",
         {"initiatives": len(passages)}, "ok",
         f"{sum(len(v) for v in claims_by_ent.values())} candidate claims for {len(passages)} initiatives", t0)

    # -------------------------------------------------------------------- VERIFY + assemble
    t0 = time.perf_counter()
    report, stats = _verify_and_assemble(ctx, index, entities, evidence, claims_by_ent, obs_by_ent, global_hits)
    _rec(ctx, "verify", "verifier", "Ground every claim in its cited passage and re-check document access live",
         {}, "ok" if report else "empty",
         f"{stats['kept']} claims kept, {stats['dropped']} dropped" if report else "Nothing survived verification", t0)
    if report is None:
        return AgentResult("partial" if partial else "abstained", NO_ACCESS_MSG, claims_total=stats["total"],
                           claims_dropped=stats["dropped"])
    msgs = []
    if ctx.injection_docs:
        msgs.append(f"Security note: {len(ctx.injection_docs)} source document(s) contained instruction-like text, "
                    "which was ignored.")
    if partial:
        msgs.insert(0, f"Partial result: {partial}. Findings cover the evidence gathered before the limit.")
    return AgentResult("partial" if partial else "ok", " ".join(msgs), report,
                       docs_cited=len({c.doc_id for c in report.citations}), claims_total=stats["total"],
                       claims_dropped=stats["dropped"])


def _verify_and_assemble(ctx, index, entities, evidence, claims_by_ent, obs_by_ent, global_hits):
    cfg_c = get_config()["conflict"]
    cmap: dict[str, str] = {}          # chunk_id -> final citation id (c1, c2, ... in order of first use)

    def use(chunk_id: str) -> str:
        return cmap.setdefault(chunk_id, f"c{len(cmap) + 1}")

    def readable(chunk_id: str) -> bool:                      # live ACL re-check, not the cached allow-list
        h = ctx.ledger.get(chunk_id)
        return bool(h) and acl.can_read(ctx.user_id, h.doc_id)

    total = dropped = kept_n = 0
    findings: list[Finding] = []
    conflicts: list[Conflict] = []
    timeline: list[TimelineEvent] = []
    gaps: list[str] = []
    order = sorted(evidence, key=lambda e: evidence[e][0].effective_date)
    for eid in order:
        ent = entities[eid]
        kept: list[Claim] = []
        for c in claims_by_ent.get(eid, []):
            total += 1
            chunks = [x for x in c["chunks"] if readable(x)]
            if not chunks:
                dropped += 1
                continue
            score = grounding_score(c["text"], [ctx.ledger[x].text for x in chunks])
            cls = classify(score)
            if cls == "drop":
                dropped += 1
                log_event("claim_dropped", entity=eid, score=score, text=c["text"][:120])
                continue
            kept.append(Claim(text=c["text"], citations=[use(x) for x in chunks], support=cls, grounding_score=score))
            first = ctx.ledger[chunks[0]]
            timeline.append(TimelineEvent(date=first.effective_date, initiative=ent["name"], event=c["text"],
                                          citations=[cmap[chunks[0]]]))
        if not kept:
            continue
        kept_n += len(kept)
        obs = [o for o in obs_by_ent.get(eid, []) if readable(o["chunk_id"])]
        history, last = [], None
        for o in obs:
            if o["status"] != last:
                history.append({"status": o["status"], "date": o["date"], "citation": use(o["chunk_id"]),
                                "source": o["title"]})
                last = o["status"]
        for a, b in conflicts_from_observations(obs, cfg_c["window_days"]):
            conflicts.append(Conflict(
                initiative=ent["name"], citations=[use(a["chunk_id"]), use(b["chunk_id"])],
                description=(f"Sources disagree on status: '{a['status']}' in \"{a['title']}\" ({a['date']}) vs "
                             f"'{b['status']}' in \"{b['title']}\" ({b['date']}).")))
        dates = [h.effective_date for h in evidence[eid]]
        period = (dates[0].strftime("%Y-%m") if dates[0].strftime("%Y-%m") == dates[-1].strftime("%Y-%m")
                  else f"{dates[0]:%Y-%m} to {dates[-1]:%Y-%m}")
        status = history[-1]["status"] if history else "unknown"
        findings.append(Finding(initiative=ent["name"], entity_id=eid,
                                aliases=[a for a in ent["aliases"] if a != ent["name"]], owner_team=ent["owner_team"],
                                period=period, status=status, status_history=history, claims=kept))
        ref_end = ctx.window.end or today()
        if status == "active" and dates[-1] < ref_end - timedelta(days=180):
            gaps.append(f"No updates found for {ent['name']} since {dates[-1]} (still marked active).")
    stats = {"total": total, "dropped": dropped, "kept": kept_n}
    if not findings:
        return None, stats

    linked = set(entities)
    other = [h for h in global_hits if not (index.entities_of_chunk(h.chunk_id) & linked)]
    if other:
        gaps.append(f"{len({h.doc_id for h in other})} other document(s) matched your keywords but belong to "
                    "initiatives outside this topic, so they were not summarized.")

    timeline.sort(key=lambda t: (t.date, t.initiative))
    fl = [{"initiative": f.initiative, "status": f.status, "period": f.period, "owner_team": f.owner_team,
           "facts": [c.text for c in f.claims]} for f in findings]
    summary = make_summary(ctx, fl, len(conflicts), ctx.window)

    citations = []
    for chunk_id, cid in cmap.items():
        h = ctx.ledger[chunk_id]
        citations.append(Citation(id=cid, doc_id=h.doc_id, title=h.title, section=h.section, doc_type=h.doc_type,
                                  effective_date=h.effective_date, url=h.url, chunk_id=chunk_id))
    report = Report(question=ctx.question, summary=summary, time_window=ctx.window, findings=findings,
                    timeline=timeline, conflicts=conflicts, gaps=gaps, citations=citations)
    return report, stats
