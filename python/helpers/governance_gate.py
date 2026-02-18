from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

from python.helpers.errors import RepairableException
from python.governance_runtime.repos import (
    get_persist_backend,
    get_postgres_repo,
    is_dual_write_enabled,
    is_postgres_backend_enabled,
)

GATE_TOKEN_KEY = "__governance_gate_evaluated"
TOOL_CALL_HASH_KEY = "__governance_tool_call_hash"


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _sanitize_tool_args(tool_args: dict[str, Any]) -> dict[str, Any]:
    return {
        k: v
        for k, v in tool_args.items()
        if not str(k).startswith("__governance_")
    }


def _deterministic_tool_call_hash(project_name: str, tool_name: str, tool_args: dict[str, Any]) -> str:
    payload = {
        "project": project_name,
        "tool": tool_name,
        "args": _sanitize_tool_args(tool_args),
    }
    return hashlib.sha256(_stable_json(payload).encode("utf-8")).hexdigest()


def _resolve_governance_storage_dir() -> Path:
    env_override = os.environ.get("A0_GOVERNANCE_DIR", "").strip()
    candidates = []
    if env_override:
        candidates.append(Path(env_override))
    candidates.extend(
        [
            Path("/opt/agentzero/data/a0/usr/governance"),
            Path("/tmp/agentzero/governance"),
        ]
    )
    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            return candidate
        except Exception:
            continue
    raise RuntimeError("Unable to initialize governance storage directory")


def _approval_file_path(approval_id: str) -> Path:
    base = _resolve_governance_storage_dir() / "approvals"
    base.mkdir(parents=True, exist_ok=True)
    return base / f"{approval_id}.json"


def _append_governance_event(event: dict[str, Any]) -> None:
    wrote_postgres = False
    if is_postgres_backend_enabled():
        repo = get_postgres_repo()
        if repo is not None:
            try:
                repo.append_event(event)
                wrote_postgres = True
            except Exception:
                wrote_postgres = False
    if wrote_postgres and not is_dual_write_enabled():
        return

    base = _resolve_governance_storage_dir() / "events"
    base.mkdir(parents=True, exist_ok=True)
    day_file = base / f"events-{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d')}.jsonl"
    with day_file.open("a", encoding="utf-8") as f:
        f.write(_stable_json(event) + "\n")


def _load_project_governance(agent: Any) -> dict[str, Any]:
    from python.helpers import projects

    context = getattr(agent, "context", None)
    project_name = projects.get_context_project_name(context) if context else None
    if not project_name:
        return {
            "project_name": None,
            "governance_enabled": False,
            "mode": "autonomy",
            "require_approval_for": [],
            "tool_overrides": {},
            "default_policy": "allow",
        }

    project_data = projects.load_basic_project_data(project_name)
    governance = project_data.get("governance") if isinstance(project_data, dict) else None
    if not isinstance(governance, dict):
        governance = {}

    policy = project_data.get("policy_config") if isinstance(project_data, dict) else None
    if not isinstance(policy, dict):
        policy = {
            "require_approval_for": governance.get("require_approval_for", ["high", "critical"]),
            "default_policy": governance.get("default_policy", "allow"),
            "policy_file": governance.get("policy_file", "governance/config/policy.json"),
            "allow_readonly_terminal_without_approval": False,
            "tool_overrides": {},
        }

    enabled = bool(project_data.get("governance_enabled", governance.get("enabled", False)))
    mode = str(project_data.get("governance_mode", governance.get("mode", "standard"))).lower().strip()
    if mode not in {"autonomy", "standard", "strict", "custom"}:
        mode = "standard"

    req = policy.get("require_approval_for", ["high", "critical"])
    if not isinstance(req, list):
        req = ["high", "critical"]
    require_approval_for = [str(x).lower().strip() for x in req if str(x).strip()]

    tool_overrides = policy.get("tool_overrides", {})
    if not isinstance(tool_overrides, dict):
        tool_overrides = {}

    default_policy = str(policy.get("default_policy", "allow")).lower().strip()
    if default_policy not in {"allow", "deny"}:
        default_policy = "allow"
    allow_readonly_terminal_without_approval = bool(
        policy.get("allow_readonly_terminal_without_approval", False)
    )

    return {
        "project_name": project_name,
        "governance_enabled": enabled,
        "mode": mode,
        "require_approval_for": require_approval_for,
        "allow_readonly_terminal_without_approval": allow_readonly_terminal_without_approval,
        "tool_overrides": tool_overrides,
        "default_policy": default_policy,
    }


