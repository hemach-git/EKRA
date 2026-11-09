"""Config loading: config.yaml + environment overrides. No secrets live here."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


@lru_cache(maxsize=1)
def get_config() -> dict[str, Any]:
    with open(ROOT / "config.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    llm = cfg["llm"]
    llm["provider"] = os.getenv("LLM_PROVIDER", llm["provider"]).lower()
    llm["ollama_url"] = os.getenv("OLLAMA_URL", llm["ollama_url"])
    llm["models"]["fast"] = os.getenv("LLM_MODEL_FAST", llm["models"]["fast"])
    llm["models"]["main"] = os.getenv("LLM_MODEL_MAIN", llm["models"]["main"])
    ref = os.getenv("EKRA_REFERENCE_DATE", cfg.get("reference_date"))
    cfg["reference_date"] = str(ref) if ref else None
    return cfg


def reload_config() -> dict[str, Any]:
    get_config.cache_clear()
    return get_config()


def today() -> date:
    ref = get_config().get("reference_date")
    return date.fromisoformat(ref) if ref else date.today()


def path_for(key: str) -> Path:
    p = Path(get_config()["paths"][key])
    p = p if p.is_absolute() else ROOT / p
    if key != "eval_results":
        p.parent.mkdir(parents=True, exist_ok=True)
    else:
        p.mkdir(parents=True, exist_ok=True)
    return p


def config_snapshot() -> tuple[str, dict[str, Any]]:
    """Return (snapshot_id, config) - the id is a short hash so each run is reproducible."""
    from app.agent.prompts import PROMPT_VERSION

    cfg = {**get_config(), "prompt_version": PROMPT_VERSION}
    blob = json.dumps(cfg, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:12], cfg
