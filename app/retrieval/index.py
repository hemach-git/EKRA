"""In-process hybrid search index: BM25 (keyword) + embeddings (vector), fused with reciprocal rank fusion.

The ACL filter is applied FIRST (candidate set = chunks of documents the user may read); ranking never sees
anything else. Chunks flagged as prompt-injection are neutralized before they leave the index.
"""
from __future__ import annotations

import math
import re
import threading
from collections import Counter
from datetime import date
from typing import Optional

import numpy as np

from app.core import db
from app.core.config import get_config
from app.core.models import ChunkHit
from app.guardrails.input import neutralize_untrusted
from app.llm.base import LLMProvider

_TOK = re.compile(r"[a-z0-9]+")
_STOP = set("the a an and or of to in on for with is are was were be by as at from that this it its into than "
            "we our their they about all any which what when who how did do does has have had not no".split())


def tokenize(text: str) -> list[str]:
    out = []
    for t in _TOK.findall(text.lower()):
        if t in _STOP:
            continue
        for suf in ("ations", "ation", "izing", "ized", "ing", "ed", "es", "s"):
            if len(t) > len(suf) + 3 and t.endswith(suf):
                t = t[: -len(suf)]
                break
        out.append(t)
    return out


class SearchIndex:
    K1, B = 1.4, 0.75

    def __init__(self, provider: LLMProvider):
        self.provider = provider
        self.recs: list[dict] = []
        self.V: Optional[np.ndarray] = None
        self.embed_model = ""
        self._load()

    # ------------------------------------------------------------------ build
    def _load(self) -> None:
        with db.read() as c:
            rows = c.execute(
                """SELECT c.chunk_id, c.doc_id, c.section, c.text, c.injection_suspect,
                          d.title, d.doc_type, d.effective_date, d.url, d.superseded
                   FROM chunks c JOIN documents d ON d.doc_id = c.doc_id ORDER BY c.chunk_id""").fetchall()
            ent = {}
            for r in c.execute("SELECT chunk_id, entity_id FROM entity_mentions"):
                ent.setdefault(r[0], set()).add(r[1])
        self.recs = []
        for r in rows:
            toks = tokenize(f"{r['title']} {r['section']} {r['text']}")
            self.recs.append({
                "chunk_id": r["chunk_id"], "doc_id": r["doc_id"], "section": r["section"], "text": r["text"],
                "suspect": bool(r["injection_suspect"]), "title": r["title"], "doc_type": r["doc_type"],
                "date": date.fromisoformat(r["effective_date"]), "url": r["url"], "superseded": bool(r["superseded"]),
                "tf": Counter(toks), "dl": len(toks), "entities": ent.get(r["chunk_id"], set()),
                "embed_text": f"{r['title']}. {r['section']}. {r['text']}",
            })
        n = len(self.recs) or 1
        df: Counter = Counter()
        for rec in self.recs:
            df.update(rec["tf"].keys())
        self.idf = {t: math.log(1 + (n - d + 0.5) / (d + 0.5)) for t, d in df.items()}
        self.avgdl = sum(r["dl"] for r in self.recs) / n
        self._load_vectors()

    def _load_vectors(self) -> None:
        self.provider.embed(["warmup"], "query")            # settles which embedding model is really in use
        self.embed_model = self.provider.embed_name
        with db.read() as c:
            cached = {r[0]: np.frombuffer(r[1], dtype=np.float32)
                      for r in c.execute("SELECT chunk_id, vector FROM chunk_embeddings WHERE model=?",
                                         (self.embed_model,))}
        missing = [r for r in self.recs if r["chunk_id"] not in cached]
        for i in range(0, len(missing), 32):
            batch = missing[i:i + 32]
            vecs = self.provider.embed([r["embed_text"] for r in batch], "document")
            if self.provider.embed_name != self.embed_model:      # embedder died mid-build -> restart on fallback
                self.embed_model = self.provider.embed_name
                return self._load_vectors()
            with db.tx() as c:
                for r, v in zip(batch, vecs):
                    c.execute("INSERT OR REPLACE INTO chunk_embeddings VALUES (?,?,?)",
                              (r["chunk_id"], self.embed_model, v.astype(np.float32).tobytes()))
            for r, v in zip(batch, vecs):
                cached[r["chunk_id"]] = v.astype(np.float32)
        self.V = np.stack([cached[r["chunk_id"]] for r in self.recs]) if self.recs else None

    # ------------------------------------------------------------------ search
    def _bm25(self, q_tokens: list[str], rec: dict) -> float:
        s = 0.0
        for t in set(q_tokens):
            tf = rec["tf"].get(t, 0)
            if tf:
                s += self.idf.get(t, 0.0) * tf * (self.K1 + 1) / (tf + self.K1 * (1 - self.B + self.B * rec["dl"] / self.avgdl))
        return s

    def search(self, query: str, allowed: set[str], *, date_from: Optional[date] = None, date_to: Optional[date] = None,
               doc_types: Optional[list[str]] = None, entity_ids: Optional[list[str]] = None,
               doc_ids: Optional[list[str]] = None, top_k: int = 8, include_superseded: bool = False
               ) -> tuple[list[ChunkHit], list[str]]:
        notes: list[str] = []
        cfg = get_config()["retrieval"]
        ents = set(entity_ids or [])
        cand = []
        for i, r in enumerate(self.recs):
            if r["doc_id"] not in allowed:                      # ACL PRE-FILTER (first condition, always)
                continue
            if r["superseded"] and not include_superseded:
                continue
            if date_from and r["date"] < date_from or date_to and r["date"] > date_to:
                continue
            if doc_types and r["doc_type"] not in doc_types:
                continue
            if doc_ids and r["doc_id"] not in doc_ids:
                continue
            if ents and not (r["entities"] & ents):
                continue
            cand.append(i)
        if not cand:
            return [], notes
        q_tokens = tokenize(query)
        bm = np.array([self._bm25(q_tokens, self.recs[i]) for i in cand])
        cos = np.zeros(len(cand))
        if self.V is not None:
            qv = self.provider.embed([query], "query")[0]
            if qv.shape[0] == self.V.shape[1]:
                cos = self.V[cand] @ qv
            else:
                notes.append("vector_search_skipped_dim_mismatch")
        k = cfg["rrf_k"]
        fused = np.zeros(len(cand))
        for scores, valid in ((bm, bm > 0), (cos, cos >= cfg.get("min_cosine", 0.6))):
            order = np.argsort(-scores)
            rank = 0
            for j in order:
                if valid[j]:
                    rank += 1
                    fused[j] += 1.0 / (k + rank)
        keep = [j for j in np.argsort(-fused) if fused[j] > 0][:top_k]
        hits = []
        for j in keep:
            r = self.recs[cand[j]]
            clean, flagged = neutralize_untrusted(r["text"])
            hits.append(ChunkHit(chunk_id=r["chunk_id"], doc_id=r["doc_id"], title=r["title"], section=r["section"],
                                 doc_type=r["doc_type"], effective_date=r["date"], text=clean,
                                 score=round(float(fused[j]), 5), url=r["url"], injection_suspect=flagged or r["suspect"]))
        return hits, notes

    def chunks_of(self, doc_id: str) -> list[ChunkHit]:
        out = []
        for r in self.recs:
            if r["doc_id"] == doc_id:
                clean, flagged = neutralize_untrusted(r["text"])
                out.append(ChunkHit(chunk_id=r["chunk_id"], doc_id=doc_id, title=r["title"], section=r["section"],
                                    doc_type=r["doc_type"], effective_date=r["date"], text=clean, url=r["url"],
                                    injection_suspect=flagged or r["suspect"]))
        return out

    def entities_of_chunk(self, chunk_id: str) -> set[str]:
        if not hasattr(self, "_chunk_ents"):
            self._chunk_ents = {r["chunk_id"]: r["entities"] for r in self.recs}
        return set(self._chunk_ents.get(chunk_id, ()))


_cache: dict[str, SearchIndex] = {}
_lock = threading.Lock()


def get_index(provider: LLMProvider) -> SearchIndex:
    with _lock:
        idx = _cache.get(provider.name)
        if idx is None:
            idx = _cache[provider.name] = SearchIndex(provider)
        return idx


def reset_index_cache() -> None:
    with _lock:
        _cache.clear()
