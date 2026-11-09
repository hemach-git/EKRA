import sqlite3
from datetime import date

import pytest

from app.core import db
from app.llm import get_provider
from app.retrieval import acl
from app.retrieval.index import get_index, tokenize
from app.tools.tools import call_tool


def test_schema_enforces_foreign_keys():
    with pytest.raises(sqlite3.IntegrityError):
        with db.tx() as c:
            c.execute("INSERT INTO acl_entries VALUES ('no-such-doc','all-employees')")


def test_schema_enforces_check_constraints():
    with pytest.raises(sqlite3.IntegrityError):
        with db.tx() as c:
            c.execute("INSERT INTO documents (doc_id,title,doc_type,effective_date,modified_at,owner_team,"
                      "source_system,url,text) VALUES ('x','t','spreadsheet','2025-01-01','2025-01-01','o','s','u','t')")


def test_seeded_corpus_is_consistent():
    with db.read() as c:
        assert c.execute("PRAGMA foreign_key_check").fetchall() == []
        assert c.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 52
        assert c.execute("SELECT COUNT(*) FROM documents WHERE is_synthetic=0").fetchone()[0] == 0


def test_acl_groups_gate_documents():
    assert "lighthouse-report" in acl.allowed_doc_ids("carol")
    for u in ("alice", "bob", "dave"):
        assert "lighthouse-report" not in acl.allowed_doc_ids(u)
    assert "compass-meeting-0910" in acl.allowed_doc_ids("alice")          # growth-only
    assert "compass-meeting-0910" not in acl.allowed_doc_ids("bob")


def test_stale_or_missing_acl_is_denied_by_default():
    assert all("orion-draft" not in acl.allowed_doc_ids(u) for u in ("alice", "bob", "carol", "dave"))
    assert not acl.can_read("alice", "orion-draft")


def test_unknown_user_gets_nothing():
    assert acl.allowed_doc_ids("mallory") == set()
    assert not acl.can_read("mallory", "compass-prd")


def test_contractor_sees_only_glossary():
    assert acl.allowed_doc_ids("dave") == {"glossary-wiki"}


def test_search_prefilters_by_acl():
    idx = get_index(get_provider())
    q = "Project Lighthouse licensing recommendation engine Orbit AI"
    hits_bob, _ = idx.search(q, acl.allowed_doc_ids("bob"), top_k=20)
    hits_carol, _ = idx.search(q, acl.allowed_doc_ids("carol"), top_k=20)
    assert not any(h.doc_id.startswith("lighthouse") for h in hits_bob)
    assert any(h.doc_id == "lighthouse-report" for h in hits_carol)


def test_search_excludes_superseded_and_applies_window():
    idx = get_index(get_provider())
    allowed = acl.allowed_doc_ids("alice")
    hits, _ = idx.search("Project Compass general availability", allowed, top_k=30)
    assert "roadmap-2025q2-draft" not in {h.doc_id for h in hits}
    hits, _ = idx.search("Related Items collaborative filtering", allowed, date_from=date(2024, 11, 9), top_k=30)
    assert not {h.doc_id for h in hits} & {"legacy-prd", "legacy-report-2023", "legacy-report-2024"}


def test_search_neutralizes_injection_in_retrieved_text():
    idx = get_index(get_provider())
    hits, _ = idx.search("NBA engineering standup recommendations", acl.allowed_doc_ids("alice"), top_k=20)
    standup = [h for h in hits if h.doc_id == "beacon-standup-0203"]
    assert standup and all("Ignore all previous" not in h.text for h in standup)
    assert any(h.injection_suspect for h in standup)


def test_hybrid_ranking_finds_expected_document():
    idx = get_index(get_provider())
    hits, _ = idx.search("rolled back creator exposure regression", acl.allowed_doc_ids("alice"), top_k=3)
    assert hits[0].doc_id == "compass-incident"


def test_tokenizer_stems_and_drops_stopwords():
    assert tokenize("The recommendations were personalized") == ["recommend", "personal"]
    assert tokenize("personalization") == tokenize("personalize") == tokenize("personalized")


def test_entity_lookup_never_reveals_hidden_initiatives(ctx):
    for user in ("alice", "bob", "dave"):
        r = call_tool(ctx(user), "entity_lookup", {"terms": ["Project Lighthouse", "personalization"]})
        assert "Project Lighthouse" not in [e["name"] for e in (r.data or [])]
    r = call_tool(ctx("carol"), "entity_lookup", {"terms": ["Project Lighthouse"]})
    assert [e["name"] for e in r.data] == ["Project Lighthouse"]


def test_short_alias_is_case_sensitive(ctx):
    assert [e["name"] for e in call_tool(ctx(), "entity_lookup", {"terms": ["status of NBA"]}).data] == [
        "Next-Best-Action Engine"]
    assert call_tool(ctx(), "entity_lookup", {"terms": ["we watched the nba finals"]}).status == "empty"
