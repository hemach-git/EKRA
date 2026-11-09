"""Ingestion of the SYNTHETIC corpus: parse -> chunk -> flag injections -> entity mentions -> ACL sync.

In production each step is a connector/pipeline stage (see docs/design.md section 2.5). Here it is one function.
Run `python -m app.data.seed --reset` to rebuild the database.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone

from app.core import db
from app.core.config import get_config, path_for
from app.core.logging import log_event
from app.data import corpus
from app.guardrails.input import is_suspicious


def _chunk_section(heading: str, body: str, target: int) -> list[tuple[str, str]]:
    """One chunk per section; sections longer than `target` chars are split at sentence boundaries."""
    if len(body) <= target:
        return [(heading, body)]
    parts, cur = [], ""
    for sent in re.split(r"(?<=[.!?])\s+", body):
        if cur and len(cur) + len(sent) > target:
            parts.append(cur.strip())
            cur = ""
        cur += sent + " "
    if cur.strip():
        parts.append(cur.strip())
    return [(f"{heading} (part {i + 1})", p) for i, p in enumerate(parts)]


def alias_regex(alias: str) -> re.Pattern:
    flags = 0 if len(alias) <= 3 else re.I   # short aliases such as "NBA" are case-sensitive
    return re.compile(rf"(?<![A-Za-z0-9]){re.escape(alias)}(?![A-Za-z0-9])", flags)


def find_mentions(text: str, entities: dict[str, list[str]]) -> list[str]:
    return [eid for eid, names in entities.items() if any(alias_regex(n).search(text) for n in names)]


def is_seeded() -> bool:
    try:
        with db.read() as c:
            return c.execute("SELECT COUNT(*) FROM documents").fetchone()[0] > 0
    except Exception:  # noqa: BLE001
        return False


def seed(reset: bool = False) -> dict:
    if reset:
        p = path_for("db")
        for suffix in ("", "-wal", "-shm"):
            f = p.with_name(p.name + suffix)
            if f.exists():
                f.unlink()
    db.init_db()
    if is_seeded():
        return {"seeded": False}
    cfg = get_config()["retrieval"]
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    entities = {e[0]: [e[1], *e[2]] for e in corpus.ENTITIES}
    n_chunks = n_mentions = 0
    with db.tx() as c:
        for gid, desc in corpus.GROUPS.items():
            c.execute("INSERT INTO groups VALUES (?,?)", (gid, desc))
        for uid, name, role, groups in corpus.USERS:
            c.execute("INSERT INTO users VALUES (?,?,?)", (uid, name, role))
            for g in groups:
                c.execute("INSERT INTO user_groups VALUES (?,?)", (uid, g))
        for eid, name, aliases, team, topics in corpus.ENTITIES:
            c.execute("INSERT INTO entities VALUES (?,?,?,?,1)", (eid, name, team, json.dumps(topics)))
            for a in {name, *aliases}:
                c.execute("INSERT INTO entity_aliases VALUES (?,?)", (a, eid))
        for d in corpus.DOCS:
            text = "\n\n".join(f"## {h}\n{b}" for h, b in d["sections"])
            suspect = int(is_suspicious(text))
            src = corpus.SOURCE_BY_TYPE[d["doc_type"]]
            c.execute(
                "INSERT INTO documents VALUES (?,?,?,?,?,?,?,?,?,?,?,?,1,?)",
                (d["doc_id"], d["title"], d["doc_type"], d["effective_date"], d["modified_at"], d["owner_team"], src,
                 f"internal://{src.lower()}/{d['doc_id']}", text, d["version"], int(d["superseded"]),
                 now if d["acl_synced"] else None, suspect))
            for g in d["acl"]:
                c.execute("INSERT INTO acl_entries VALUES (?,?)", (d["doc_id"], g))
            ordn = 0
            for heading, body in d["sections"]:
                for sec, part in _chunk_section(heading, body, cfg["chunk_target_chars"]):
                    cid = f"{d['doc_id']}#{ordn}"
                    c.execute("INSERT INTO chunks VALUES (?,?,?,?,?,?)",
                              (cid, d["doc_id"], ordn, sec, part, int(is_suspicious(part))))
                    n_chunks += 1
                    for eid in find_mentions(f"{sec}. {part}", entities):
                        c.execute("INSERT INTO entity_mentions VALUES (?,?,?)", (eid, cid, d["doc_id"]))
                        n_mentions += 1
                    ordn += 1
    out = {"seeded": True, "docs": len(corpus.DOCS), "chunks": n_chunks, "mentions": n_mentions,
           "entities": len(corpus.ENTITIES)}
    log_event("seed_complete", **out)
    return out


def ensure_seeded() -> None:
    if not is_seeded():
        seed()


if __name__ == "__main__":
    print(seed(reset="--reset" in sys.argv))
