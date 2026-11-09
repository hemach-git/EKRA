"""Resolve relative time phrases ('last 2 years', 'in 2025', 'Q3 2025') to absolute dates - in code, not by the LLM.

The window is applied to each document's EFFECTIVE date (the date its content refers to), not its edit date.
"""
from __future__ import annotations

import calendar
import re
from datetime import date

from app.core.models import TimeWindow

_NUM = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
        "nine": 9, "ten": 10, "twelve": 12, "eighteen": 18}


def _minus_months(d: date, months: int) -> date:
    y, m = divmod(d.year * 12 + (d.month - 1) - months, 12)
    return date(y, m + 1, min(d.day, calendar.monthrange(y, m + 1)[1]))


def parse_window(question: str, today: date) -> TimeWindow:
    q = question.lower()
    m = re.search(r"\b(?:last|past|previous)\s+(\d+|[a-z]+)\s+(year|month|quarter|week)s?\b", q)
    if m:
        raw, unit = m.group(1), m.group(2)
        n = int(raw) if raw.isdigit() else _NUM.get(raw)
        if n:
            months = {"year": 12, "quarter": 3, "month": 1}.get(unit)
            start = _minus_months(today, n * months) if months else date.fromordinal(today.toordinal() - 7 * n)
            return TimeWindow(start=start, end=today, label=f"last {n} {unit}{'s' if n > 1 else ''}")
    if re.search(r"\blast year\b", q):
        y = today.year - 1
        return TimeWindow(start=date(y, 1, 1), end=date(y, 12, 31), label=f"calendar year {y}")
    if re.search(r"\bthis year\b", q):
        return TimeWindow(start=date(today.year, 1, 1), end=today, label=f"{today.year} to date")
    m = re.search(r"\bbetween\s+(20\d\d)\s+and\s+(20\d\d)\b", q)
    if m:
        a, b = sorted((int(m.group(1)), int(m.group(2))))
        return TimeWindow(start=date(a, 1, 1), end=date(b, 12, 31), label=f"{a}-{b}")
    m = re.search(r"\bq([1-4])\s*(20\d\d)\b|\b(20\d\d)\s*q([1-4])\b", q)
    if m:
        qn, y = (int(m.group(1)), int(m.group(2))) if m.group(1) else (int(m.group(4)), int(m.group(3)))
        sm = 3 * (qn - 1) + 1
        return TimeWindow(start=date(y, sm, 1), end=date(y, sm + 2, calendar.monthrange(y, sm + 2)[1]),
                          label=f"Q{qn} {y}")
    m = re.search(r"\bh([12])\s*(20\d\d)\b|\b(20\d\d)\s*h([12])\b", q)
    if m:
        h, y = (int(m.group(1)), int(m.group(2))) if m.group(1) else (int(m.group(4)), int(m.group(3)))
        return (TimeWindow(start=date(y, 1, 1), end=date(y, 6, 30), label=f"H1 {y}") if h == 1
                else TimeWindow(start=date(y, 7, 1), end=date(y, 12, 31), label=f"H2 {y}"))
    m = re.search(r"\bsince\s+(20\d\d)\b", q)
    if m:
        return TimeWindow(start=date(int(m.group(1)), 1, 1), end=today, label=f"since {m.group(1)}")
    m = re.search(r"\b(?:in|during|for|from)\s+(20\d\d)\b", q) or re.search(r"\b(20\d\d)\b", q)
    if m:
        y = int(m.group(1))
        return TimeWindow(start=date(y, 1, 1), end=date(y, 12, 31), label=str(y))
    return TimeWindow(label="all time")
