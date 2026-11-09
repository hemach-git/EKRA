"""Render a RunResult: banner, summary, findings, timeline, conflicts, gaps, citations, trace, metrics, downloads."""
from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from app.core.models import Citation, Report, RunResult
from app.services import research
from app.ui.common import (STEP_STATUS, cite_chips, fmt_ms, html_md, initiative_status_chip, run_status_chip,
                           status_banner)


# ---- markdown export ----------------------------------------------------------------------------------------
def to_markdown(res: RunResult) -> str:
    out = [f"# EKRA Research Report", "",
           f"**Question:** {res.question}  ", f"**Status:** {res.status}  ",
           f"**Run:** `{res.run_id}` · request `{res.request_id}` · user `{res.user_id}` · {res.created_at}  ",
           "_All data is synthetic._", ""]
    if res.message:
        out += [f"> {res.message}", ""]
    rep = res.report
    if rep:
        out += [f"**Time window:** {rep.time_window.label}", "", "## Summary", "", rep.summary, ""]
        if rep.findings:
            out += ["## Findings", ""]
            for f in rep.findings:
                out += [f"### {f.initiative} — {f.status}", ""]
                meta = []
                if f.aliases:
                    meta.append(f"Aliases: {', '.join(f.aliases)}")
                if f.owner_team:
                    meta.append(f"Owner: {f.owner_team}")
                if f.period:
                    meta.append(f"Period: {f.period}")
                if meta:
                    out += [" · ".join(meta), ""]
                if f.status_history:
                    hist = " → ".join(f"{h.get('status')} ({h.get('date')} [{h.get('citation')}])"
                                      for h in f.status_history)
                    out += [f"Status history: {hist}", ""]
                for c in f.claims:
                    tag = "" if c.support == "supported" else " _(partially supported)_"
                    out.append(f"- {c.text} {''.join(f'[{i}]' for i in c.citations)}{tag}")
                out.append("")
        if rep.timeline:
            out += ["## Timeline", "", "| Date | Initiative | Event | Sources |", "|---|---|---|---|"]
            for t in sorted(rep.timeline, key=lambda t: t.date):
                ev = t.event.replace("|", "\\|")
                out.append(f"| {t.date} | {t.initiative} | {ev} | {' '.join(f'[{i}]' for i in t.citations)} |")
            out.append("")
        if rep.conflicts:
            out += ["## Conflicts", ""] + [f"- **{c.initiative}:** {c.description} "
                                            f"{''.join(f'[{i}]' for i in c.citations)}" for c in rep.conflicts] + [""]
        if rep.gaps:
            out += ["## Gaps", ""] + [f"- {g}" for g in rep.gaps] + [""]
        if rep.citations:
            out += ["## Citations", ""] + [f"- **[{c.id}]** {c.title} — {c.section} ({c.doc_type}, "
                                            f"{c.effective_date}) `{c.url}`" for c in rep.citations] + [""]
    m = res.metrics
    out += ["## Run metrics", "", f"- Latency: {m.latency_ms} ms · steps {m.steps} · replans {m.replans}",
            f"- Tokens: {m.prompt_tokens} prompt + {m.completion_tokens} completion · LLM calls {m.llm_calls}",
            f"- Provider: {m.provider} ({m.model_fast} / {m.model_main})",
            f"- Claims: {m.claims_total} total, {m.claims_dropped} dropped by verifier", ""]
    return "\n".join(out)


# ---- sections -----------------------------------------------------------------------------------------------
def _findings(rep: Report) -> None:
    st.subheader(f"Findings ({len(rep.findings)})")
    if not rep.findings:
        st.caption("No initiatives matched.")
        return
    for f in rep.findings:
        with st.container(border=True):
            html_md(f"<div style='display:flex;justify-content:space-between;align-items:center;gap:8px;"
                    f"flex-wrap:wrap'><strong style='font-size:1.08rem'>{html.escape(f.initiative)}</strong>"
                    f"{initiative_status_chip(f.status)}</div>")
            meta = []
            if f.owner_team:
                meta.append(f"**Owner:** {f.owner_team}")
            if f.period:
                meta.append(f"**Period:** {f.period}")
            if f.aliases:
                meta.append("**Also known as:** " + ", ".join(f.aliases))
            if meta:
                st.markdown(" · ".join(meta))
            if f.status_history:
                parts = [f"{initiative_status_chip(h.get('status', 'unknown'))}"
                         f"<span class='ekra-muted'>{html.escape(str(h.get('date', '')))}</span>"
                         f"{cite_chips([h['citation']] if h.get('citation') else [])}"
                         for h in f.status_history]
                html_md("<div style='margin:6px 0'><span class='ekra-muted'>Status history:&nbsp;</span>"
                        + " <span class='ekra-muted'>→</span> ".join(parts) + "</div>")
            for c in f.claims:
                flag = "" if c.support == "supported" else \
                    " <span class='ekra-muted'>(partially supported)</span>"
                html_md(f"• {html.escape(c.text)}{cite_chips(c.citations)}{flag}")


