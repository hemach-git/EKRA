"""Review & Feedback: the human-review step. Ratings are stored and written to the audit trail."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from app.core.models import FeedbackIn
from app.services import feedback, research
from app.ui.common import RUN_STATUS, current_user, fmt_ms
from app.ui.report import render_result

st.title("📝 Review & Feedback")
st.caption("Human review: rate reports and flag problems. Every rating is recorded in the audit trail.")
u = current_user()
if u is None:
    st.error("No signed-in user. Pick a demo user in the sidebar.")
    st.stop()

f1, f2 = st.columns([2, 1])
mine = f1.toggle(f"Only runs by {u.user_id}", value=False)
src = f2.selectbox("Source", ["app", "all", "eval"], index=0)
try:
    runs = research.list_runs(limit=100, user_id=u.user_id if mine else None)
except Exception as e:  # noqa: BLE001
    st.error(f"Could not load runs ({type(e).__name__}).")
    st.stop()
if src != "all":
    runs = [r for r in runs if r.source == src]
if not runs:
    st.info("No runs yet. Run a question on **Ask & Report** first.")
    st.stop()

df = pd.DataFrame([{"Created": r.created_at, "User": r.user_id, "Status": RUN_STATUS.get(r.status, ("", "", r.status))[2],
                    "Question": r.question, "Findings": r.n_findings, "Citations": r.n_citations,
                    "Latency": fmt_ms(r.latency_ms), "Source": r.source, "Run": r.run_id} for r in runs])
st.markdown(f"**Recent runs** ({len(runs)}) — select a row to review")
sel = st.dataframe(df, hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row",
                   height=260, key="runs_table", column_config={"Question": st.column_config.TextColumn(width="large")})
rows = sel.selection.rows if sel and sel.selection else []
run_id = runs[rows[0]].run_id if rows else runs[0].run_id
if not rows:
    st.caption("Showing the most recent run. Select a row above to review another one.")

res = research.get_run(run_id)
if res is None:
    st.warning("That run could not be loaded.")
    st.stop()

left, right = st.columns([3, 2], gap="large")
with right:
    with st.container(border=True):
        st.markdown(f"#### Rate this report\nAs **{u.name}** · run `{run_id}`")
        with st.form(f"fb-{run_id}", clear_on_submit=True):
            rating = st.radio("Rating", ["up", "down"], horizontal=True,
                              format_func=lambda r: "👍 Helpful" if r == "up" else "👎 Not helpful")
            reason = st.selectbox("Reason (for 👎)", ["—", "wrong", "outdated", "missing_source", "other"],
                                  format_func=lambda r: {"—": "—", "wrong": "Wrong information",
                                                         "outdated": "Outdated", "missing_source": "Missing a source",
                                                         "other": "Other"}[r])
            n_claims = sum(len(f.claims) for f in res.report.findings) if res.report else 0
            claim_idx = st.number_input("Flag a specific claim # (optional, 0 = none)", min_value=0,
                                        max_value=max(n_claims, 0), value=0, step=1,
                                        help="Claims are numbered in report order, starting at 1.")
            comment = st.text_area("Comment", max_chars=500, placeholder="What should a reviewer know?")
            if st.form_submit_button("Submit feedback", type="primary"):
                if rating == "down" and reason == "—":
                    st.warning("Please pick a reason for a 👎 rating.")
                else:
                    try:
                        out = feedback.submit_feedback(FeedbackIn(
                            run_id=run_id, user_id=u.user_id, rating=rating,
                            reason=None if reason == "—" else reason, comment=comment,
                            claim_index=int(claim_idx) - 1 if claim_idx else None))
                    except Exception as e:  # noqa: BLE001
                        out = {"ok": False, "error": type(e).__name__}
                    if out.get("ok"):
                        st.success(f"Thanks — feedback `{out.get('feedback_id')}` recorded and audited.")
                    else:
                        st.error(f"Feedback not saved: {out.get('error', 'unknown error')}")

    st.markdown("#### Prior feedback on this run")
    try:
        prior = [f for f in feedback.list_feedback(500) if f.get("run_id") == run_id]
    except Exception as e:  # noqa: BLE001
        prior = []
        st.error(f"Could not load feedback ({type(e).__name__}).")
    if prior:
        st.dataframe(pd.DataFrame([{"When": f.get("created_at"), "User": f.get("user_id"),
                                    "Rating": "👍 up" if f.get("rating") == "up" else "👎 down",
                                    "Reason": f.get("reason") or "", "Claim": f.get("claim_index"),
                                    "Comment": f.get("comment") or ""} for f in prior]),
                     hide_index=True, width="stretch")
    else:
        st.caption("No feedback yet for this run.")

with left:
    render_result(res, viewer_id=u.user_id, key_prefix="rev")