_READ_ONLY_TERMINAL_COMMANDS = {
    "awk",
    "cat",
    "cut",
    "date",
    "df",
    "du",
    "echo",
    "env",
    "file",
    "find",
    "grep",
    "head",
    "id",
    "ls",
    "printenv",
    "printf",
    "pwd",
    "rg",
    "sed",
    "sort",
    "stat",
    "tail",
    "uname",
    "uniq",
    "wc",
    "which",
    "whoami",
}

_GIT_READ_ONLY_SUBCOMMANDS = {
    "branch",
    "diff",
    "log",
    "ls-files",
    "remote",
    "rev-parse",
    "show",
    "status",
}

_SHELL_SPLIT_RE = re.compile(r"(?:&&|\|\||;|\n)+")


def _is_read_only_terminal_command(code: Any) -> bool:
    if not isinstance(code, str):
        return False
    command = code.strip()
    if not command:
        return False

    # Block shell features that can cause side-effects or hide intent.
    if any(token in command for token in [">", "<", "`", "$(", ">>"]):
        return False

    segments = [seg.strip() for seg in _SHELL_SPLIT_RE.split(command) if seg.strip()]
    if not segments:
        return False

    for segment in segments:
        parts = [p for p in segment.split() if p]
        if not parts:
            continue

        # Skip env assignments at the front of the command.
        while parts and "=" in parts[0] and not parts[0].startswith("-"):
            parts = parts[1:]
        if not parts:
            return False

        if parts[0] == "sudo":
            parts = parts[1:]
            if not parts:
                return False

        cmd = parts[0].lower()
        if cmd == "git":
            if len(parts) < 2:
                return False
            sub = parts[1].lower()
            if sub not in _GIT_READ_ONLY_SUBCOMMANDS:
                return False
            if sub == "remote" and len(parts) >= 3 and parts[2].lower() != "show":
                return False
            continue

        if cmd == "sed":
            # treat in-place edits as mutating
            if any(flag == "-i" or flag.startswith("-i") for flag in parts[1:]):
                return False

        if cmd not in _READ_ONLY_TERMINAL_COMMANDS:
            return False

    return True


def _risk_for_tool(tool_name: str, tool_args: dict[str, Any], policy: dict[str, Any]) -> tuple[str, bool]:
    # base policy mapping
    risk_map = {
        "browser_agent": "critical",
        "memory_delete": "medium",
        "memory_save": "medium",
        "a2a_chat": "medium",
        "slack": "medium",
        "search_engine": "low",
        "document_query": "low",
        "vision_load": "low",
        "input": "high",
    }

    # code_execution_tool risk depends on runtime
    if tool_name == "code_execution_tool":
        runtime = str(tool_args.get("runtime", "")).strip().lower()
        if runtime == "terminal":
            if bool(policy.get("allow_readonly_terminal_without_approval")) and _is_read_only_terminal_command(
                tool_args.get("code")
            ):
                return "low", False
            return "critical", False
        if runtime in {"python", "nodejs"}:
            return "high", False
        return "high", False

    if tool_name in risk_map:
        return risk_map[tool_name], False

    if tool_name == "gh":
        method = str(tool_args.get("method", "")).strip().lower()
        if method in {"repo_view", "issue_list", "pr_list", "pr_view"}:
            return "low", False
        return "high", False

    overrides = policy.get("tool_overrides", {})
    if isinstance(overrides, dict):
        override = overrides.get(tool_name)
        if isinstance(override, dict):
            risk = str(override.get("risk", "")).lower().strip()
            if risk in {"low", "medium", "high", "critical"}:
                return risk, False

    return "unknown", True


