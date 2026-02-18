from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from typing import Any


SCHEMA_VERSION = "1.0.0"
TAXONOMY_VERSION = "2026.02.18"

DEFAULT_TENANT_ID = "tenant_default"
DEFAULT_DEPLOYMENT_ID = "deployment_default"
DEFAULT_ENVIRONMENT = "prod"
DEFAULT_CONSENT_SCOPE = "audit_only"
DEFAULT_ACTOR_ID = "actor_agent_runtime"
DEFAULT_ACTOR_TYPE = "agent"
ALLOWED_ENVIRONMENTS = {"prod", "stage", "dev"}
ALLOWED_CONSENT_SCOPES = {"audit_only", "eval_allowed", "training_allowed"}
ALLOWED_ACTOR_TYPES = {"human_user", "agent", "system", "policy", "tool", "service", "bot"}

_REDACTED_SECRET = "[REDACTED_SECRET]"
_REDACTED_PII = "[REDACTED_PII]"
_INITIAL_CHAIN_HASH = "sha256:0"

_SECRET_KEYS = {
    "token",
    "access_token",
    "refresh_token",
    "authorization",
    "api_key",
    "apikey",
    "password",
    "secret",
    "client_secret",
    "private_key",
    "cookie",
    "session",
}

_SECRET_PATTERNS = [
    re.compile(r"(?i)\bxox[baprs]-[a-z0-9-]{10,}\b"),
    re.compile(r"(?i)\bghp_[a-z0-9]{20,}\b"),
    re.compile(r"(?i)\bgithub_pat_[a-z0-9_]{20,}\b"),
    re.compile(r"(?i)\bbearer\s+[a-z0-9._\-]{20,}\b"),
]

_EMAIL_PATTERN = re.compile(r"(?i)\b[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}\b")


@dataclass
class SanitizationResult:
    payload: dict[str, Any]
    contains_secrets: bool
    contains_pii: bool
    redaction_ratio: float


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def sha256_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normalize_enum(value: Any, allowed: set[str], default: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in allowed:
        return normalized
    return default


def _sanitize_scalar(value: Any, key_hint: str | None) -> tuple[Any, bool, bool, int]:
    if isinstance(value, str):
        key_l = (key_hint or "").lower().strip()
        if key_l in _SECRET_KEYS:
            return _REDACTED_SECRET, True, False, 1

        for pattern in _SECRET_PATTERNS:
            if pattern.search(value):
                return _REDACTED_SECRET, True, False, 1

        if _EMAIL_PATTERN.search(value):
            redacted = _EMAIL_PATTERN.sub(_REDACTED_PII, value)
            return redacted, False, True, 1
    return value, False, False, 0


def _sanitize_value(value: Any, key_hint: str | None = None) -> tuple[Any, bool, bool, int, int]:
    # Returns: value, contains_secret, contains_pii, redactions, total_fields
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        secret = False
        pii = False
        redactions = 0
        total = 0
        for k, v in value.items():
            sanitized, s, p, r, t = _sanitize_value(v, str(k))
            out[str(k)] = sanitized
            secret = secret or s
            pii = pii or p
            redactions += r
            total += t
        return out, secret, pii, redactions, total

    if isinstance(value, list):
        out_list: list[Any] = []
        secret = False
        pii = False
        redactions = 0
        total = 0
        for item in value:
            sanitized, s, p, r, t = _sanitize_value(item, key_hint)
            out_list.append(sanitized)
            secret = secret or s
            pii = pii or p
            redactions += r
            total += t
        return out_list, secret, pii, redactions, total

    sanitized, s, p, r = _sanitize_scalar(value, key_hint)
    return sanitized, s, p, r, 1


def sanitize_payload(payload: dict[str, Any]) -> SanitizationResult:
    if not isinstance(payload, dict):
        payload = {"value": payload}
    sanitized, contains_secrets, contains_pii, redactions, total = _sanitize_value(payload)
    ratio = float(redactions) / float(max(1, total))
    return SanitizationResult(
        payload=sanitized if isinstance(sanitized, dict) else {"value": sanitized},
        contains_secrets=contains_secrets,
        contains_pii=contains_pii,
        redaction_ratio=round(ratio, 6),
    )


def build_audit_event(
    *,
    base_event: dict[str, Any],
    tenant_id: str = DEFAULT_TENANT_ID,
    deployment_id: str = DEFAULT_DEPLOYMENT_ID,
    environment: str = DEFAULT_ENVIRONMENT,
    actor_id: str = DEFAULT_ACTOR_ID,
    actor_type: str = DEFAULT_ACTOR_TYPE,
    consent_scope: str = DEFAULT_CONSENT_SCOPE,
    run_id: str,
    sequence_number: int,
    prev_event_hash: str = _INITIAL_CHAIN_HASH,
    trace_id: str | None = None,
    span_id: str | None = None,
    parent_span_id: str | None = None,
) -> dict[str, Any]:
    environment_norm = _normalize_enum(environment, ALLOWED_ENVIRONMENTS, DEFAULT_ENVIRONMENT)
    actor_type_norm = _normalize_enum(actor_type, ALLOWED_ACTOR_TYPES, DEFAULT_ACTOR_TYPE)
    consent_scope_norm = _normalize_enum(consent_scope, ALLOWED_CONSENT_SCOPES, DEFAULT_CONSENT_SCOPE)
    event_type = str(base_event.get("type", "governance.event")).strip() or "governance.event"
    observed_at = str(base_event.get("created_at") or dt.datetime.now(dt.timezone.utc).isoformat())
    raw_payload = dict(base_event)
    sanitized = sanitize_payload(raw_payload)

    payload_json = {"suppressed": True} if sanitized.contains_secrets else sanitized.payload
    payload_hash = sha256_text(_stable_json(payload_json))
    chain_input = _stable_json(
        {
            "prev_event_hash": prev_event_hash,
            "payload_hash": payload_hash,
            "event_type": event_type,
            "sequence_number": sequence_number,
            "run_id": run_id,
        }
    )
    event_hash = sha256_text(chain_input)

    return {
        "event_id": str(uuid.uuid4()),
        "schema_version": SCHEMA_VERSION,
        "taxonomy_version": TAXONOMY_VERSION,
        "tenant_id": tenant_id,
        "deployment_id": deployment_id,
        "environment": environment_norm,
        "run_id": run_id,
        "sequence_number": int(sequence_number),
        "event_type": event_type,
        "observed_at": observed_at,
        "recorded_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "trace_id": trace_id,
        "span_id": span_id,
        "parent_span_id": parent_span_id,
        "actor_id": actor_id,
        "actor_type": actor_type_norm,
        "subject_kind": str(base_event.get("subject_kind") or ""),
        "subject_name": str(base_event.get("tool_name") or ""),
        "subject_version": str(base_event.get("subject_version") or ""),
        "contract_id": str(base_event.get("contract_id") or ""),
        "payload_json": payload_json,
        "payload_hash": payload_hash,
        "contains_secrets": sanitized.contains_secrets,
        "contains_pii": sanitized.contains_pii,
        "redaction_ratio": sanitized.redaction_ratio,
        "consent_scope": consent_scope_norm,
        "integrity_chain_id": f"{tenant_id}:{run_id}",
        "prev_event_hash": prev_event_hash,
        "event_hash": event_hash,
    }
