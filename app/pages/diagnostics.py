"""Diagnostics: health, recent requests, latest offline eval, audit trail."""
from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from app.services import diagnostics
from app.ui.common import fmt_pct, health

st.title("🩺 Diagnostics")
if st.button("↻ Refresh"):
    health.clear()

# ---- health ------------------------------------------------------------------------------------------------
st.subheader("Health")
try:
    h = health()
    c = st.columns(5)
    c[0].metric("Provider", h.get("provider", "—"))
    c[1].metric("Ollama", "✔ Reachable" if h.get("ollama_reachable") else "✖ Unreachable")
    c[2].metric("Database", "✔ OK" if h.get("db_ok") else "✖ Problem")
    c[3].metric("Documents", h.get("docs", 0))
    c[4].metric("Chunks", h.get("chunks", 0))
    with st.expander("Raw health payload"):
        st.json(h)
except Exception as e:  # noqa: BLE001
    st.error(f"Health check failed ({type(e).__name__}).")

# ---- latest eval -------------------------------------------------------------------------------------------
st.subheader("Latest offline evaluation")
try:
    ev = diagnostics.latest_eval()
except Exception as e:  # noqa: BLE001
    ev = None
    st.error(f"Could not read eval results ({type(e).__name__}).")
if not ev:
    st.info("No evaluation has been run yet (`evals/run.py`).")
else:
    if ev.get("provider") == "mock":
        st.warning("**Mock provider.** This pass rate checks pipeline *wiring* (retrieval, ACL, verification, "
                   "schema), **not** real LLM accuracy.")
    c = st.columns(5)
    c[0].metric("Pass rate", fmt_pct(ev.get("pass_rate")), help=f"{ev.get('passed')} / {ev.get('total')} cases")
    leaks = ev.get("acl_leaks", 0)
    c[1].metric("ACL leaks", leaks, help="Must be 0: documents a user cannot open must never be cited.")
    c[2].metric("Citation validity", fmt_pct(ev.get("citation_validity")),
                help=f"{ev.get('citations_checked', 0)} citations checked")
    c[3].metric("Avg latency", f"{ev.get('avg_latency_ms', 0)} ms")
    c[4].metric("Total tokens", f"{ev.get('total_tokens', 0):,}")
    if leaks:
        st.error(f"⛔ {leaks} ACL leak(s) detected — this must be 0.")
    else:
        st.success("✔ ACL leaks: 0")
    st.caption(f"Run {ev.get('timestamp', '—')} · provider `{ev.get('provider')}` · models "
               f"{ev.get('models', {})} · reference date {ev.get('reference_date', '—')}")
    cats = ev.get("by_category") or {}
    if cats:
        cdf = pd.DataFrame([{"Category": k, "Passed": v.get("passed", 0), "Total": v.get("total", 0),
                             "Pass rate": (v.get("passed", 0) / v["total"]) if v.get("total") else 0.0}
                            for k, v in cats.items()])
        st.dataframe(cdf, hide_index=True, width="stretch",
                     column_config={"Pass rate": st.column_config.ProgressColumn(format="percent", min_value=0,
                                                                                  max_value=1)})
    if ev.get("note"):
        st.caption(ev["note"])

# ---- recent requests ---------------------------------------------------------------------------------------
st.subheader("Recent requests")
try:
    rr = diagnostics.recent_requests(50)
except Exception as e:  # noqa: BLE001
    rr = []
    st.error(f"Could not read the request log ({type(e).__name__}).")
if rr:
    st.dataframe(pd.DataFrame(rr)[["ts", "request_id", "user_id", "status", "duration_ms", "tokens", "provider",
                                   "steps", "error"]], hide_index=True, width="stretch", height=300)
else:
    st.caption("No requests logged yet.")

# ---- audit trail -------------------------------------------------------------------------------------------
st.subheader("Audit trail")
try:
    at = diagnostics.audit_trail(100)
except Exception as e:  # noqa: BLE001
    at = []
    st.error(f"Could not read the audit trail ({type(e).__name__}).")
if at:
    actions = sorted({a["action"] for a in at})
    pick = st.multiselect("Filter actions", actions, default=[])
    rows = [a for a in at if not pick or a["action"] in pick]
    st.dataframe(pd.DataFrame([{"ts": a["ts"], "request_id": a["request_id"], "user_id": a["user_id"],
                                "action": a["action"], "model": a["model"],
                                "detail": json.dumps(a["detail"], default=str)} for a in rows]),
                 hide_index=True, width="stretch", height=320,
                 column_config={"detail": st.column_config.TextColumn(width="large")})
else:
    st.caption("No audit events yet.")
