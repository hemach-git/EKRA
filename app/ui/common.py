"""Shared UI helpers: theme CSS, signed-in user, status chips, cached service calls.

The UI never computes business numbers itself; everything shown comes from app/services/*.
"""
from __future__ import annotations

import html
from typing import Optional

import streamlit as st

from app.core.models import User
from app.services import diagnostics, research

# ---- status vocabulary: colour AND text (never colour alone) -----------------------------------------------
RUN_STATUS = {
    "ok": ("#1E7B34", "#E6F4EA", "✔ OK"),
    "partial": ("#8A5A00", "#FFF4E0", "◐ Partial"),
    "abstained": ("#4A5568", "#EDF2F7", "∅ Abstained"),
    "blocked": ("#B42318", "#FDECEA", "⛔ Blocked"),
    "error": ("#B42318", "#FDECEA", "✖ Error"),
}
INITIATIVE_STATUS = {
    "active": ("#1F4E79", "#E3EEF9", "● Active"),
    "shipped": ("#1E7B34", "#E6F4EA", "✔ Shipped"),
    "paused": ("#8A5A00", "#FFF4E0", "❚❚ Paused"),
    "cancelled": ("#B42318", "#FDECEA", "✖ Cancelled"),
    "unknown": ("#4A5568", "#EDF2F7", "? Unknown"),
}
STEP_STATUS = {"ok": "✔ ok", "empty": "∅ empty", "error": "✖ error", "skipped": "↷ skipped"}

_CSS = """
<style>
.ekra-chip{display:inline-block;padding:2px 10px;border-radius:999px;font-size:0.78rem;font-weight:600;
  border:1px solid currentColor;margin-right:6px;white-space:nowrap;line-height:1.5}
.ekra-cite{display:inline-block;padding:0 6px;margin-left:3px;border-radius:6px;font-size:0.72rem;font-weight:600;
  background:#E3EEF9;color:#1F4E79;border:1px solid #B8D0EA;font-family:ui-monospace,monospace}
.ekra-badge{display:inline-block;padding:2px 10px;border-radius:6px;font-size:0.75rem;font-weight:700;
  letter-spacing:.02em;text-transform:uppercase}
.ekra-synth{background:#FFF4E0;color:#8A5A00;border:1px solid #F0C36D}
.ekra-measured{background:#E6F4EA;color:#1E7B34;border:1px solid #9BD3AA}
.ekra-muted{color:#5B6675;font-size:0.85rem}
.ekra-hero h1{margin-bottom:0}
div[data-testid="stMetric"]{background:#F3F6FA;border:1px solid #E1E7EF;border-radius:10px;padding:10px 14px}
</style>
"""


def inject_css() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


def chip(fg: str, bg: str, label: str) -> str:
    return f'<span class="ekra-chip" style="color:{fg};background:{bg}">{html.escape(label)}</span>'


def run_status_chip(status: str) -> str:
    return chip(*RUN_STATUS.get(status, RUN_STATUS["error"]))


def initiative_status_chip(status: str) -> str:
    return chip(*INITIATIVE_STATUS.get(status, INITIATIVE_STATUS["unknown"]))


def cite_chips(ids: list[str]) -> str:
    return "".join(f'<span class="ekra-cite">[{html.escape(i)}]</span>' for i in ids)


def badge(kind: str) -> str:
    """kind = 'synthetic' | 'measured'."""
    if kind == "synthetic":
        return '<span class="ekra-badge ekra-synth">Synthetic data</span>'
    return '<span class="ekra-badge ekra-measured">Measured</span>'


def html_md(s: str) -> None:
    st.markdown(s, unsafe_allow_html=True)


def status_banner(status: str, message: str = "") -> None:
    """Status banner for a run. Always shows the service's message when present."""
    label = RUN_STATUS.get(status, RUN_STATUS["error"])[2]
    text = f"**{label}**" + (f" — {message}" if message else "")
    {"ok": st.success, "partial": st.warning, "abstained": st.info,
     "blocked": st.error, "error": st.error}.get(status, st.error)(text)


def fmt_ms(ms: Optional[float]) -> str:
    if ms is None:
        return "—"
    return f"{ms / 1000:.1f} s" if ms >= 1000 else f"{ms:.0f} ms"


def fmt_pct(x: Optional[float]) -> str:
    return "—" if x is None else f"{x * 100:.0f}%"


# ---- cached service reads (short TTL; these never mutate state) --------------------------------------------
@st.cache_data(ttl=300, show_spinner=False)
def users() -> list[User]:
    return research.list_users()


@st.cache_data(ttl=300, show_spinner=False)
def examples() -> list[str]:
    return research.example_questions()


@st.cache_data(ttl=20, show_spinner=False)
def health() -> dict:
    return diagnostics.health()


# ---- signed-in user -----------------------------------------------------------------------------------------
def current_user() -> Optional[User]:
    uid = st.session_state.get("user_id")
    return next((u for u in users() if u.user_id == uid), None)


def sidebar_user_picker() -> None:
    try:
        us = users()
    except Exception as e:  # noqa: BLE001
        st.sidebar.error(f"Could not load users: {type(e).__name__}")
        return
    if not us:
        st.sidebar.warning("No demo users found.")
        return
    ids = [u.user_id for u in us]
    if st.session_state.get("user_id") not in ids:
        st.session_state["user_id"] = ids[0]
    by_id = {u.user_id: u for u in us}
    st.sidebar.markdown("#### Sign in as")
    st.sidebar.selectbox("Demo user", ids, key="user_id", label_visibility="collapsed",
                         format_func=lambda i: f"{by_id[i].name} ({i})")
    u = by_id[st.session_state["user_id"]]
    st.sidebar.markdown(f"**{html.escape(u.role)}**")
    st.sidebar.markdown(" ".join(f"`{g}`" for g in u.groups) or "_no groups_")
    st.sidebar.caption("🔒 Answers only use documents this user can open. Switch users to see how access changes "
                       "the evidence.")
    st.sidebar.divider()
    st.sidebar.markdown(f'<div style="margin-top:4px">{badge("synthetic")}</div>', unsafe_allow_html=True)
    st.sidebar.caption("All documents, people and projects are fictional.")
