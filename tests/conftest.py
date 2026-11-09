"""Tests run fully offline: mock LLM provider, fixed reference date, isolated temp DB + log file."""
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["LLM_PROVIDER"] = "mock"
os.environ["EKRA_REFERENCE_DATE"] = "2026-11-09"


@pytest.fixture(scope="session", autouse=True)
def isolated_env(tmp_path_factory):
    from app.core import config

    tmp = tmp_path_factory.mktemp("ekra")
    cfg = config.get_config()
    cfg["paths"]["db"] = str(tmp / "test.db")
    cfg["paths"]["log_file"] = str(tmp / "app.jsonl")
    from app.data.seed import seed
    from app.retrieval.index import reset_index_cache

    reset_index_cache()
    seed(reset=True)
    yield tmp


@pytest.fixture()
def ctx():
    from app.agent.budget import Budget
    from app.agent.context import RunContext
    from app.llm import get_provider
    from app.retrieval import acl

    def make(user="alice", mode="deep"):
        return RunContext(request_id="t", user_id=user, question="q", mode=mode, provider=get_provider(),
                          budget=Budget(mode), allowed=acl.allowed_doc_ids(user))
    return make
