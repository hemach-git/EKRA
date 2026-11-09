# EKRA: As-Built Architecture (prototype)

This document describes what was **actually built**. The production-scale target design is in [design.md](design.md). Every document, person, team, project and number in the prototype corpus is **synthetic**.

## 1. Architecture

```mermaid
flowchart LR
  UI[Streamlit UI] --> SVC[Services API]
  SVC --> GIN[Input Guardrails]
  GIN --> AG[Agent Loop]
  AG --> TL[Typed Tools]
  TL --> RET[Hybrid Retriever + ACL]
  RET --> DB[(SQLite)]
  AG --> LLM[LLM Provider]
  LLM --> OL[Ollama local]
  LLM --> MK[Mock offline]
  AG --> VER[Verifier]
  SVC --> AUD[(Audit + Run Store)]
  SVC --> LOG[JSON Logs]
  EV[Eval Runner] --> SVC
```

| Component | File | Responsibility |
|---|---|---|
| UI (separate session) | `app/main.py`, `app/pages/`, `app/ui/` | Ask, report, review, analytics, diagnostics pages |
| Services (the contract) | `app/services/*.py` | Only API the UI calls; Pydantic shapes in `app/core/models.py` |
| Input guardrails | `app/guardrails/input.py`, `pii.py` | Length/type checks, injection patterns, PII masking |
| Agent loop | `app/agent/loop.py` | Plan, act, observe, replan, synthesize, verify |
| Planner | `app/agent/planner.py`, `timewin.py` | Time window in code; LLM only proposes sub-queries |
| Budget | `app/agent/budget.py` | Step, time, token and tool-call caps; loop detection |
| Tools | `app/tools/` | `entity_lookup`, `list_documents`, `hybrid_search`, `fetch_document` with validated schemas |
| Retriever | `app/retrieval/index.py`, `acl.py` | BM25 + vectors with RRF; ACL applied before ranking |
| Synthesizer | `app/agent/synthesizer.py` | Per-initiative claim extraction, summary, conflicts |
| Verifier | `app/agent/verifier.py` | Claim-to-passage grounding; live ACL re-check |
| LLM providers | `app/llm/` | `ollama` (default, local), `mock` (offline). OpenAI is deliberately not supported |
| Store | `app/core/db.py` | SQLite, foreign keys on, CHECK constraints |

## 2. Data flow (one question)

```mermaid
flowchart TD
  Q[Question + user id] --> V[Validate and sanitize]
  V --> W[Resolve time window]
  W --> P[Plan sub-queries]
  P --> E[Entity lookup, ACL filtered]
  E --> L[List documents in window]
  L --> S[Parallel hybrid search]
  S --> O[Observe coverage]
  O -->|gap| R[Replan: fetch key documents]
  R --> O
  O --> X[Extract claims per initiative]
  X --> G[Verify grounding + live ACL]
  G --> A[Assemble cited report]
  A --> D[Persist run + audit + logs]
```

## 3. Request sequence

```mermaid
sequenceDiagram
  participant U as User
  participant S as Services
  participant G as Guardrails
  participant A as Agent
  participant T as Tools
  participant M as LLM
  participant V as Verifier
  participant D as DB
  U->>S: run_research
  S->>G: check_input
  G-->>S: ok
  S->>A: run_agent with ACL allow-list
  A->>M: plan sub-queries
  A->>T: entity_lookup, list_documents
  T-->>A: initiatives and documents
  par parallel
    A->>T: hybrid_search per query
    A->>T: hybrid_search per initiative
  end
  A->>A: observe coverage and replan
  A->>M: extract claims per initiative
  A->>V: verify claims
  V->>D: live ACL check
  V-->>A: kept and dropped claims
  A->>M: write summary
  A-->>S: report
  S->>D: persist run and audit
  S-->>U: RunResult
```

## 4. Data model

