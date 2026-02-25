from __future__ import annotations

import datetime as dt
import hashlib
from typing import Any

from python.integrations.control_plane_redaction import compact_json, sanitize_payload


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def tool_call_hash(*, run_id: str, tool_name: str, tool_args: dict[str, Any]) -> str:
    material = {
        "run_id": run_id,
        "tool_name": tool_name,
        "tool_args": sanitize_payload(tool_args),
    }
    return hashlib.sha256(compact_json(material).encode("utf-8")).hexdigest()
