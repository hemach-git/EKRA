# Agentic AI Research Assistant: Enterprise System Design

**Mode:** design only. **Author:** Hema Chepuri. **Date:** 2026-11-08.
**Running example:** *"Summarize all company initiatives related to personalization and recommendation systems from the last 2 years."* This resolves to the window **2024-11-08 → 2026-11-08**.

**How this maps to the required submission:**

| Required item | Section |
|---|---|
| Architecture diagram | 2.1 (plus sequence, data-flow and ER diagrams in 2.4–2.5) |
| Written system design document | 1–2 |
| Trade-off analysis | 3 |
| Failure mode analysis | 4 |
| Production operations discussion | 5–6 |

---

## 1. Requirements

### 1.1 Clarifying questions (with the answers assumed)

| Question | Assumed answer |
|---|---|
| Who are the users? | Product managers, engineers, strategy and leadership staff, and new hires. All are employees signed in through SSO. |
| What decisions does it support? | Planning, avoiding duplicate work, finding prior art, briefing leadership. It informs people and never acts for them. |
| Which sources? | Confluence/wiki, SharePoint/Drive, Jira/epics, meeting transcripts and notes, project reports, PRDs/specs, roadmap decks. |
| Compliance? | Strict document-level permissions; PII and HR/legal content restricted; data residency; audit logs. |
| Write actions? | None in v0. The system is read-only. |

### 1.2 Functional requirements
- **FR1** Natural-language questions, including multi-hop, time-bounded and enumeration questions ("all initiatives…").
- **FR2** The system plans its research on its own: it breaks the question into sub-queries, chooses tools, and replans when it finds gaps.
- **FR3** It retrieves across all connected sources, limited to what the asking user is allowed to see.
- **FR4** It synthesizes a structured answer: summary → findings (deduplicated by initiative) → timeline → conflicts → gaps, with every claim cited to an openable source (doc, section, date).
- **FR5** It asks a clarifying question when the request is ambiguous (calendar or fiscal year? which business units?).
- **FR6** Two modes: Quick answer (synchronous, streamed) and Deep research report (asynchronous, with progress updates and an exportable report).
- **FR7** Feedback on the whole answer and on individual claims (wrong, outdated, missing source).
- **FR8** Session follow-ups ("drill into the 2025 ones") and optional saved reports.

### 1.3 Non-functional requirements (all numbers illustrative)

| Dimension | Target |
|---|---|
| Scale | 20k employees; 2k daily users; about 6k queries/day; peak 15 QPS |
| Corpus | About 5M documents, about 60M chunks, about 50k changed docs/day |
| Latency | Quick answer: first token under 3 s, p95 under 20 s. Deep report: p95 under 4 min |
| Freshness | Content indexed within 15 min (event-driven); ACL changes applied within 5 min, deny by default if stale |
| Availability | 99.5% for the answer path; degrade to search-only if LLMs are down |
| Quality | Faithfulness ≥ 95%; citation validity ≥ 98%; permission-leak rate = 0; enumeration recall ≥ 85% |
| Cost | About $0.05 per quick answer, about $0.60 per deep report; blended about $0.13 per query |
| Security | SSO (OIDC/SAML); encrypted at rest and in transit; zero-retention LLM contracts; full audit trail |

### 1.4 What "done" means and success KPIs
- **Done:** a correct, grounded answer that the user is allowed to see, where every claim links to a source they can open, delivered within the latency target.
- **Business KPIs:** research time saved per query, weekly active users, the share of answers rated useful, and fewer duplicate initiatives found in planning reviews.

### 1.5 Never list (hard rules)
1. NEVER retrieve, quote or cite a document the user can't open.
2. NEVER state a claim that isn't grounded in a retrieved passage. Say "not found" instead.
3. NEVER follow instructions found inside retrieved content.
4. NEVER take a write or side-effect action without a human.
5. NEVER let long-term memory override what the source documents say.

### 1.6 Top user journeys
1. **PM, landscape question:** asks the example query → reviews the plan preview → gets a deep report with a timeline of initiatives → exports it to the planning doc.
2. **Engineer, prior art:** "Did we ever try two-tower retrieval for the home feed?" → quick answer with 3 cited sources and an owner team to contact.
3. **Leader, follow-up:** "Which of those were shut down and why?" → the session context carries over → the answer cites post-mortems and flags conflicting statuses.

