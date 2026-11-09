"""Tool implementations + executor (validation, timeout, retry/backoff, loop detection, audit of retrieved docs)."""
from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from typing import Any

from app.agent.budget import BudgetExceeded, LoopDetected
from app.agent.context import RunContext
from app.core import db
from app.core.logging import log_event
from app.data.seed import alias_regex
from app.retrieval.index import SearchIndex, get_index
from app.tools.schemas import TOOL_ARGS, ToolResult

TOOL_TIMEOUT_S = {"hybrid_search": 40, "list_documents": 10, "fetch_document": 10, "entity_lookup": 10}
_pool = ThreadPoolExecutor(max_workers=6, thread_name_prefix="tool")       # runs the tool bodies
_fan = ThreadPoolExecutor(max_workers=6, thread_name_prefix="fanout")      # separate pool: avoids nested-submit deadlock


def _entity_table() -> list[dict]:
    with db.read() as c:
        ents = {r["entity_id"]: dict(r) for r in c.execute("SELECT * FROM entities")}
        for e in ents.values():
            e["aliases"] = []
        for r in c.execute("SELECT alias, entity_id FROM entity_aliases ORDER BY alias"):
            ents[r["entity_id"]]["aliases"].append(r["alias"])
    import json
    for e in ents.values():
        e["topics"] = json.loads(e["topics"])
    return list(ents.values())


def entity_docs(index: SearchIndex) -> dict[str, set]:
    out: dict[str, set] = {}
    for r in index.recs:
        for e in r["entities"]:
            out.setdefault(e, set()).add(r["doc_id"])
    return out


# ------------------------------------------------------------------ tool bodies
def _entity_lookup(ctx: RunContext, a, index: SearchIndex) -> list[dict]:
    terms = [t.lower().strip() for t in a.terms if t.strip()]
    edocs = entity_docs(index)
    out = []
    for e in _entity_table():
        visible = edocs.get(e["entity_id"], set()) & ctx.allowed        # never reveal initiatives the user can't see
        if not visible:
            continue
        matched = []
        for term in terms:
            for topic in e["topics"]:
                if re.search(rf"\b{re.escape(topic.lower())}\b", term) or (len(term) > 3 and re.search(rf"\b{re.escape(term)}\b", topic.lower())):
                    matched.append(topic)
            for al in e["aliases"]:
                if alias_regex(al).search(term):
                    matched.append(al)
        if matched:
            out.append({"entity_id": e["entity_id"], "name": e["canonical_name"], "aliases": e["aliases"],
                        "owner_team": e["owner_team"], "matched_on": sorted(set(matched))})
    return out


def _list_documents(ctx: RunContext, a, index: SearchIndex) -> list[dict]:
    ids = set(a.entity_ids)
    docs: dict[str, dict] = {}
    for r in index.recs:
        if r["doc_id"] not in ctx.allowed or r["superseded"] or not (r["entities"] & ids):
            continue
        if a.date_from and r["date"] < a.date_from or a.date_to and r["date"] > a.date_to:
            continue
        d = docs.setdefault(r["doc_id"], {"doc_id": r["doc_id"], "title": r["title"], "doc_type": r["doc_type"],
                                          "effective_date": r["date"].isoformat(), "entity_ids": set()})
        d["entity_ids"] |= (r["entities"] & ids)
    out = sorted(({**d, "entity_ids": sorted(d["entity_ids"])} for d in docs.values()),
                 key=lambda d: d["effective_date"])
    return out[:200]


def _hybrid_search(ctx: RunContext, a, index: SearchIndex) -> list:
    hits, notes = index.search(a.query, ctx.allowed, date_from=a.date_from, date_to=a.date_to, doc_types=a.doc_types,
                               entity_ids=a.entity_ids, doc_ids=a.doc_ids, top_k=a.top_k)
    for n in notes:
        ctx.degrade(n)
    return hits


def _fetch_document(ctx: RunContext, a, index: SearchIndex) -> list:
    if a.doc_id not in ctx.allowed:
        return []                                              # indistinguishable from "does not exist"
    return index.chunks_of(a.doc_id)


_IMPL = {"entity_lookup": _entity_lookup, "list_documents": _list_documents,
         "hybrid_search": _hybrid_search, "fetch_document": _fetch_document}


# ------------------------------------------------------------------ executor
def call_tool(ctx: RunContext, name: str, args: dict[str, Any]) -> ToolResult:
    t0 = time.perf_counter()

    def done(status, data=None, hint="", n=0) -> ToolResult:
        ms = int((time.perf_counter() - t0) * 1000)
        log_event("tool_call", tool=name, status=status, duration_ms=ms, n=n, hint=hint[:120])
        return ToolResult(tool=name, status=status, data=data, hint=hint, duration_ms=ms, n=n)

    if name not in TOOL_ARGS:
        return done("error", hint=f"unknown tool '{name}'")
    try:
        parsed = TOOL_ARGS[name](**args)
    except Exception as e:  # noqa: BLE001
        return done("error", hint=f"invalid arguments: {str(e)[:150]}")
    try:
        ctx.budget.register_tool_call(name, parsed.model_dump(mode="json"))
    except LoopDetected as e:
        return done("skipped", hint=str(e))
    except BudgetExceeded:
        raise
    index = get_index(ctx.provider)
    last = ""
    for attempt in range(2):                                   # 1 retry with backoff
        fut = _pool.submit(_IMPL[name], ctx, parsed, index)
        try:
            data = fut.result(timeout=TOOL_TIMEOUT_S[name])
            break
        except FutureTimeout:
            last = f"timeout after {TOOL_TIMEOUT_S[name]}s"
        except Exception as e:  # noqa: BLE001
            last = f"{type(e).__name__}: {e}"
        time.sleep(0.2 * (attempt + 1))
    else:
        return done("error", hint=last)                        # error goes back to the planner as an observation
    if name in ("hybrid_search", "fetch_document"):
        for h in data:
            ctx.note(h)
    if not data:
        return done("empty", data=[], hint="no accessible results; try broader terms or a wider date range")
    return done("ok", data=data, n=len(data))


def call_many(ctx: RunContext, calls: list[tuple[str, dict]]) -> list[ToolResult]:
    """Parallel fan-out. Each call is independent; failures are returned, not raised (except budget stops)."""
    futs = [_fan.submit(call_tool, ctx, n, a) for n, a in calls]
    return [f.result() for f in futs]