def _resolve_decision(mode: str, risk: str, unknown_tool: bool, require_approval_for: list[str], default_policy: str) -> str:
    if mode == "autonomy":
        return "allow"

    if unknown_tool:
        if mode == "strict":
            return "deny"
        # standard/custom default to explicit approval for unknown tools
        return "require_approval"

    if risk in require_approval_for:
        return "require_approval"

    if mode == "strict" and risk == "medium":
        return "require_approval"

    if default_policy == "deny" and risk not in {"low"}:
        return "deny"

    return "allow"


def _persist_approval_if_needed(agent: Any, *, project_name: str, tool_name: str, tool_args: dict[str, Any], risk: str, tool_call_hash: str) -> str:
    approval_id = f"apv_{tool_call_hash[:16]}"
    path: Path | None = None

    payload = {
        "approval_id": approval_id,
        "project_name": project_name,
        "tool_name": tool_name,
        "tool_args": _sanitize_tool_args(tool_args),
        "risk": risk,
        "tool_call_hash": tool_call_hash,
        "status": "pending",
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }

    existing_db_status = "pending"
    if is_postgres_backend_enabled():
        repo = get_postgres_repo()
        if repo is not None:
            try:
                existing_db_status = repo.get_approval_status(approval_id)
            except Exception:
                existing_db_status = "pending"
        if existing_db_status in {"approved", "denied"}:
            return approval_id
    write_file = get_persist_backend() != "postgres" or is_dual_write_enabled()
    if write_file:
        path = _approval_file_path(approval_id)
    if write_file and path is not None and path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            existing = None
        if isinstance(existing, dict):
            status = str(existing.get("status", "pending")).lower().strip()
            if status in {"approved", "denied"}:
                return approval_id
            payload.update(existing)
            payload["status"] = "pending"
            payload["updated_at"] = _now_iso()

    wrote_postgres = False
    if is_postgres_backend_enabled():
        repo = get_postgres_repo()
        if repo is not None:
            try:
                repo.upsert_approval(payload)
                wrote_postgres = True
            except Exception:
                wrote_postgres = False
    if write_file or not wrote_postgres:
        if path is None:
            path = _approval_file_path(approval_id)
        path.write_text(_stable_json(payload), encoding="utf-8")

    event = {
        "type": "approval.requested",
        "created_at": _now_iso(),
        "approval_id": approval_id,
        "project_name": project_name,
        "tool_name": tool_name,
        "risk": risk,
        "tool_call_hash": tool_call_hash,
        "tool_args": _sanitize_tool_args(tool_args),
    }
    _append_governance_event(event)

    context = getattr(agent, "context", None)
    if context is not None:
        context.paused = True
        try:
            context.log.log(
                type="governance_approval_requested",
                heading=f"Governance approval requested: {tool_name}",
                content="Tool execution paused pending approval.",
                kvps={
                    "approval_id": approval_id,
                    "tool_name": tool_name,
                    "risk": risk,
                    "tool_args": _sanitize_tool_args(tool_args),
                },
            )
        except Exception:
            pass
        try:
            from python.helpers import persist_chat

            persist_chat.save_tmp_chat(context)
        except Exception:
            pass

    return approval_id


def _load_approval_status(approval_id: str) -> str:
    if is_postgres_backend_enabled():
        repo = get_postgres_repo()
        if repo is not None:
            try:
                return repo.get_approval_status(approval_id)
            except Exception:
                pass

    path = _approval_file_path(approval_id)
    if not path.exists():
        return "pending"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return "pending"
    return str(payload.get("status", "pending")).lower().strip()


def is_governance_enabled(agent: Any) -> bool:
    policy = _load_project_governance(agent)
    return bool(policy.get("governance_enabled"))


