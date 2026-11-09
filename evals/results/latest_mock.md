# Eval results (mock) - 2026-11-09T00:43:25

**Pass rate: 30/30 (100%)** | ACL leaks: **0** | citation validity: 1.0 (456 checked) | avg latency: 103 ms | tokens: 54836

> Mock provider: pass rate checks pipeline WIRING (retrieval, ACL, verification, schema), NOT real LLM accuracy; the mock heuristics were written alongside this golden set.

| Category | Passed | Total |
|---|---|---|
| positive | 10 | 10 |
| negative | 6 | 6 |
| edge | 10 | 10 |
| acl | 4 | 4 |

| ID | Category | User | Result | Status | Latency ms | Failures |
|---|---|---|---|---|---|---|
| P01 | positive | alice | PASS | ok | 288 |  |
| P02 | positive | carol | PASS | ok | 252 |  |
| P03 | positive | alice | PASS | ok | 50 |  |
| P04 | positive | alice | PASS | ok | 280 |  |
| P05 | positive | alice | PASS | ok | 61 |  |
| P06 | positive | alice | PASS | ok | 56 |  |
| P07 | positive | bob | PASS | ok | 75 |  |
| P08 | positive | alice | PASS | ok | 39 |  |
| P09 | positive | bob | PASS | ok | 53 |  |
| P10 | positive | alice | PASS | ok | 45 |  |
| N01 | negative | alice | PASS | abstained | 12 |  |
| N02 | negative | alice | PASS | abstained | 12 |  |
| N03 | negative | alice | PASS | abstained | 13 |  |
| N04 | negative | alice | PASS | abstained | 14 |  |
| N05 | negative | dave | PASS | abstained | 11 |  |
| N06 | negative | bob | PASS | abstained | 13 |  |
| E01 | edge | carol | PASS | ok | 31 |  |
| E02 | edge | alice | PASS | ok | 29 |  |
| E03 | edge | alice | PASS | ok | 305 |  |
| E04 | edge | alice | PASS | ok | 277 |  |
| E05 | edge | alice | PASS | ok | 307 |  |
| E06 | edge | alice | PASS | abstained | 20 |  |
| E07 | edge | alice | PASS | blocked | 16 |  |
| E08 | edge | alice | PASS | blocked | 14 |  |
| E09 | edge | alice | PASS | ok | 103 |  |
| E10 | edge | alice | PASS | ok | 92 |  |
| A01 | acl | alice | PASS | abstained | 19 |  |
| A02 | acl | bob | PASS | ok | 321 |  |
| A03 | acl | alice | PASS | ok | 278 |  |
| A04 | acl | nobody | PASS | blocked | 0 |  |