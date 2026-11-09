"""Step / time / token / tool-call budgets + loop detection (mitigates: infinite loops, cost runaway)."""
from __future__ import annotations

import hashlib
import json
import threading
import time

from app.core.config import get_config


class BudgetExceeded(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class LoopDetected(Exception):
    pass


class Budget:
    def __init__(self, mode: str = "deep"):
        cfg = dict(get_config()["agent"])
        if mode == "quick":
            cfg["max_replans"] = 0
            cfg["max_seconds"] = min(cfg["max_seconds"], 90)
        self.cfg = cfg
        self.t0 = time.monotonic()
        self.steps = 0
        self.replans = 0
        self.tool_calls = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.llm_calls = 0
        self._seen: set[str] = set()
        self._lock = threading.Lock()

    @property
    def tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def elapsed_s(self) -> float:
        return time.monotonic() - self.t0

    def check(self) -> None:
        if self.elapsed_s() > self.cfg["max_seconds"]:
            raise BudgetExceeded(f"time budget of {self.cfg['max_seconds']}s reached")
        if self.steps > self.cfg["max_steps"]:
            raise BudgetExceeded(f"step budget of {self.cfg['max_steps']} reached")
        if self.tokens > self.cfg["max_tokens"]:
            raise BudgetExceeded(f"token budget of {self.cfg['max_tokens']} reached")
        if self.tool_calls > self.cfg["max_tool_calls"]:
            raise BudgetExceeded(f"tool-call budget of {self.cfg['max_tool_calls']} reached")

    def exhausted(self) -> bool:
        try:
            self.check()
            return False
        except BudgetExceeded:
            return True

    def start_step(self) -> None:
        with self._lock:
            self.steps += 1
        self.check()

    def can_replan(self) -> bool:
        return self.replans < self.cfg["max_replans"] and self.steps < self.cfg["max_steps"]

    def charge_llm(self, prompt_tokens: int, completion_tokens: int) -> None:
        with self._lock:
            self.llm_calls += 1
            self.prompt_tokens += prompt_tokens
            self.completion_tokens += completion_tokens
        self.check()

    def register_tool_call(self, name: str, args: dict) -> None:
        key = hashlib.sha1(json.dumps([name, args], sort_keys=True, default=str).encode()).hexdigest()
        with self._lock:
            if key in self._seen:
                raise LoopDetected(f"identical {name} call already made")
            self._seen.add(key)
            self.tool_calls += 1
        self.check()