def evaluate_tool_gate(agent: Any, tool_name: str, tool_args: dict[str, Any] | None = None) -> dict[str, Any]:
    args = tool_args if isinstance(tool_args, dict) else {}
    policy = _load_project_governance(agent)
    project_name = str(policy.get("project_name") or "")

    if not policy.get("governance_enabled"):
        token = f"gov_off_{hashlib.sha256(str(tool_name).encode('utf-8')).hexdigest()[:16]}"
        return {
            "decision": "allow",
            "risk": "none",
            "mode": policy.get("mode", "autonomy"),
            "token": token,
            "approval_id": None,
            "tool_call_hash": "",
        }

    risk, unknown_tool = _risk_for_tool(tool_name, args, policy)
    is_readonly_terminal = (
        tool_name == "code_execution_tool"
        and str(args.get("runtime", "")).strip().lower() == "terminal"
        and _is_read_only_terminal_command(args.get("code"))
    )

    override_decision: str | None = None
    overrides = policy.get("tool_overrides", {})
    if isinstance(overrides, dict):
        override = overrides.get(tool_name)
        if isinstance(override, dict):
            decision_raw = str(override.get("decision", "")).lower().strip()
            if decision_raw in {"allow", "deny", "require_approval"}:
                override_decision = decision_raw

    if override_decision:
        decision = override_decision
    elif bool(policy.get("allow_readonly_terminal_without_approval")) and is_readonly_terminal:
        decision = "allow"
    else:
        decision = _resolve_decision(
            str(policy.get("mode", "standard")),
            risk,
            unknown_tool,
            list(policy.get("require_approval_for", ["high", "critical"])),
            str(policy.get("default_policy", "allow")),
        )

    tool_call_hash = _deterministic_tool_call_hash(project_name, tool_name, args)
    token = f"gov_{tool_call_hash[:20]}"
    approval_id: str | None = None

    if decision == "require_approval":
        approval_id = _persist_approval_if_needed(
            agent,
            project_name=project_name,
            tool_name=tool_name,
            tool_args=args,
            risk=risk,
            tool_call_hash=tool_call_hash,
        )
        status = _load_approval_status(approval_id)
        if status == "approved":
            decision = "allow"
        elif status == "denied":
            decision = "deny"

    if decision == "deny":
        try:
            agent.context.log.log(
                type="governance_denied",
                heading=f"Governance denied: {tool_name}",
                content="Tool execution denied by governance policy.",
                kvps={"tool_name": tool_name, "risk": risk},
            )
        except Exception:
            pass

    return {
        "decision": decision,
        "risk": risk,
        "readonly_terminal": is_readonly_terminal,
        "mode": policy.get("mode", "standard"),
        "token": token,
        "approval_id": approval_id,
        "tool_call_hash": tool_call_hash,
    }


def enforce_tool_gate_or_raise(agent: Any, tool_name: str, tool_args: dict[str, Any] | None = None) -> dict[str, Any]:
    gate = evaluate_tool_gate(agent, tool_name, tool_args or {})
    decision = str(gate.get("decision", "allow"))
    if decision == "allow":
        return gate
    if decision == "require_approval":
        raise RepairableException(
            "Governance approval required before tool execution. "
            f"tool={tool_name} risk={gate.get('risk', 'unknown')} "
            f"approval_id={gate.get('approval_id', '')}"
        )
    raise RepairableException(
        "Governance denied tool execution. "
        f"tool={tool_name} risk={gate.get('risk', 'unknown')}"
    )


def assert_governance_provenance(agent: Any, tool_args: dict[str, Any]) -> None:
    if not is_governance_enabled(agent):
        return
    token = str(tool_args.get(GATE_TOKEN_KEY, "")).strip()
    if not token:
        raise RepairableException(
            "Governance provenance assertion failed: missing gate token on governed code execution."
        )



