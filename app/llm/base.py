"""LLM provider interface. Providers: ollama (real, local) and mock (deterministic, offline)."""
from __future__ import annotations

import re
import zlib
from dataclasses import dataclass
from typing import Optional

import numpy as np


class LLMError(Exception):
    """Provider failure (timeout, bad status, empty output). The agent degrades instead of crashing."""


@dataclass
class LLMResponse:
    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model: str = ""
    latency_ms: int = 0


class LLMProvider:
    name = "base"
    embed_name = "hash-256"

    def generate(self, task: str, system: str, user: str, *, tier: str = "fast", json_mode: bool = True,
                 payload: Optional[dict] = None, max_tokens: Optional[int] = None) -> LLMResponse:
        raise NotImplementedError

    def embed(self, texts: list[str], kind: str = "document") -> np.ndarray:
        return hash_embed(texts)

    def available(self) -> bool:
        return True

    def model_for(self, tier: str) -> str:
        return self.name


_TOKEN = re.compile(r"[a-z0-9]+")
HASH_DIM = 256


def hash_embed(texts: list[str]) -> np.ndarray:
    """Deterministic bag-of-words + bigram hashing embedding (offline fallback). L2-normalized."""
    out = np.zeros((len(texts), HASH_DIM), dtype=np.float32)
    for i, t in enumerate(texts):
        toks = _TOKEN.findall(t.lower())
        feats = toks + [f"{a}_{b}" for a, b in zip(toks, toks[1:])]
        for f in feats:
            h = zlib.crc32(f.encode())
            out[i, h % HASH_DIM] += 1.0 if (h >> 8) & 1 else -1.0
    norms = np.linalg.norm(out, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return out / norms
