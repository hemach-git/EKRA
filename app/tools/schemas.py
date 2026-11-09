"""Typed tool contracts. Arguments are validated BEFORE the call; tools are read-only with bounded outputs."""
from __future__ import annotations

from datetime import date
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class SearchArgs(BaseModel):
    query: str = Field(min_length=1, max_length=256)
    doc_types: Optional[list[Literal["roadmap", "prd", "report", "meeting", "wiki"]]] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    entity_ids: Optional[list[str]] = Field(default=None, max_length=30)
    doc_ids: Optional[list[str]] = Field(default=None, max_length=30)
    top_k: int = Field(default=8, ge=1, le=50)


class ListDocsArgs(BaseModel):
    entity_ids: list[str] = Field(min_length=1, max_length=30)
    date_from: Optional[date] = None
    date_to: Optional[date] = None


class FetchArgs(BaseModel):
    doc_id: str = Field(min_length=1, max_length=100)


class EntityArgs(BaseModel):
    terms: list[str] = Field(min_length=1, max_length=30)


TOOL_ARGS = {"hybrid_search": SearchArgs, "list_documents": ListDocsArgs, "fetch_document": FetchArgs,
             "entity_lookup": EntityArgs}

TOOL_DESCRIPTIONS = {
    "hybrid_search": "Keyword+vector search over documents the user may read. Returns up to top_k passages.",
    "list_documents": "Metadata scan: documents linked to the given initiatives within a date window.",
    "fetch_document": "Read all passages of one accessible document.",
    "entity_lookup": "Map topic words or names to known initiatives (with aliases).",
}


class ToolResult(BaseModel):
    tool: str
    status: Literal["ok", "empty", "error", "skipped"]
    data: Any = None
    hint: str = ""
    duration_ms: int = 0
    n: int = 0
