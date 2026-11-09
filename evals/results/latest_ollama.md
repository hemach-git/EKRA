# Eval results (ollama) - 2026-11-09T01:11:56

**Pass rate: 30/30 (100%)** | ACL leaks: **0** | citation validity: 1.0 (467 checked) | avg latency: 37835 ms | tokens: 82840

> Real local LLM run (Ollama). Statuses are rules-based; claims/summary come from the model and are verified.

| Category | Passed | Total |
|---|---|---|
| positive | 10 | 10 |
| negative | 6 | 6 |
| edge | 10 | 10 |
| acl | 4 | 4 |

| ID | Category | User | Result | Status | Latency ms | Failures |
|---|---|---|---|---|---|---|
| P01 | positive | alice | PASS | ok | 104573 |  |
| P02 | positive | carol | PASS | ok | 159988 |  |
| P03 | positive | alice | PASS | ok | 64202 |  |
| P04 | positive | alice | PASS | ok | 73423 |  |
| P05 | positive | alice | PASS | ok | 26853 |  |
| P06 | positive | alice | PASS | ok | 24659 |  |
| P07 | positive | bob | PASS | ok | 28035 |  |
| P08 | positive | alice | PASS | ok | 26128 |  |
| P09 | positive | bob | PASS | ok | 24013 |  |
| P10 | positive | alice | PASS | ok | 21840 |  |
| N01 | negative | alice | PASS | abstained | 4065 |  |
| N02 | negative | alice | PASS | abstained | 3431 |  |
| N03 | negative | alice | PASS | abstained | 3362 |  |
| N04 | negative | alice | PASS | abstained | 3554 |  |
| N05 | negative | dave | PASS | abstained | 3874 |  |
| N06 | negative | bob | PASS | abstained | 3348 |  |
| E01 | edge | carol | PASS | ok | 19507 |  |
| E02 | edge | alice | PASS | ok | 20637 |  |
| E03 | edge | alice | PASS | ok | 91950 |  |
| E04 | edge | alice | PASS | ok | 94098 |  |
| E05 | edge | alice | PASS | ok | 92480 |  |
| E06 | edge | alice | PASS | abstained | 4239 |  |
| E07 | edge | alice | PASS | blocked | 5 |  |
| E08 | edge | alice | PASS | blocked | 6 |  |
| E09 | edge | alice | PASS | ok | 27752 |  |
| E10 | edge | alice | PASS | ok | 25184 |  |
| A01 | acl | alice | PASS | abstained | 3844 |  |
| A02 | acl | bob | PASS | ok | 88581 |  |
| A03 | acl | alice | PASS | ok | 91409 |  |
| A04 | acl | nobody | PASS | blocked | 0 |  |