---

## 2. Main System Components

### 2.1 Architecture diagram

```mermaid
flowchart TB
  subgraph Clients
    UI[Web App]
    BOT[Slack/Teams Bot]
    API[Public API]
  end
  subgraph Edge
    GW[Gateway + SSO]
    IDN[Identity Resolver]
    GIN[Input Guardrails]
  end
  subgraph Agent[Agent Runtime]
    QU[Query Understanding]
    PL[Planner Loop]
    BC[Budget Controller]
    EX[Tool Executor]
    SY[Synthesizer]
    VF[Verifier]
    WM[(Working Memory)]
  end
  subgraph Tools[Read-only Tools]
    T1[hybrid_search]
    T2[list_documents]
    T3[fetch_document]
    T4[entity_lookup]
  end
  subgraph Retrieval
    IDX[(Hybrid Index + ACL)]
    RR[Reranker + MMR]
    KG[(Entity Store)]
  end
  subgraph Ingestion
    CON[Connectors]
    ACL[ACL Sync]
    PAR[Parse + Dedupe]
    ENR[Enrich + Entities]
    CHK[Chunk + Embed]
  end
  subgraph Platform
    LLMGW[LLM Gateway]
    JOBQ[Job Queue]
    LTM[(Long-term Memory)]
    META[(Runs + Audit DB)]
    OBS[Observability + Evals]
  end
  Clients --> Edge
  GW --> IDN --> GIN --> QU --> PL
  PL <--> BC
  PL --> EX --> Tools
  EX --> WM
  Tools --> Retrieval
  PL --> SY --> VF
  CON --> PAR --> ENR --> CHK --> IDX
  ENR --> KG
  CON --> ACL --> IDX
  Agent --> Platform
```

### 2.2 Components and why each exists

| Component | Responsibility | Business why |
|---|---|---|
| Gateway, SSO and identity resolver | Authenticates the user and expands them into ACL principals (user ID plus group IDs), cached for 5 min | Every request carries identity, which makes leak-free answers possible and keeps security sign-off simple |
| Input guardrails | Length and type limits, prompt-injection heuristics plus a classifier, PII detection, restricted policy topics | Blocks misuse before any money is spent |
| Query understanding | Classifies intent (lookup / enumeration / comparison / timeline), resolves relative dates to absolute ones, extracts entities, decides quick vs deep, asks a clarifying question when confidence is low | Avoids confidently answering the wrong question |
| Planner (single agent) | Produces an upfront plan (sub-queries, tools, stop criteria), then runs Plan → Act → Observe with bounded replanning | Gives autonomy that can still be audited; the user can preview the plan |
| Tool executor | Runs typed, read-only tools in parallel with timeouts, retries and schema validation. Errors go back to the planner as observations | Most agents break at the tool boundary, so it is hardened here |
| Budget and loop controller | Caps steps (12), replans (3), tokens, dollars and wall-clock time; detects repeated identical calls | Predictable cost and latency |
| Synthesizer | Map: pulls structured records out of each evidence chunk. Reduce: resolves entities, orders the timeline, writes sections | Answers "all X" questions with full coverage, not just the top 5 chunks |
| Verifier | Checks every claim against its cited passage, checks that citations resolve and that the user can access them, drops or flags unsupported claims | Builds trust: no uncited claims ship |
| Retrieval layer | Query rewrite and synonyms → hybrid BM25 + vector with ACL pre-filter → cross-encoder rerank → MMR diversity → recency/authority boost | Internal jargon needs keyword search; paraphrases need vectors |
| Entity store | Initiatives, projects, teams and products with aliases ("RecSys v2" = "Project Compass"), built at ingestion | Makes enumeration and deduplication reliable |
| Ingestion pipeline | Connectors (webhook/CDC plus nightly reconciliation), parsing, minhash deduplication, metadata enrichment (doc type, effective date, owner, status), structure-aware chunking, embeddings | Messy sources become citable, time-aware evidence |
| LLM gateway | Model routing (small model for classify/extract, large for plan/synthesize), prompt caching, rate limits, provider failover, PII redaction in logs | Controls cost and availability; prompts and models are config |
| Memory | Working: per-run plan, evidence and scratchpad. Long-term: opt-in preferences and saved reports, with TTL and delete | Supports follow-ups without stale facts leaking in |
| Job queue | Deep research runs asynchronously with progress events (SSE) | Long reports don't time out chat clients |
| Observability and eval | OTel spans for every step, tool and LLM call; offline and online evals; feedback store | You can't debug reasoning you didn't trace |

