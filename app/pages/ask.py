"""Ask & Report: the core workflow. Live plan steps while running, then the full cited report."""
from __future__ import annotations

import queue
import threading
import time

import streamlit as st
from pydantic import ValidationError

from app.core.models import PlanStep, ResearchRequest, RunResult
from app.services import research
from app.ui.common import STEP_STATUS, current_user, examples, fmt_ms
from app.ui.report import render_result

st.title("🔎 Ask & Report")
u = current_user()
if u is None:
    st.error("No signed-in user. Pick a demo user in the sidebar.")
    st.stop()
st.caption(f"Researching as **{u.name}** · {u.role} — answers only use documents this user can open.")


def _set_q(q: str) -> None:
    st.session_state["question"] = q


st.session_state.setdefault("question", "")
st.text_area("Your question", key="question", height=90, max_chars=1000,
             placeholder="e.g. Which personalization initiatives were paused or cancelled, and why?")
try:
    ex = examples()
except Exception:  # noqa: BLE001
    ex = []
if ex:
    st.caption("Examples")
    ecols = st.columns(len(ex))
    for i, (col, q) in enumerate(zip(ecols, ex)):
        col.button(q if len(q) < 70 else q[:67] + "…", key=f"ex-{i}", help=q, on_click=_set_q, args=(q,),
                   width="stretch")

c1, c2 = st.columns([3, 1])
mode = c1.radio("Mode", ["deep", "quick"], horizontal=True, key="mode",
                format_func=lambda m: {"deep": "Deep — full plan, replans, verification",
                                       "quick": "Quick — fewer steps, faster"}[m])
go = c2.button("Run research", type="primary", width="stretch")


def _run_in_thread(req: ResearchRequest, events: "queue.Queue", box: dict) -> None:
    """run_research may emit events from worker threads; we marshal them to the script thread via a queue."""
    try:
        box["result"] = research.run_research(req, on_event=events.put)
    except Exception as e:  # noqa: BLE001
        box["error"] = f"{type(e).__name__}: {e}"


def _step_line(s: PlanStep) -> str:
    tool = f" `{s.tool}`" if s.tool else ""
    return (f"**{s.step}. {s.kind}**{tool} — {s.purpose or ''}  \n"
            f"<span class='ekra-muted'>{STEP_STATUS.get(s.status, s.status)} · {s.summary} · "
            f"{fmt_ms(s.duration_ms)}</span>")


if go:
    q = st.session_state["question"].strip()
    if not q:
        st.warning("Type a question or pick an example first.")
    else:
        try:
            req = ResearchRequest(question=q, user_id=u.user_id, mode=mode, source="app")
        except ValidationError as e:
            st.error(f"Invalid request: {e.errors()[0].get('msg', 'validation error')}")
            st.stop()
        events: queue.Queue = queue.Queue()
        box: dict = {}
        th = threading.Thread(target=_run_in_thread, args=(req, events, box), daemon=True)
        t0 = time.perf_counter()
        with st.status(f"Researching as {u.user_id} ({mode} mode)…", expanded=True) as status:
            th.start()
            n = 0
            while th.is_alive() or not events.empty():
                try:
                    ev = events.get(timeout=0.25)
                except queue.Empty:
                    status.update(label=f"Researching as {u.user_id} ({mode} mode)… {time.perf_counter() - t0:.0f}s"
                                        f" · {n} steps")
                    continue
                if ev.get("type") == "step":
                    try:
                        s = PlanStep(**ev["step"])
                    except Exception:  # noqa: BLE001
                        continue
                    n += 1
                    st.markdown(_step_line(s), unsafe_allow_html=True)
            th.join()
            res: RunResult | None = box.get("result")
            if res is None:
                status.update(label="Research failed", state="error")
                st.error("The research service raised an unexpected error. Please try again; details are in the "
                         "server log.")
            else:
                ok = res.status in ("ok", "partial")
                status.update(label=f"Done in {fmt_ms(res.metrics.latency_ms)} · {res.status} · {n} steps",
                              state="complete" if ok or res.status == "abstained" else "error", expanded=False)
                st.session_state["last_result"] = res
                st.session_state["opened_docs"] = {}

res = st.session_state.get("last_result")
if res is not None:
    st.divider()
    render_result(res, viewer_id=u.user_id, key_prefix="ask")
elif not go:
    st.info("Ask a question to generate a cited research report. Progress appears here while the agent works.")
