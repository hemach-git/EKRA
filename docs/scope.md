# Scope Document: EKRA Agentic AI Research Assistant

## 1. Business problem and objectives

Employees spend hours searching wikis, decks, reports and meeting notes to answer cross-cutting questions such as *"Summarize all company initiatives related to personalization and recommendation systems from the last 2 years."* Answers are slow, incomplete and often miss restricted or outdated material.

**Objective:** a research assistant that plans its own research, retrieves only what the asker may see, and returns a structured, cited report in minutes.

**Success measures:** time saved per research question, share of answers rated useful, zero permission leaks, and every claim traceable to a source.

## 2. Business requirements

| # | Requirement |
|---|---|
| R1 | Accept a natural-language question and return a structured report (summary, findings, timeline, conflicts, gaps, citations). |
| R2 | Plan research steps autonomously: resolve the time window, expand terms, find initiatives, replan when key documents are missing. |
| R3 | Retrieve only documents the signed-in user may open; deny by default when access data is missing or stale. |
| R4 | Apply time windows to the date a document's content refers to, not its edit date. |
| R5 | Cite every claim to a document the user can open; drop or flag unsupported claims; say "not found" instead of guessing. |
| R6 | Treat document text as untrusted data; ignore instructions embedded in it. |
| R7 | Show the plan, evidence, conflicts and gaps; collect feedback on answers. |
| R8 | Record an audit trail, a per-run config snapshot, structured logs and operational metrics. |
| R9 | Run locally on a local model; no data leaves the machine. |

## 3. Top 3 user journeys

1. **PM, landscape.** Asks the personalization question → sees the plan → gets a report with 9 initiatives, status history, a timeline and a conflict flagged.
2. **Engineer, prior art.** "Did we ever try two-tower retrieval for the home feed?" → short answer citing the PRD and the status of the follow-up work.
3. **Restricted user.** Asks about a confidential initiative without access → gets "no accessible sources", with no hint that it exists.

## 4. MVP scope

| In | Out |
|---|---|
| Agent loop with plan, act, observe, replan, synthesize, verify | Real connectors (Confluence, SharePoint, Jira) |
| ACL-aware hybrid retrieval (BM25 + vectors) | SSO / real identity |
| Synthetic corpus of 52 documents, 15 initiatives | Async job queue, long-running reports |
| Cited, verified reports; status history; conflicts; gaps | Long-term memory, saved or shared reports |
| Guardrails, audit, logs, feedback, KPIs, diagnostics | Write actions of any kind (the system is read-only) |
| Local Ollama and an offline mock provider | Cloud LLM providers (OpenAI intentionally excluded) |
| Golden evals and automated tests | Production scale, multi-tenant deployment |

## 5. Acceptance criteria (measured; see README for results)

| # | Criterion | Pass condition |
|---|---|---|
| A1 | Example query returns all 9 in-scope initiatives, none out of scope | Eval P01 passes |
| A2 | Permission leaks | **0** documents outside the user's allow-list retrieved or cited, across all evals |
| A3 | Citation validity | 100% of citations resolve to documents the user can open |
| A4 | Uncited claims | 0 in any report |
| A5 | Negative questions abstain | Evals N01-N06 pass |
| A6 | Injection | Input injection blocked; document injection neutralized and answer unchanged |
| A7 | Budget | A run never exceeds 12 steps, 3 replans, 3 min or the token cap |
| A8 | Automated tests | All pytest tests pass |
| A9 | Real local model run | Example query completes with status ok on `gpt-oss:20b` + `llama3:8b` |

## 6. Architecture summary

See [architecture.md](architecture.md) for the as-built diagrams and [design.md](design.md) for the production-scale design (v2.0). Its section 0.2 checks each target behaviour (plan autonomously, retrieve relevant information, synthesize, structured cited response) against the design and the prototype evidence.

## 7. Data sources

All data is synthetic. See [data_sources.md](data_sources.md).

## 8. Assumptions and limitations

- Entity tags and aliases are hand-seeded; status detection is rule-based and tuned to the synthetic corpus.
- Local model latency: about 2 minutes for the full example query on this machine.
- The mock provider's eval pass rate verifies pipeline wiring, not language-model accuracy.
- Numbers in the design document (users, cost, latency) are illustrative.
- Only list-all and single-initiative question types are built and tested. Timeline, comparison and "why" questions, reason extraction, clarifying questions and plan preview are designed but not built.
- The golden set was also used for debugging; a held-out set is needed to measure accuracy on new questions.

## 9. Governance and human review points

- **Human review:** every report has a feedback step (thumbs, reason, comment). Feedback is validated and written to the audit trail.
- **No autonomous consequential action:** the assistant is read-only; it informs people and never acts.
- **Audit trail:** who asked what, which documents were retrieved and cited, model, config snapshot id, timestamp.
- **Config registry:** every run stores a config snapshot id (config plus prompt version).
- **Access refusals** are audited and look the same as "not found".