### 2.3 Retrieval and memory deep dive

**Grounding over messy internal knowledge**
- Parsing is aware of each format: slide decks keep slide titles, transcripts are split by speaker turn and agenda item, Jira keeps epic → story links.
- Chunking follows the document's own structure: headings, sections or slides, about 300–800 tokens each, with the parent heading path prepended.
- Every chunk stores `doc_id, url, section_path, char_offsets, effective_date, doc_type, version, acl_principals[]`, so it can always be cited.
- **Effective date ≠ modified date.** At ingestion, a small model extracts the date the content refers to (e.g. an H1 2025 roadmap edited in 2026). Time filters use the effective date.
- Authority and freshness signals: docs marked superseded or archived are down-ranked, and the latest version of a page wins.

**Permission-aware retrieval**
- ACLs are synced from each source and stored on every chunk.
- Every search applies `acl_principals ∩ user_principals ≠ ∅` as a pre-filter inside the index query, never as a post-filter only.
- Second check before delivery: the verifier re-checks access for each cited doc with a live source-system call or a fresh ACL cache entry.
- Deny by default when `acl_synced_at` is older than its SLA or the ACL is missing.
- Each run logs which doc IDs were retrieved for which user, so access can be audited.

**Tool contracts** (JSON schema, read-only, bounded outputs)

```json
{ "name": "hybrid_search",
  "args": { "query": "string(<=256)",
            "filters": { "doc_type": ["roadmap","prd","report","meeting","wiki"],
                         "effective_date_from": "date", "effective_date_to": "date",
                         "entity_ids": ["string"] },
            "top_k": "int(1..50)" },
  "returns": [{ "chunk_id": "str", "doc_id": "str", "title": "str", "snippet": "str(<=1200)",
                "effective_date": "date", "score": "float", "url": "str" }] }
```

- Other tools: `list_documents` (metadata-only scan for recall), `fetch_document(doc_id, sections)`, `entity_lookup(name|alias)`, `org_directory(team)`.
- Failure handling: timeouts of 2–5 s, 2 retries with jittered backoff, and circuit breakers for each connector.
- An empty result or error comes back as `{"status": "error|empty", "hint": ...}`, so the planner can widen the query or switch tools instead of crashing.

**Memory**
- **Short-term:** the per-run evidence ledger (`chunk_id → extracted facts`), held to a token budget. Raw chunks are replaced by extracted facts once the map step has processed them. It is discarded when the run ends; only the final report and trace persist.
- **Long-term:** opt-in. It holds preferences and saved reports. TTL is 180 days, users can view and delete it, and it is never used as evidence. Saved reports are re-validated against ACLs when reopened.

**Synthesis output schema**

```json
{ "summary": "string",
  "time_window": {"from": "2024-11-08", "to": "2026-11-08"},
  "findings": [{ "initiative": "string", "aliases": ["string"], "owner_team": "string",
                 "period": "string", "status": "active|shipped|paused|cancelled|unknown",
                 "claims": [{ "text": "string", "citations": ["c1","c4"], "support": "supported|partial" }] }],
  "timeline": [{ "date": "date", "event": "string", "citations": ["c2"] }],
  "conflicts": [{ "description": "string", "citations": ["c3","c7"] }],
  "gaps": ["string"],
  "citations": [{ "id": "c1", "doc_title": "string", "url": "string", "section": "string", "effective_date": "date" }] }
```

### 2.4 The example query, traced end to end