def resolve_approval(agent: Any, approval_id: str, decision: str, rationale: str = "") -> dict[str, Any]:
    decision_norm = str(decision or "").lower().strip()
    if decision_norm not in {"approved", "denied", "reject", "rejected"}:
        raise RepairableException(f"Invalid approval decision: {decision}")

    status = "approved" if decision_norm == "approved" else "denied"
    payload: dict[str, Any] | None = None
    write_file = get_persist_backend() != "postgres" or is_dual_write_enabled()

    if is_postgres_backend_enabled():
        repo = get_postgres_repo()
        if repo is not None:
            try:
                payload = repo.resolve_approval(approval_id, status, rationale or "")
            except Exception:
                payload = None

    if write_file:
        path = _approval_file_path(approval_id)
        if not path.exists() and payload is None:
            raise RepairableException(f"Approval not found: {approval_id}")
        file_payload: dict[str, Any]
        if path.exists():
            file_payload = json.loads(path.read_text(encoding="utf-8"))
        else:
            file_payload = {
                "approval_id": approval_id,
                "project_name": (payload or {}).get("project_name"),
                "tool_name": (payload or {}).get("tool_name"),
                "risk": (payload or {}).get("risk"),
                "tool_call_hash": (payload or {}).get("tool_call_hash"),
                "tool_args": {},
                "created_at": _now_iso(),
            }
        file_payload["status"] = status
        file_payload["rationale"] = rationale or ""
        file_payload["updated_at"] = _now_iso()
        path.write_text(_stable_json(file_payload), encoding="utf-8")
        payload = file_payload
    elif payload is None:
        raise RepairableException(f"Approval not found: {approval_id}")

    event = {
        "type": "approval.resolved",
        "created_at": _now_iso(),
        "approval_id": approval_id,
        "status": status,
        "rationale": rationale or "",
        "project_name": (payload or {}).get("project_name"),
        "tool_name": (payload or {}).get("tool_name"),
        "risk": (payload or {}).get("risk"),
        "tool_call_hash": (payload or {}).get("tool_call_hash"),
    }
    _append_governance_event(event)

    context = getattr(agent, "context", None)
    if context is not None:
        context.paused = False
        try:
            context.log.log(
                type="governance_approval_resolved",
                heading=f"Governance approval {status}: {payload.get('tool_name', '')}",
                content=f"Approval {approval_id} {status}.",
                kvps={
                    "approval_id": approval_id,
                    "status": status,
                    "rationale": rationale or "",
                },
            )
        except Exception:
            pass
        try:
            from python.helpers import persist_chat
            persist_chat.save_tmp_chat(context)
        except Exception:
            pass

    return {
        "approval_id": approval_id,
        "status": status,
        "rationale": rationale or "",
    }



def _project_matches(payload: dict[str, Any], project_name: str | None) -> bool:
    if not project_name:
        return True
    return str(payload.get("project_name", "")).strip() == str(project_name).strip()


def load_governance_approvals(project_name: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
    if is_postgres_backend_enabled():
        repo = get_postgres_repo()
        if repo is not None:
            try:
                return repo.load_approvals(project_name=project_name, limit=limit)
            except Exception:
                pass

    base = _resolve_governance_storage_dir() / "approvals"
    if not base.exists():
        return []

    items: list[dict[str, Any]] = []
    for path in sorted(base.glob("apv_*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        if not _project_matches(payload, project_name):
            continue
        items.append(payload)

    items.sort(key=lambda x: str(x.get("updated_at", x.get("created_at", ""))), reverse=True)
    return items[: max(0, int(limit))]


def load_governance_events(project_name: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
    if is_postgres_backend_enabled():
        repo = get_postgres_repo()
        if repo is not None:
            try:
                return repo.load_events(project_name=project_name, limit=limit)
            except Exception:
                pass

    base = _resolve_governance_storage_dir() / "events"
    if not base.exists():
        return []

    events: list[dict[str, Any]] = []
    files = sorted(base.glob("events-*.jsonl"), reverse=True)
    for path in files:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except Exception:
            continue
        for line in reversed(lines):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except Exception:
                continue
            if not isinstance(payload, dict):
                continue
            if not _project_matches(payload, project_name):
                continue
            events.append(payload)
            if len(events) >= limit:
                return events

    return events[: max(0, int(limit))]
