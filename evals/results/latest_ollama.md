# Eval results (ollama) - 2026-11-09T00:48:16

**Pass rate: 8/9 (89%)** | ACL leaks: **0** | citation validity: 1.0 (175 checked) | avg latency: 39374 ms | tokens: 27918

> Real local LLM run (Ollama). Statuses are rules-based; claims/summary come from the model and are verified.

| Category | Passed | Total |
|---|---|---|
| positive | 2 | 3 |
| negative | 2 | 2 |
| edge | 3 | 3 |
| acl | 1 | 1 |

| ID | Category | User | Result | Status | Latency ms | Failures |
|---|---|---|---|---|---|---|
| P01 | positive | alice | FAIL | ok | 82915 | missing citation to compass-incident |
| P03 | positive | alice | PASS | ok | 24948 |  |
| P08 | positive | alice | PASS | ok | 24207 |  |
| N01 | negative | alice | PASS | abstained | 4149 |  |
| N06 | negative | bob | PASS | abstained | 3347 |  |
| E03 | edge | alice | PASS | ok | 83477 |  |
| E09 | edge | alice | PASS | ok | 24352 |  |
| E10 | edge | alice | PASS | ok | 24967 |  |
| A02 | acl | bob | PASS | ok | 82005 |  |