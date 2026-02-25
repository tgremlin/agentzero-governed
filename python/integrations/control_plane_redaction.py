from __future__ import annotations

import json
from typing import Any

_REDACT_KEY_TOKENS = {
    "password",
    "passwd",
    "secret",
    "token",
    "authorization",
    "api_key",
    "apikey",
    "access_key",
    "private_key",
    "session",
    "cookie",
}

MAX_STR_LEN = 4096
MAX_LIST_LEN = 100
MAX_DICT_KEYS = 100


def compact_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def sanitize_payload(value: Any) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for idx, (key, item) in enumerate(value.items()):
            if idx >= MAX_DICT_KEYS:
                out["__truncated_keys__"] = max(0, len(value) - MAX_DICT_KEYS)
                break
            key_text = str(key)
            key_lower = key_text.lower()
            if key_lower in _REDACT_KEY_TOKENS or any(token in key_lower for token in _REDACT_KEY_TOKENS):
                out[key_text] = "[REDACTED]"
            else:
                out[key_text] = sanitize_payload(item)
        return out

    if isinstance(value, list):
        if len(value) > MAX_LIST_LEN:
            return [sanitize_payload(item) for item in value[:MAX_LIST_LEN]] + [
                {"__truncated_items__": len(value) - MAX_LIST_LEN}
            ]
        return [sanitize_payload(item) for item in value]

    if isinstance(value, tuple):
        seq = list(value)
        if len(seq) > MAX_LIST_LEN:
            seq = seq[:MAX_LIST_LEN] + [{"__truncated_items__": len(value) - MAX_LIST_LEN}]
        return [sanitize_payload(item) for item in seq]

    if isinstance(value, str):
        if len(value) > MAX_STR_LEN:
            return value[:MAX_STR_LEN] + f"...[truncated {len(value) - MAX_STR_LEN} chars]"
        return value

    return value