```mermaid
erDiagram
  USERS ||--o{ USER_GROUPS : has
  GROUPS ||--o{ USER_GROUPS : includes
  GROUPS ||--o{ ACL_ENTRIES : grants
  DOCUMENTS ||--o{ ACL_ENTRIES : protected_by
  DOCUMENTS ||--o{ CHUNKS : contains
  CHUNKS ||--o{ CHUNK_EMBEDDINGS : embedded_as
  ENTITIES ||--o{ ENTITY_ALIASES : known_as
  ENTITIES ||--o{ ENTITY_MENTIONS : mentioned_in
  CHUNKS ||--o{ ENTITY_MENTIONS : mentions
  USERS ||--o{ RESEARCH_RUNS : asks
  CONFIG_SNAPSHOTS ||--o{ RESEARCH_RUNS : configures
  RESEARCH_RUNS ||--o{ RUN_STEPS : executes
  RESEARCH_RUNS ||--o{ RUN_CITATIONS : cites
  DOCUMENTS ||--o{ RUN_CITATIONS : cited
  RESEARCH_RUNS ||--o{ FEEDBACK : receives
  DOCUMENTS {
    string doc_id PK
    string doc_type
    date effective_date
    datetime acl_synced_at
    bool superseded
    bool is_synthetic
  }
  CHUNKS {
    string chunk_id PK
    string doc_id FK
    string section
    bool injection_suspect
  }
  ACL_ENTRIES {
    string doc_id FK
    string group_id FK
  }
  ENTITIES {
    string entity_id PK
    string canonical_name
    string owner_team
  }
  ENTITY_MENTIONS {
    string entity_id FK
    string chunk_id FK
    string doc_id FK
  }
  RESEARCH_RUNS {
    string run_id PK
    string user_id FK
    string status
    string snapshot_id FK
    int latency_ms
    int tokens
  }
  RUN_STEPS {
    int step_id PK
    string run_id FK
    string kind
    string tool
  }
  RUN_CITATIONS {
    string run_id FK
    string citation_id
    string doc_id FK
  }
  FEEDBACK {
    string feedback_id PK
    string run_id FK
    string user_id FK
    string rating
  }
  USERS {
    string user_id PK
    string name
  }
  GROUPS {
    string group_id PK
  }
  USER_GROUPS {
    string user_id FK
    string group_id FK
  }
  CONFIG_SNAPSHOTS {
    string snapshot_id PK
  }
```

Additional tables not drawn: `audit_log` (who, what, when, model, request id), `chunk_embeddings` (cache), `entity_aliases`.

## 5. Key design decisions (with business why)

| Decision | Why it matters to the business |
|---|---|
| ACL filter applied **before** ranking, then re-checked live before delivery | Leaders can trust that restricted material never appears in a summary |
| Initiative **status derived by rules**, not by the model | Status changes are auditable; a model cannot invent "shipped" |
| Time windows resolved **in code** against each document's *effective* date | "Last 2 years" means the same thing every time, even if a 2023 doc was edited in 2025 |
| Every claim verified against its cited passage; invented numbers are dropped | Fewer wrong statements reach decision-makers |
| LLM output validated (JSON schema, retry once, rules-based fallback) | The assistant keeps working if the local model misbehaves |
| Local Ollama by default; OpenAI not supported | Company data stays on the machine; no per-query cost |
| One planner agent with parallel fan-out, not many agents | Simpler traces and fewer cascading errors |

## 6. Limitations of the prototype

- Entity tags and aliases are **seeded by hand** (a stand-in for an extraction pipeline). Initiatives that are not in the entity table cannot be summarized; the report says how many matching documents belong to initiatives outside the topic.
- Status rules cover the phrases in the synthetic corpus; real documents need broader patterns or a trained classifier.
- SQLite plus in-process vectors suit ~50 documents, not millions.
- Demo identities replace SSO. There is no real connector, no async job queue and no long-term memory.
