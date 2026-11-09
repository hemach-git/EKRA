"""Ollama provider (local models). No API keys involved - data never leaves the machine."""
from __future__ import annotations

import time
from typing import Optional

import numpy as np
import requests

from app.core.config import get_config
from app.llm.base import LLMError, LLMProvider, LLMResponse, hash_embed


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(self):
        cfg = get_config()["llm"]
        self.url = cfg["ollama_url"].rstrip("/")
        self.models = cfg["models"]
        self.embed_model = cfg["embed_model"]
        self.timeout = cfg["timeout_s"]
        self.temperature = cfg["temperature"]
        self.max_out = cfg["max_output_tokens"]
        self._embed_ok: Optional[bool] = None

    @property
    def embed_name(self) -> str:  # type: ignore[override]
        return self.embed_model if self._embed_ok is not False else "hash-256"

    def model_for(self, tier: str) -> str:
        return self.models["main" if tier == "main" else "fast"]

    def available(self) -> bool:
        try:
            return requests.get(f"{self.url}/api/tags", timeout=3).ok
        except requests.RequestException:
            return False

    def generate(self, task, system, user, *, tier="fast", json_mode=True, payload=None, max_tokens=None):
        model = self.model_for(tier)
        body = {
            "model": model, "stream": False,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "options": {"temperature": self.temperature, "num_predict": max_tokens or self.max_out},
        }
        if json_mode:
            body["format"] = "json"
        if model.startswith("gpt-oss"):
            body["think"] = "low"                      # reasoning model: keep thinking short
            body["options"]["num_predict"] = (max_tokens or self.max_out) + 1500
        last: Optional[Exception] = None
        for attempt in range(2):
            t0 = time.perf_counter()
            try:
                r = requests.post(f"{self.url}/api/chat", json=body, timeout=self.timeout)
                if r.status_code != 200:
                    raise LLMError(f"ollama HTTP {r.status_code}: {r.text[:200]}")
                data = r.json()
                text = (data.get("message") or {}).get("content", "")
                if not text.strip():
                    raise LLMError("ollama returned empty content")
                return LLMResponse(text=text, prompt_tokens=data.get("prompt_eval_count", 0),
                                   completion_tokens=data.get("eval_count", 0), model=model,
                                   latency_ms=int((time.perf_counter() - t0) * 1000))
            except (requests.RequestException, LLMError) as e:
                last = e
                time.sleep(0.5 * (attempt + 1))
        raise LLMError(f"ollama call failed after retries: {last}")

    def embed(self, texts, kind="document"):
        prefix = "search_query: " if kind == "query" else "search_document: "
        try:
            r = requests.post(f"{self.url}/api/embed", timeout=self.timeout,
                              json={"model": self.embed_model, "input": [prefix + t for t in texts]})
            r.raise_for_status()
            arr = np.array(r.json()["embeddings"], dtype=np.float32)
            norms = np.linalg.norm(arr, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            self._embed_ok = True
            return arr / norms
        except (requests.RequestException, KeyError, ValueError):
            self._embed_ok = False
            return hash_embed(texts)
