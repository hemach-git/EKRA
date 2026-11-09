# Eval results (mock) - 2026-11-09T00:52:54

**Pass rate: 30/30 (100%)** | ACL leaks: **0** | citation validity: 1.0 (521 checked) | avg latency: 79 ms | tokens: 63746

> Mock provider: pass rate checks pipeline WIRING (retrieval, ACL, verification, schema), NOT real LLM accuracy; the mock heuristics were written alongside this golden set.

| Category | Passed | Total |
|---|---|---|
| positive | 10 | 10 |
| negative | 6 | 6 |
| edge | 10 | 10 |
| acl | 4 | 4 |

| ID | Category | User | Result | Status | Latency ms | Failures |
|---|---|---|---|---|---|---|
| P01 | positive | alice | PASS | ok | 240 |  |
| P02 | positive | carol | PASS | ok | 226 |  |
| P03 | positive | alice | PASS | ok | 48 |  |
| P04 | positive | alice | PASS | ok | 217 |  |
| P05 | positive | alice | PASS | ok | 41 |  |
| P06 | positive | alice | PASS | ok | 52 |  |
| P07 | positive | bob | PASS | ok | 56 |  |
| P08 | positive | alice | PASS | ok | 42 |  |
| P09 | positive | bob | PASS | ok | 34 |  |
| P10 | positive | alice | PASS | ok | 46 |  |
| N01 | negative | alice | PASS | abstained | 7 |  |
| N02 | negative | alice | PASS | abstained | 9 |  |
| N03 | negative | alice | PASS | abstained | 8 |  |
| N04 | negative | alice | PASS | abstained | 8 |  |
| N05 | negative | dave | PASS | abstained | 8 |  |
| N06 | negative | bob | PASS | abstained | 8 |  |
| E01 | edge | carol | PASS | ok | 20 |  |
| E02 | edge | alice | PASS | ok | 20 |  |
| E03 | edge | alice | PASS | ok | 234 |  |
| E04 | edge | alice | PASS | ok | 235 |  |
| E05 | edge | alice | PASS | ok | 236 |  |
| E06 | edge | alice | PASS | abstained | 7 |  |
| E07 | edge | alice | PASS | blocked | 6 |  |
| E08 | edge | alice | PASS | blocked | 6 |  |
| E09 | edge | alice | PASS | ok | 50 |  |
| E10 | edge | alice | PASS | ok | 36 |  |
| A01 | acl | alice | PASS | abstained | 8 |  |
| A02 | acl | bob | PASS | ok | 223 |  |
| A03 | acl | alice | PASS | ok | 233 |  |
| A04 | acl | nobody | PASS | blocked | 0 |  |