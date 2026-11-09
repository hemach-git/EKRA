You are building the **Streamlit frontend only** for: **EKRA Research Assistant** - an agentic AI research assistant that answers complex questions over internal company knowledge (wikis, PRDs, roadmaps, meeting notes, reports) with a visible plan, permission-aware retrieval and a fully cited report. All data is **synthetic**.

**Repo/folder:** `C:\Users\Chepuri\agentic-research-assistant`. **Branch:** same folder - touch only frontend files, **do not commit**; the main session commits. Use the venv: `.venv\Scripts\python -m streamlit ...`.

**You own:** `app/main.py`, `app/pages/*`, `app/ui/*`. **Do not edit** `app/services/*`, `app/core/*`, `app/agent/*`, `app/tools/*`, `app/retrieval/*`, `app/llm/*`, `app/guardrails/*`, `app/data/*`, `tests/*`, `evals/*`, `docs/*` (except nothing).

**Interface contract (call these, don't reimplement):** all shapes are Pydantic models in `app/core/models.py` (read it first).
```python
# app/services/research.py
list_users() -> list[User]                                   # demo identities (alice, bob, carol, dave) - "Sign in as" picker in sidebar
example_questions() -> list[str]                             # pre-fill buttons
run_research(req: ResearchRequest, on_event=None) -> RunResult   # blocking; on_event(dict) is called while it runs:
                                                             #   {"type":"step","step":{PlanStep as dict}}  -> render live plan/progress
get_run(run_id) -> RunResult | None
list_runs(limit=50, user_id=None) -> list[RunSummary]
open_document(doc_id, user_id) -> DocumentView | None        # None = user has no access -> show "You don't have access"
# app/services/feedback.py
submit_feedback(FeedbackIn) -> dict ; list_feedback(limit) -> list[dict]
# app/services/analytics.py
kpis(source=None) -> dict ; runs_over_time(source=None) -> list[dict] ; corpus_stats() -> dict ; export_runs_csv(source=None) -> str
# app/services/diagnostics.py
health() -> dict ; recent_requests(limit) -> list[dict] ; latest_eval() -> dict | None ; audit_trail(limit) -> list[dict]
```
`RunResult.status` is one of `ok | partial | abstained | blocked | error`; always show `message` when present (e.g. why a request was blocked, or "no accessible sources"). Until the real services land (the main session is replacing the stubs now; signatures will not change), the stubs in `app/services/` return canned data - build against them.

**Pages (sidebar nav via `st.navigation` or pages/):**
1. **Home** - what EKRA does in 3 lines, how it works (plan -> retrieve -> synthesize -> verify), system status from `health()` (provider, Ollama reachable, doc/chunk counts), a clear **"Synthetic data"** badge, and the 3 demo journeys as buttons that jump to Ask with the question pre-filled.
2. **Ask & Report** (core workflow) - question box + example buttons + mode (quick/deep). While running: `st.status` showing live plan steps from `on_event`. Result: status banner; **summary**; **findings** as cards (initiative, aliases, owner team, period, status chip, status history, claims each with citation chips `[c1]`); **timeline** (sorted table or chart); **conflicts** (warning callouts); **gaps** (info callouts); **citations list** where each can be opened with `open_document` in an expander (shows title, type, date, text; no-access message when None); expandable **"How it worked"** trace (plan steps with tool, status, duration) and metrics (latency, steps, replans, tokens, provider/model, claims dropped). Download report as JSON and Markdown.
3. **Review & Feedback** - recent runs (`list_runs`), pick one, thumbs up/down + reason (`wrong|outdated|missing_source|other`) + comment via `submit_feedback`; shows prior feedback. This is the human-review step (recorded in the audit trail).
4. **Analytics** - 3-5 KPI metric cards from `kpis()` (runs, success rate, avg latency, avg citations, thumbs-up rate), at least one chart (`runs_over_time`, plus corpus docs by quarter/type from `corpus_stats()`), filter by `source` (app / eval / all), CSV export button (`export_runs_csv`). Label corpus numbers "Synthetic data" and run numbers "Measured".
5. **Diagnostics** - `recent_requests` table (request_id, duration, status, tokens, provider), `health()` panel, `latest_eval()` (pass rate, ACL leaks must be 0, by category; if the provider is `mock` show a note that this checks pipeline wiring, not LLM accuracy), `audit_trail` table.

**Sidebar:** "Sign in as" user picker (stored in `st.session_state`), shows the user's role and groups. Switching users changes what the agent may see - make that obvious in the UI (e.g. a small caption "Answers only use documents this user can open").

**Quality bar:** professional enterprise look (consistent theme via `.streamlit/config.toml`, sidebar nav, cards/metrics, status chips with color + text, not color alone), clear spinners, error and empty states, success states, realistic pre-filled demo scenarios, synthetic-vs-measured labels, readable on a laptop screen. No hardcoded KPI numbers; everything comes from services.

**Rules:** use **port 8503** (the main session checked it is free; 8501 and 8502 are taken by other apps - do not use or stop them). Run `.venv\Scripts\python -m streamlit run app/main.py --server.port 8503` and verify each page loads with no exceptions before reporting done; report exactly what you verified. Never hardcode keys. If you need a service change, tell the user so they can relay it to the main session - don't edit services yourself.
