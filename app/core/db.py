"""SQLite with foreign keys ON. Schema = the data model in docs/design.md (prototype subset)."""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager

from app.core.config import path_for

SCHEMA = """
CREATE TABLE IF NOT EXISTS groups (group_id TEXT PRIMARY KEY, description TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS users (user_id TEXT PRIMARY KEY, name TEXT NOT NULL, role TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS user_groups (
  user_id TEXT NOT NULL REFERENCES users(user_id), group_id TEXT NOT NULL REFERENCES groups(group_id),
  PRIMARY KEY (user_id, group_id));
CREATE TABLE IF NOT EXISTS documents (
  doc_id TEXT PRIMARY KEY, title TEXT NOT NULL,
  doc_type TEXT NOT NULL CHECK (doc_type IN ('roadmap','prd','report','meeting','wiki')),
  effective_date TEXT NOT NULL, modified_at TEXT NOT NULL, owner_team TEXT NOT NULL,
  source_system TEXT NOT NULL, url TEXT NOT NULL, text TEXT NOT NULL, version TEXT NOT NULL DEFAULT 'v1',
  superseded INTEGER NOT NULL DEFAULT 0, acl_synced_at TEXT,
  is_synthetic INTEGER NOT NULL DEFAULT 1, injection_suspect INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS acl_entries (
  doc_id TEXT NOT NULL REFERENCES documents(doc_id), group_id TEXT NOT NULL REFERENCES groups(group_id),
  PRIMARY KEY (doc_id, group_id));
CREATE TABLE IF NOT EXISTS chunks (
  chunk_id TEXT PRIMARY KEY, doc_id TEXT NOT NULL REFERENCES documents(doc_id), ord INTEGER NOT NULL,
  section TEXT NOT NULL, text TEXT NOT NULL, injection_suspect INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS chunk_embeddings (
  chunk_id TEXT NOT NULL REFERENCES chunks(chunk_id), model TEXT NOT NULL, vector BLOB NOT NULL,
  PRIMARY KEY (chunk_id, model));
CREATE TABLE IF NOT EXISTS entities (
  entity_id TEXT PRIMARY KEY, canonical_name TEXT NOT NULL, owner_team TEXT NOT NULL,
  topics TEXT NOT NULL, is_synthetic INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS entity_aliases (
  alias TEXT NOT NULL, entity_id TEXT NOT NULL REFERENCES entities(entity_id), PRIMARY KEY (alias, entity_id));
CREATE TABLE IF NOT EXISTS entity_mentions (
  entity_id TEXT NOT NULL REFERENCES entities(entity_id), chunk_id TEXT NOT NULL REFERENCES chunks(chunk_id),
  doc_id TEXT NOT NULL REFERENCES documents(doc_id), PRIMARY KEY (entity_id, chunk_id));
CREATE TABLE IF NOT EXISTS config_snapshots (
  snapshot_id TEXT PRIMARY KEY, config_json TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS research_runs (
  run_id TEXT PRIMARY KEY, request_id TEXT NOT NULL, user_id TEXT NOT NULL REFERENCES users(user_id),
  question TEXT NOT NULL, status TEXT NOT NULL CHECK (status IN ('ok','partial','abstained','blocked','error')),
  message TEXT NOT NULL DEFAULT '', source TEXT NOT NULL DEFAULT 'app',
  plan_json TEXT NOT NULL, report_json TEXT, metrics_json TEXT NOT NULL,
  snapshot_id TEXT NOT NULL REFERENCES config_snapshots(snapshot_id),
  latency_ms INTEGER NOT NULL DEFAULT 0, tokens INTEGER NOT NULL DEFAULT 0,
  n_findings INTEGER NOT NULL DEFAULT 0, n_citations INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS run_steps (
  step_id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL REFERENCES research_runs(run_id),
  step_no INTEGER NOT NULL, kind TEXT NOT NULL, tool TEXT NOT NULL, status TEXT NOT NULL,
  duration_ms INTEGER NOT NULL, summary TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS run_citations (
  run_id TEXT NOT NULL REFERENCES research_runs(run_id), citation_id TEXT NOT NULL,
  doc_id TEXT NOT NULL REFERENCES documents(doc_id), chunk_id TEXT NOT NULL REFERENCES chunks(chunk_id),
  PRIMARY KEY (run_id, citation_id));
CREATE TABLE IF NOT EXISTS feedback (
  feedback_id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES research_runs(run_id),
  user_id TEXT NOT NULL REFERENCES users(user_id), rating TEXT NOT NULL CHECK (rating IN ('up','down')),
  reason TEXT, comment TEXT NOT NULL DEFAULT '', claim_index INTEGER, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit_log (
  audit_id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, request_id TEXT NOT NULL, user_id TEXT NOT NULL,
  action TEXT NOT NULL, detail_json TEXT NOT NULL, model TEXT NOT NULL DEFAULT '');
CREATE INDEX IF NOT EXISTS ix_chunks_doc ON chunks(doc_id);
CREATE INDEX IF NOT EXISTS ix_mentions_doc ON entity_mentions(doc_id);
CREATE INDEX IF NOT EXISTS ix_runs_created ON research_runs(created_at);
CREATE INDEX IF NOT EXISTS ix_audit_ts ON audit_log(ts);
"""

_write_lock = threading.RLock()


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(path_for("db"), timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def tx():
    """Serialized write transaction (SQLite is single-writer; agent workers write from threads)."""
    with _write_lock:
        conn = connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


@contextmanager
def read():
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    with tx() as c:
        c.executescript(SCHEMA)