```mermaid
sequenceDiagram
  participant U as User
  participant G as Gateway
  participant Q as QueryUnderstanding
  participant P as Planner
  participant T as Tools
  participant S as Synthesizer
  participant V as Verifier
  U->>G: Summarize recsys initiatives, last 2 yrs
  G->>Q: query + principals
  Q->>Q: enumeration, window 2024-11-08 to 2026-11-08, deep
  Q->>P: structured task
  P->>U: plan preview, async job started
  par ACL pre-filtered fan-out
    P->>T: entity_lookup personalization, recsys
    P->>T: hybrid_search synonyms x doc types
    P->>T: list_documents entities + window
  end
  T-->>P: 140 chunks from 62 docs
  P->>P: gap found - no H2 2025 reports
  P->>T: replan - targeted meeting-notes search
  T-->>P: 18 more chunks
  P->>S: evidence ledger, reranked and trimmed
  S->>S: map - extract initiative records
  S->>S: reduce - 9 initiatives, timeline, conflicts
  S->>V: draft with claim-citation links
  V->>V: grounding, citation and live ACL checks
  V-->>U: report - 9 initiatives, 41 citations, 2 conflicts, 1 gap
```

1. **Plan.** Expand synonyms (personalization, recommendations, recsys, "for you", ranking, next-best-action, user embeddings). Target roadmaps, PRDs, project reports and meeting notes, filtered by effective date.
2. **Act.** Run entity lookup, hybrid search and a metadata scan in parallel, all pre-filtered by ACL.
3. **Observe and replan.** The coverage check (per quarter × source type) finds the hole in H2 2025 and runs a targeted query.
4. **Synthesize.** Map-reduce extraction; entity resolution merges "Project Compass" and "RecSys v2"; build the timeline.
5. **Cite and deliver.** Every claim links to a doc/section the user can open. Conflicts are shown (e.g. a roadmap says "shipped Q2" but the report says "paused"). Gaps are stated.

### 2.5 Data flow and data model

```mermaid
flowchart LR
  SRC[Source Systems] --> RAW[(Raw Store)]
  RAW --> PARSE[Parse + Dedupe]
  PARSE --> ENRICH[Enrich + Entities]
  ENRICH --> CHUNK[Chunk + Embed]
  CHUNK --> IDX[(Hybrid Index)]
  ENRICH --> KG[(Entity Store)]
  SRC --> ACLS[ACL Sync]
  ACLS --> IDX
  IDX --> AGENT[Agent Runtime]
  KG --> AGENT
  AGENT --> RUNS[(Runs + Audit)]
  FB[User Feedback] --> RUNS
  RUNS --> EVAL[Evals + Dashboards]
```

```mermaid
erDiagram
  DOCUMENT ||--o{ CHUNK : contains
  DOCUMENT ||--o{ ACL_ENTRY : protected_by
  PRINCIPAL ||--o{ ACL_ENTRY : granted
  ENTITY ||--o{ ENTITY_MENTION : mentioned_in
  CHUNK ||--o{ ENTITY_MENTION : has
  RESEARCH_RUN ||--o{ RUN_STEP : executes
  RESEARCH_RUN ||--o{ CLAIM : produces
  CLAIM ||--o{ CITATION : supported_by
  CHUNK ||--o{ CITATION : cited
  RESEARCH_RUN ||--o{ FEEDBACK : receives
  DOCUMENT {
    string doc_id PK
    string source_system
    string url
    string doc_type
    date effective_date
    datetime modified_at
    string version
    datetime acl_synced_at
  }
  CHUNK {
    string chunk_id PK
    string doc_id FK
    string section_path
    int char_start
    int char_end
  }
  ACL_ENTRY {
    string doc_id FK
    string principal_id FK
    string permission
  }
  PRINCIPAL {
    string principal_id PK
    string type
  }
  ENTITY {
    string entity_id PK
    string type
    string canonical_name
  }
  ENTITY_MENTION {
    string entity_id FK
    string chunk_id FK
    float confidence
  }
  RESEARCH_RUN {
    string run_id PK
    string user_id
    string status
    string config_snapshot_id
    float cost_usd
  }
  RUN_STEP {
    string step_id PK
    string run_id FK
    string tool
    string status
  }
  CLAIM {
    string claim_id PK
    string run_id FK
    string support
  }
  CITATION {
    string citation_id PK
    string claim_id FK
    string chunk_id FK
  }
  FEEDBACK {
    string feedback_id PK
    string run_id FK
    string rating
  }
```

---

## 3. Trade-off Analysis

### 3.1 Trade-offs ledger

