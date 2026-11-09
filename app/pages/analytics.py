"""Analytics: measured run KPIs + synthetic corpus stats. No hardcoded numbers; everything comes from services."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from app.services import analytics
from app.ui.common import badge, fmt_ms, fmt_pct, html_md

st.title("📊 Analytics")
src_label = st.segmented_control("Source", ["All", "App", "Eval"], default="All", key="an_src")
source = {"All": None, "App": "app", "Eval": "eval"}.get(src_label or "All")

try:
    k = analytics.kpis(source)
    rot = analytics.runs_over_time(source)
    cs = analytics.corpus_stats()
except Exception as e:  # noqa: BLE001
    st.error(f"Could not load analytics ({type(e).__name__}).")
    st.stop()

html_md(f"<h4 style='margin-bottom:4px'>Research runs {badge('measured')}</h4>")
st.caption(f"Computed from stored run records · source: {src_label or 'All'}")
c = st.columns(5)
c[0].metric("Runs", f"{k.get('runs', 0):,}")
c[1].metric("Success rate", fmt_pct(k.get("success_rate")), help="Share of runs with status ok or partial.")
c[2].metric("Avg latency", fmt_ms(k.get("avg_latency_ms")), help="Excludes blocked requests.")
c[3].metric("Avg citations", f"{k.get('avg_citations', 0):.1f}", help="Per successful report.")
fbn = k.get("feedback_count", 0)
c[4].metric("Thumbs-up rate", fmt_pct(k.get("thumbs_up_rate")), help=f"{fbn} feedback ratings (all sources).")
c2 = st.columns(4)
c2[0].metric("Abstain rate", fmt_pct(k.get("abstain_rate")))
c2[1].metric("Blocked requests", k.get("blocked_requests", 0))
c2[2].metric("ACL denials", k.get("acl_denials", 0), help="Document opens refused by access control.")
c2[3].metric("Avg tokens / run", f"{k.get('avg_tokens', 0):,.0f}")

if k.get("runs", 0) == 0:
    st.info("No runs recorded for this source yet.")
elif rot:
    df = pd.DataFrame(rot).set_index("day")
    a, b = st.columns(2)
    with a:
        st.markdown("**Runs per day**")
        st.bar_chart(df[["runs"]], y_label="runs", color="#1F4E79")
    with b:
        st.markdown("**Average latency per day (ms)**")
        st.line_chart(df[["avg_latency_ms"]], y_label="ms", color="#8A5A00")

csv = analytics.export_runs_csv(source)
st.download_button("⬇ Export runs (CSV)", csv, file_name=f"ekra_runs_{(source or 'all')}.csv", mime="text/csv",
                   type="primary")

st.divider()
html_md(f"<h4 style='margin-bottom:4px'>Knowledge corpus {badge('synthetic')}</h4>")
st.caption(f"{cs.get('total_docs', 0)} fictional documents generated for this prototype.")
a, b = st.columns(2)
with a:
    st.markdown("**Documents by quarter**")
    q = cs.get("docs_by_quarter") or {}
    if q:
        st.bar_chart(pd.DataFrame({"docs": q}), y_label="documents", color="#5B6675")
    else:
        st.caption("No data.")
with b:
    st.markdown("**Documents by type**")
    t = cs.get("docs_by_type") or {}
    if t:
        st.bar_chart(pd.DataFrame({"docs": t}), y_label="documents", color="#5B6675")
    else:
        st.caption("No data.")
ini = cs.get("docs_by_initiative") or {}
if ini:
    st.markdown("**Documents mentioning each initiative**")
    st.bar_chart(pd.DataFrame({"docs": ini}), horizontal=True, x_label="documents", color="#5B6675",
                 sort="-docs")
