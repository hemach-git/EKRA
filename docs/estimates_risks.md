# Estimates and Risk Register

## Estimates

| Task | Owner session | Time-box (min) | Actual (min) | Status |
|---|---|---|---|---|
| Design walkthrough (6 steps) and plan | main | 15 | not timed | Done |
| Skeleton: config, models, DB, synthetic corpus, data register | main | 20 | not timed | Done |
| Retriever with ACL, tools, LLM providers | main | 25 | not timed | Done |
| Agent loop, synthesizer, verifier, research service | main | 30 | not timed | Done |
| Frontend (Streamlit pages) | frontend | 30 | Separate session | Done; checked in Chrome (all 5 routes, Ask flow, no-access flow) |
| Guardrails, audit, logging, analytics, diagnostics | main | 15 | not timed | Done |
| Tests and evals (run and verified) | main | 15 | not timed | Done |
| README, scope, risk docs, diagrams, docx, PPTX, GitHub push | main | 15 | not timed | Done |
| Design deep dive v2.0 (6-step framework, behaviour conformance check, [built] claims verified against code) | main | not time-boxed | not timed | Done (2026-11-12) |

Actual time was not tracked with a stopwatch, so it is left as "not timed" rather than guessed. Task order and status are accurate.

## Risk register

| ID | Risk | Likelihood | Impact | Mitigation | Owner | Status |
|---|---|---|---|---|---|---|
| R1 | Permission leak through a summary | L | H | ACL pre-filter, live re-check before delivery, deny by default, leak check in every eval (0 leaks in both the 30-question mock run and the 30-question real-model run) | Backend | Mitigated |
| R2 | Local model returns invalid JSON or invents facts | M | H | Schema validation, one retry, rules-based fallback, grounding check drops invented numbers and unsupported claims | Backend | Mitigated |
| R3 | Prompt injection in documents | M | H | Instruction-like text removed before prompting; read-only tools; security note shown | Backend | Mitigated |
| R4 | Local model too slow for demo | M | M | Parallel extraction, fast model for extraction, mock provider fallback, budgets | Backend | Open (measured: about 103 s per enumeration question, about 32 s per single-initiative question) |
| R5 | Low recall on initiatives missing from the entity table | M | M | Report counts unmatched documents; coverage check; roadmap item: automatic entity extraction | Backend | Open |
| R6 | Rule-based status misses phrasing in real documents | H | M | Statuses cite their source; roadmap item: trained classifier plus human review | Backend | Open |
| R7 | Synthetic corpus gives a false sense of production accuracy | M | M | Label synthetic everywhere; mock eval described as wiring check; pilot on real data before claims | Product | Open |
| R8 | Stale ACL after permission changes | L | H | Deny when ACL older than 30 days or never synced; live re-check; event-driven sync in production | Backend | Mitigated in prototype |
| R9 | Cost or runaway loops in production | L | M | Step, time, token and tool-call caps; loop detection; partial answer on cap | Backend | Mitigated |
| R10 | SQLite and in-process index do not scale | H | M | Out of scope for the prototype; managed search and Postgres in the production design | Platform | Accepted |
| R11 | 30/30 golden result overstates accuracy because the set was also used for debugging | H | M | Build a held-out set never used for fixes; online judges in production (design.md 5.4) | Quality | Open |
| R12 | Timeline, comparison and "why" questions get the list-all plan, so answers may be poorly shaped | M | M | Intent playbooks designed (design.md 2.3.6); build and add golden items per intent | Backend | Open |
| R13 | "Why was it stopped" answers lack an explicit reason | M | M | Add a cited `reason` field to extraction and the report (design.md 2.7.1, 2.8.1) | Backend | Open |
| R14 | Ambiguous questions answered without asking | M | M | Clarifying question and plan preview (design.md 2.3.1, 2.3.2); time window always shown in the report | Backend | Open |