| Tension | We lean | We gave up | Why it's right here |
|---|---|---|---|
| Planning: upfront plan vs purely reactive (ReAct) | Plan first, then bounded replanning | Some flexibility on odd queries | The user can preview the plan, cost is predictable, the plan is auditable; replanning still closes gaps |
| Orchestration: single vs multi-agent | Single planner + deterministic parallel workers | Specialist agents with separate personas | Fewer handoffs, fewer cascading errors, simpler traces, lower cost |
| Retrieval: vector only vs hybrid | Hybrid BM25 + vector + reranker, plus entity index and metadata scan | Simplicity; about 100 ms extra latency | Internal code names break pure embeddings; enumeration needs recall beyond top-k |
| Recall vs latency (enumeration) | Map-reduce over many candidates in deep mode | Speed: deep reports take minutes | Missing an initiative is worse than waiting 3 minutes |
| Freshness: index vs live query | Indexed (event-driven, 15 min SLA) with live fetch for final verification | Real-time content | Live querying of 6 source APIs is slow and rate-limited |
| Grounding: strict citation vs fluency | Strict: unsupported claims are dropped or flagged | Some smoothness and inferred insight | Leaders act on these reports; a wrong uncited claim costs more trust than a terse answer |
| Permissions: pre-filter vs post-filter | Pre-filter in the index + re-check before delivery | Index complexity; ACL sync infrastructure | A post-filter alone leaks through the summaries the LLM writes; leak rate must be 0 |
| Cost: one big model vs routing and caching | Routing: small model for classify/extract/verify, large for plan/synthesize; caching | Some peak quality on extraction | Extraction is about 70% of tokens; routing cuts cost about 3–4× |
| Interaction: sync chat vs async jobs | Both: quick mode streams, deep mode runs async | Simplicity of a single path | Matches the job: a quick lookup vs a landscape report |
| Build vs buy | Managed search + LLM via a multi-provider gateway | Fine-grained control | Faster time to value; provider choice stays open |
| Long-term memory | Opt-in, preferences only, never evidence | Personalization depth | Avoids stale or poisoned facts; simpler privacy review |

### 3.2 Key decisions in more depth
- **Why not plain RAG?** Top-k retrieval answers "what is X" well but fails at "summarize all X over 2 years". That needs decomposition, coverage checks, cross-document deduplication and time ordering. Those are the steps that justify an agent.
- **Why an entity store?** The same initiative appears under 3–4 names across decks, Jira and meeting notes. Without canonical entities, the report double-counts or splits initiatives.
- **Why a live ACL check before delivery?** The index ACL can lag by up to 5 min. Checking the 20–50 cited docs live costs little and closes the lag window for the documents that actually reach the user.

---

## 4. Failure Mode Analysis

### 4.1 Agentic failure modes

| # | Failure mode | Symptom | Detection | Mitigation |
|---|---|---|---|---|
| 1 | Infinite or long loops | Repeated near-identical searches; latency blows up | Step counter; hash of (tool, args) repeated | Caps: 12 steps, 3 replans, 4 min; dedupe calls; graceful partial answer listing what wasn't covered |
| 2 | Plan derailment | Drifts to general "ML infrastructure" | Each step scored for relevance against the goal | Goal re-statement each planner turn; prune off-topic steps; cap replans |
| 3 | Context overflow | Truncated evidence, lost citations | Token budget monitor | Map step compresses chunks into facts; rerank and trim; hierarchical reduce |
| 4 | Cascading errors | Bad tool output poisons synthesis | Schema validation fails; empty results | Validate every output; retry/fallback; fail closed for ACL errors |
| 5 | Confident hallucination | Fluent claims with no or wrong citation | Verifier grounding score; citation-span match | Claim → passage entailment check; drop or flag; "not found" is a valid answer |
| 6 | Cost runaway | $/request spikes | Per-run cost meter; spend alerts | Per-request token and $ caps; model routing; caching; deep mode only on explicit intent |

### 4.2 Enterprise and RAG-specific failure modes

