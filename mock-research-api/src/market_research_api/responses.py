from __future__ import annotations

from typing import Any


SCHEMA_VERSION = 1
SOURCE = "mock-research-api"


def ok(data: Any, *, as_of: str = "", extra_meta: dict[str, Any] | None = None) -> dict[str, Any]:
    meta = {
        "row_count": len(data) if isinstance(data, list) else 1,
        "source": SOURCE,
        "as_of": as_of,
    }
    if extra_meta:
        meta.update(extra_meta)
    return {"schema_version": SCHEMA_VERSION, "data": data, "meta": meta}


def error(code: str, message: str) -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "error": {"code": code, "message": message}}
