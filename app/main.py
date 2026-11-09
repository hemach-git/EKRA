"""EKRA Research Assistant - Streamlit entrypoint.

Run:  .venv\\Scripts\\python -m streamlit run app/main.py --server.port 8503
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:  # `streamlit run app/main.py` puts app/ (not the repo root) on sys.path
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from app.ui.common import inject_css, sidebar_user_picker  # noqa: E402

st.set_page_config(page_title="EKRA Research Assistant", page_icon="🔎", layout="wide",
                   initial_sidebar_state="expanded")
inject_css()

PAGES_DIR = Path(__file__).parent / "pages"
pages = [
    st.Page(PAGES_DIR / "home.py", title="Home", icon="🏠", default=True, url_path="home"),
    st.Page(PAGES_DIR / "ask.py", title="Ask & Report", icon="🔎", url_path="ask"),
    st.Page(PAGES_DIR / "review.py", title="Review & Feedback", icon="📝", url_path="review"),
    st.Page(PAGES_DIR / "analytics.py", title="Analytics", icon="📊", url_path="analytics"),
    st.Page(PAGES_DIR / "diagnostics.py", title="Diagnostics", icon="🩺", url_path="diagnostics"),
]
st.session_state["_pages"] = {p.url_path: p for p in pages}

nav = st.navigation(pages, position="sidebar")
st.sidebar.markdown("### 🔎 EKRA")
st.sidebar.caption("Enterprise Knowledge Research Assistant")
sidebar_user_picker()
nav.run()