| # | Failure mode | Impact | Mitigation |
|---|---|---|---|
| 7 | Permission leak (stale or missing ACL) | Severe: security incident | Pre-filter + deny-by-default + live re-check + audit; leak canary tests in CI and production |
| 8 | Prompt injection in documents | Data exfiltration, wrong answers | Retrieved text delimited as untrusted data; read-only tools; injection classifier; no outbound actions |
| 9 | Stale or superseded content | Wrong decisions | Effective date + version + superseded signals; dates on every citation; conflicts flagged |
| 10 | Low recall on enumeration | Missing initiatives | Synonym expansion, entity index, metadata scan, coverage grid; report states the searched scope |
| 11 | Entity confusion (two projects named "Atlas") | Merged or misattributed findings | Resolution uses owner team + dates + context; low-confidence merges flagged |
| 12 | Time misattribution | Out-of-window results | Effective-date extraction; filter on events, not edit timestamps |
| 13 | Noisy meeting transcripts | Overstated claims | Source-type weighting; hedged language for meeting-only claims |
| 14 | Connector or source outage | Partial coverage | Circuit breakers; answer notes which source was unavailable |
| 15 | LLM provider outage or rate limit | Downtime | Gateway failover; queue deep jobs; degrade to cited search results |
| 16 | Embedding model change | Index inconsistency | Versioned indexes; blue/green reindex; never mix embedding versions |
| 17 | PII exposure in answers or logs | Compliance breach | Output PII detection; log/trace redaction; restricted collections excluded by policy |

**Human-in-the-loop points:** confirming the plan for expensive deep runs; low-confidence entity merges; saving a report to a shared space; any future write tool (always requires approval).

---

## 5. Observability & Feedback Loops

### 5.1 Tracing (OpenTelemetry)
- **One trace per run**, with spans for query understanding → each plan step → each tool call → each LLM call → verifier.
- **Captured per span:** inputs/outputs (PII-redacted, stored by reference), tokens, model, latency, status, retrieved doc IDs and scores, prompt and config version.
- **Correlation:** `request_id` / `run_id` flows from the UI through connectors and into the audit log.

### 5.2 Metrics at each level

| Level | Metrics |
|---|---|
| Request | p50/p95 latency (TTFT and total), success/error rate, $/request, tokens, abstain rate, partial-answer rate |
| Step | Tool error/timeout rate per tool, replans per run, steps per run, cache hit rate, retrieval empty rate |
| Quality | Faithfulness, citation validity, ACL-leak canary (must be 0), judge scores on sampled traffic |
| Data | Ingestion lag, ACL sync lag, connector health, % docs with an effective date, index drift |
| Business | WAU, queries per user, thumbs-up rate, reports exported, estimated time saved, top unanswered topics |

### 5.3 Evaluation
- **Golden set (offline, about 300 items, growing):**
  - Positive: single-hop, multi-hop, enumeration with a known complete list, timeline questions.
  - Negative: the answer doesn't exist, so the system should abstain.
  - Edge: ambiguous time ranges, aliases, conflicting sources, injection-laced docs.
  - ACL tests: user A must not see doc X.
- **Metrics:** answer correctness, faithfulness, citation validity, enumeration recall/precision, ACL-leak rate, tool-call success, cost and latency.
- **LLM-as-judge with known biases:** position bias (randomize order), verbosity bias (length-normalize the rubric), self-preference (use a different model family as judge). Calibrate against about 100 human-labelled items; target judge-human agreement κ ≥ 0.7.
- **Offline vs online:**
  - Offline gates releases (prompt, model, retriever changes) in CI.
  - Online runs judges on about 5% of production traffic, plus canary leak probes and drift detection.

### 5.4 Feedback loops

```mermaid
flowchart LR
  A[User Feedback] --> B[Triage Queue]
  B --> C[Golden Set]
  B --> D[Retrieval Tuning]
  B --> E[Content Owner Alerts]
  B --> F[Prompt Fixes]
  C --> G[CI Eval Gate]
  D --> G
  F --> G
  G --> H[Release]
  H --> I[Online Evals]
  I --> B
```

- **Quality loop:** flagged claims become golden items and reranker hard negatives.
- **Content loop:** repeated "outdated" flags on a doc notify its owner, so the knowledge base improves too.
- **Coverage loop:** clusters of "not found" and low-recall queries reveal missing connectors or alias gaps.

---

## 6. Productionization & Operations

### 6.1 Deployment and runtime
- **Services:** stateless agent workers on Kubernetes (autoscaled on queue depth and CPU); separate ingestion workers; managed search cluster; Postgres for metadata, runs and audit; Redis for cache and sessions; object store for raw docs.
- **Invocation:** quick mode streams over SSE. Deep mode is an async job with progress events, a cancel button and a notification when done.
- **Where it breaks first** (in order) and the response to each:
  1. LLM rate limits → gateway quotas, priority queues, multi-provider.
  2. Reranker latency → GPU pool, cap candidates at 100.
  3. ACL sync lag at large orgs → incremental events plus deny-by-default.
  4. Context window on huge enumerations → hierarchical reduce.