def _timeline(rep: Report) -> None:
    st.subheader("Timeline")
    if not rep.timeline:
        st.caption("No dated events.")
        return
    df = pd.DataFrame([{"Date": t.date, "Initiative": t.initiative, "Event": t.event,
                        "Sources": " ".join(f"[{i}]" for i in t.citations)} for t in rep.timeline])
    df = df.sort_values("Date").reset_index(drop=True)
    st.dataframe(df, hide_index=True, width="stretch",
                 column_config={"Date": st.column_config.DateColumn(format="YYYY-MM-DD", width="small"),
                                "Event": st.column_config.TextColumn(width="large")})


def _citations(rep: Report, user_id: str) -> None:
    st.subheader(f"Citations ({len(rep.citations)})")
    if not rep.citations:
        st.caption("No citations.")
        return
    opened: dict = st.session_state.setdefault("opened_docs", {})
    for c in rep.citations:
        _citation(c, user_id, opened)


def _citation(c: Citation, user_id: str, opened: dict) -> None:
    with st.expander(f"[{c.id}]  {c.title} — {c.section}  ·  {c.doc_type} · {c.effective_date}"):
        st.caption(f"`{c.url}` · chunk `{c.chunk_id}`")
        key = (user_id, c.doc_id)
        if key not in opened:
            # open_document re-checks the ACL and writes to the audit trail, so only call it on demand.
            if st.button("Open document", key=f"open-{c.id}-{c.doc_id}"):
                with st.spinner("Checking access…"):
                    try:
                        opened[key] = research.open_document(c.doc_id, user_id)
                    except Exception as e:  # noqa: BLE001
                        st.error(f"Could not open the document ({type(e).__name__}).")
                        return
            else:
                return
        doc = opened.get(key)
        if doc is None:
            st.warning(f"🔒 You don't have access to this document as **{user_id}**.")
            return
        st.markdown(f"**{doc.title}**")
        st.caption(f"{doc.doc_type} · {doc.effective_date} · owner {doc.owner_team} · {doc.source_system}"
                   + (" · synthetic" if doc.is_synthetic else ""))
        st.text_area("Document text", doc.text, height=240, disabled=True, key=f"doc-{c.id}-{c.doc_id}",
                     label_visibility="collapsed")


def _trace(res: RunResult) -> None:
    with st.expander("How it worked — plan, tools and metrics", expanded=False):
        m = res.metrics
        c = st.columns(4)
        c[0].metric("Latency", fmt_ms(m.latency_ms))
        c[1].metric("Steps / replans", f"{m.steps} / {m.replans}")
        c[2].metric("Tokens", f"{m.prompt_tokens + m.completion_tokens:,}",
                    help=f"{m.prompt_tokens:,} prompt + {m.completion_tokens:,} completion · {m.llm_calls} LLM calls")
        c[3].metric("Claims dropped", f"{m.claims_dropped} / {m.claims_total}",
                    help="Claims removed by the grounding verifier because the cited text did not support them.")
        st.caption(f"Provider **{m.provider or '—'}** · fast model `{m.model_fast or '—'}` · main model "
                   f"`{m.model_main or '—'}` · docs retrieved {m.docs_retrieved} · docs cited {m.docs_cited} · "
                   f"config snapshot `{m.config_snapshot_id or '—'}`")
        if m.degraded:
            st.warning("Degraded mode used: " + ", ".join(m.degraded))
        if res.plan:
            df = pd.DataFrame([{"#": s.step, "Kind": s.kind, "Tool": s.tool, "Purpose": s.purpose,
                                "Status": STEP_STATUS.get(s.status, s.status), "Result": s.summary,
                                "Duration": fmt_ms(s.duration_ms)} for s in res.plan])
            st.dataframe(df, hide_index=True, width="stretch")
        else:
            st.caption("No plan steps were recorded for this run.")


def render_result(res: RunResult, viewer_id: str, key_prefix: str = "r") -> None:
    html_md(f"{run_status_chip(res.status)}<span class='ekra-muted'>run <code>{res.run_id}</code> · "
            f"asked as <b>{html.escape(res.user_id)}</b> · {html.escape(res.created_at)}</span>")
    status_banner(res.status, res.message)
    if viewer_id != res.user_id:
        st.caption(f"ℹ️ This report was produced for **{res.user_id}**. Opening citations checks access for the "
                   f"currently signed-in user (**{viewer_id}**).")
    rep = res.report
    if rep:
        st.subheader("Summary")
        st.markdown(rep.summary or "_No summary._")
        st.caption(f"Time window: {rep.time_window.label}")
        _findings(rep)
        _timeline(rep)
        if rep.conflicts:
            st.subheader(f"Conflicts ({len(rep.conflicts)})")
            for c in rep.conflicts:
                st.warning(f"**{c.initiative}:** {c.description} " + " ".join(f"`[{i}]`" for i in c.citations),
                           icon="⚠️")
        if rep.gaps:
            st.subheader(f"Gaps ({len(rep.gaps)})")
            for g in rep.gaps:
                st.info(g, icon="🕳️")
        _citations(rep, viewer_id)
    _trace(res)
    d1, d2, _ = st.columns([1, 1, 3])
    d1.download_button("⬇ Report (Markdown)", to_markdown(res), file_name=f"{res.run_id}.md",
                       mime="text/markdown", key=f"{key_prefix}-md", width="stretch")
    d2.download_button("⬇ Report (JSON)", res.model_dump_json(indent=2), file_name=f"{res.run_id}.json",
                       mime="application/json", key=f"{key_prefix}-json", width="stretch")
