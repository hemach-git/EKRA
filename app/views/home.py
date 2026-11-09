"""Home: what EKRA does, how it works, system status, demo journeys."""
from __future__ import annotations

import streamlit as st

from app.ui.common import badge, current_user, health, html_md

html_md(f"<div class='ekra-hero'><h1>EKRA Research Assistant</h1></div>{badge('synthetic')}")
st.markdown(
    "Ask a complex question about company initiatives and get a **cited research report** in seconds.  \n"
    "EKRA searches wikis, PRDs, roadmaps, meeting notes and status reports **you are allowed to see**, "
    "reconciles conflicting sources and builds a timeline.  \n"
    "Every claim links back to its source; anything it cannot ground is dropped or flagged as a gap.")

st.markdown("#### How it works")
cols = st.columns(4)
for col, (icon, title, text) in zip(cols, [
    ("🧭", "1 · Plan", "Resolves the time window, expands aliases and drafts search queries."),
    ("🔐", "2 · Retrieve", "Hybrid keyword + vector search, filtered by the signed-in user's access."),
    ("🧩", "3 · Synthesize", "Extracts per-initiative claims, status history, timeline and conflicts."),
    ("✅", "4 · Verify", "Checks every claim against its cited text; unsupported claims are dropped."),
]):
    with col.container(border=True):
        st.markdown(f"**{icon} {title}**")
        st.caption(text)

st.markdown("#### Try a demo journey")
JOURNEYS = [
    ("📚 Portfolio summary", "Summarize all company initiatives related to personalization and recommendation "
                            "systems from the last 2 years.", "Multi-source synthesis with timeline and conflicts."),
    ("🔍 Did we ever try…?", "Did we ever try two-tower retrieval for the home feed?",
     "Alias resolution across old project code names."),
    ("⏸️ Paused & cancelled", "Which personalization initiatives were paused or cancelled, and why?",
     "Status reasoning with cited reasons."),
]


def _go(q: str) -> None:
    st.session_state["question"] = q


jc = st.columns(3)
for col, (label, q, why) in zip(jc, JOURNEYS):
    with col.container(border=True):
        st.markdown(f"**{label}**")
        st.caption(why)
        st.markdown(f"<span class='ekra-muted'>“{q}”</span>", unsafe_allow_html=True)
        if st.button("Open in Ask →", key=f"j-{label}", type="primary", width="stretch", on_click=_go, args=(q,)):
            st.switch_page(st.session_state["_pages"]["ask"])

u = current_user()
if u:
    st.caption(f"Signed in as **{u.name}** ({u.role}). Results depend on which documents this user can open — "
               "try the same question as `dave` (contractor) to see access control in action.")

st.markdown("#### System status")
try:
    with st.spinner("Checking system health…"):
        h = health()
    c = st.columns(5)
    c[0].metric("LLM provider", h.get("provider", "—"))
    c[1].metric("Ollama", "✔ Reachable" if h.get("ollama_reachable") else "✖ Unreachable")
    c[2].metric("Database", "✔ OK" if h.get("db_ok") else "✖ Problem")
    c[3].metric("Documents", h.get("docs", 0), help="Synthetic corpus")
    c[4].metric("Chunks", h.get("chunks", 0), help="Indexed passages")
    mdl = h.get("models", {})
    st.caption(f"Models — fast `{mdl.get('fast', '—')}` · main `{mdl.get('main', '—')}` · embeddings "
               f"`{mdl.get('embed', '—')}`")
    if h.get("provider") == "ollama" and not h.get("ollama_reachable"):
        st.warning("Ollama is not reachable, so research runs may fail or degrade. Start Ollama or switch the "
                   "provider to `mock` in config.")
except Exception as e:  # noqa: BLE001
    st.error(f"Health check failed ({type(e).__name__}). See Diagnostics for details.")