### 6.2 SLOs, alerts and on-call

| SLO | Alert |
|---|---|
| Answer-path availability 99.5% | Error rate > 2% for 5 min |
| Quick p95 < 20 s; deep p95 < 4 min | p95 breach for 15 min |
| ACL leak = 0 | Any canary hit → page immediately, auto-disable the affected source |
| Ingestion lag < 15 min; ACL lag < 5 min | Lag breach per connector |
| Cost ≤ budget | Daily spend > 120% of forecast; per-user anomaly |
| Faithfulness ≥ 95% (online sample) | 24 h rolling drop > 3 points |

**Runbooks:** provider outage (fail over, degrade to search-only); connector outage (circuit-break, banner); leak canary (kill switch per source, incident process); quality drop (roll back prompt/model version); cost spike (tighten caps, check for loops).

### 6.3 Change management: prompts and models are config
- Prompts, tool schemas, routing rules and thresholds live in a versioned config registry, with PR review and CI eval gates.
- **Model upgrades:** offline eval → shadow traffic → A/B at 5% → full rollout. Each run stores a `config_snapshot_id` for reproducibility.
- **Index changes:** blue/green reindex, with retrieval evals compared before cutover.

### 6.4 Cost model (illustrative)

| Item | Estimate |
|---|---|
| Quick answer (about 3 small-model calls + 1 large call) | about $0.05 |
| Deep report (about 40 extract calls on the small model + plan/synthesize/verify on the large model) | about $0.60 |
| Blend: 85% quick / 15% deep, 6k queries/day | about $0.13 × 6k ≈ $800/day ≈ $24k/month in LLM spend, plus about $8–12k/month for infrastructure |
| Value check | 6k × 15 min saved × $80/h ≈ $120k/day in recovered time |

**Cost levers:** model routing, prompt caching, an ACL-scoped semantic cache for repeat questions, extraction results cached per chunk version, deep mode only when the user asks for it.

### 6.5 Security and governance
- **Audit trail:** who asked, the query, docs retrieved and cited, model and config version, cost, timestamp. Retained for 1 year (configurable).
- **Data governance:**
  - A data-sources register (owner, classification, connector, ACL model).
  - Restricted collections opt in only.
  - Right-to-delete propagates from source → index → caches → saved reports within 24 h.
- **LLM vendor terms:** zero data retention, no training on company data, regional endpoints for residency.
- **Security review:** pen test for injection and exfiltration paths; red-team suite in CI.

### 6.6 Roadmap (trust features ship first)
- **v0 (one team, about 6 weeks):** read-only; 2 sources (wiki + docs); quick mode; ACL pre-filter and citations from day one; golden set of 100; tracing.
- **v1:** all 6 source types; deep async reports; entity store; verifier; online evals; model routing; semantic cache; Slack bot.
- **v2:** saved and shared reports with ACL re-check; scheduled briefs; proactive conflict detection; human-approved write tools.

### 6.7 Risk register

| Risk | Likelihood | Impact | Mitigation / owner |
|---|---|---|---|
| ACL leak | Low | Critical | Pre-filter + live re-check + canaries / Security |
| Low trust from early hallucinations | Medium | High | Strict grounding, visible citations, limited v0 / Product |
| Connector API limits and changes | High | Medium | Reconciliation jobs, circuit breakers / Platform |
| LLM cost overrun | Medium | Medium | Caps, routing, budgets / FinOps |
| Poor source quality (stale wikis) | High | Medium | Content-owner feedback loop, freshness signals / Knowledge mgmt |
| Adoption stalls | Medium | High | Slack integration, champions, measure time saved / Product |

### 6.8 Assumptions and limitations
- Source systems expose ACLs and change events. If they don't, nightly sync is used, with a larger lag window and stricter deny-by-default.
- Answers can only be as good as the documents. The system reports gaps but cannot fill them.
- Effective-date and entity extraction are probabilistic, so low-confidence cases are flagged, not hidden.
- All numbers are illustrative and need validation in a pilot.
