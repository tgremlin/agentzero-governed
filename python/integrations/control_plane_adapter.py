from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from python.integrations.control_plane_client import ControlPlaneClient, ControlPlaneClientError
from python.integrations.control_plane_config import ControlPlaneConfig
from python.integrations.control_plane_events import now_iso
from python.integrations.control_plane_redaction import compact_json, sanitize_payload

CTX_KEY_STATE = "_cp_adapter_state"


@dataclass(frozen=True)
class ToolDecisionResult:
    decision: str
    status: str
    run_status: str
    approval_id: str
    raw: dict[str, Any]


class ControlPlaneAdapter:
    def __init__(self, agent: Any, *, config: ControlPlaneConfig | None = None, client: ControlPlaneClient | None = None):
        self.agent = agent
        self.config = config or ControlPlaneConfig.load()
        self.client = client or ControlPlaneClient(base_url=self.config.api_url)
        self._config_error: str = ""
        if self.config.adapter_enabled:
            try:
                self.config.validate()
            except Exception as exc:
                self._config_error = str(exc)
                self._log_startup_diagnostics()
                raise ControlPlaneClientError(
                    f"control-plane adapter configuration invalid: {self._config_error}"
                ) from exc
        self._log_startup_diagnostics()

    @property
    def enabled(self) -> bool:
        return bool(self.config.adapter_enabled and not self._config_error)

    @property
    def config_error(self) -> str:
        return self._config_error

    def _state(self) -> dict[str, Any]:
        state = self.agent.context.get_data(CTX_KEY_STATE)
        if isinstance(state, dict):
            return state
        state = {
            "run_id": "",
            "event_seq": 0,
            "executed_tool_calls": [],
            "consumed_approvals": [],
            "approval_terminal": {},
            "last_error": "",
        }
        self.agent.context.set_data(CTX_KEY_STATE, state)
        return state

    def _set_state(self, state: dict[str, Any]) -> None:
        self.agent.context.set_data(CTX_KEY_STATE, state)

    def correlation(self) -> dict[str, Any]:
        return {
            "context_id": str(getattr(self.agent.context, "id", "") or ""),
            "thread_id": str(getattr(self.agent.context, "id", "") or ""),
            "agent": str(getattr(self.agent, "agent_name", "A0") or "A0"),
            "context_name": str(getattr(self.agent.context, "name", "") or ""),
        }

    def _runner_token(self) -> str:
        return self.config.runner_token

    def _ingestor_token(self) -> str:
        if self.config.ingestor_token:
            return self.config.ingestor_token
        if self.config.strict_mode:
            raise ControlPlaneClientError("CP_ADAPTER_STRICT_MODE requires CP_INGESTOR_TOKEN")
        self._safe_log("warning", "control-plane adapter using runner token for events ingest (non-strict mode)")
        return self.config.runner_token

    def _safe_log(self, level: str, message: str) -> None:
        log = getattr(getattr(self.agent, "context", None), "log", None)
        if log and hasattr(log, "log"):
            try:
                log.log(type=level, content=message)
            except Exception:
                pass

    def _log_startup_diagnostics(self) -> None:
        token_split = bool(self.config.runner_token and self.config.ingestor_token and self.config.runner_token != self.config.ingestor_token)
        self._safe_log(
            "info",
            (
                "control-plane adapter init: "
                f"enabled={self.config.adapter_enabled and not self._config_error} "
                f"strict_mode={self.config.strict_mode} "
                f"api_url={self.config.api_url or '<unset>'} "
                f"profile={self.config.execution_profile} "
                f"llm_gateway_enabled={bool(self.config.llm_gateway_url)} "
                f"token_split_distinct={token_split}"
            ),
        )

    def ensure_run_started(self) -> str:
        if not self.enabled:
            return ""

        state = self._state()
        existing = str(state.get("run_id", "") or "").strip()
        if existing:
            return existing

        payload: dict[str, Any] = {
            "tenant_id": self.config.tenant_id,
            "deployment_id": self.config.deployment_id,
            "tags": self._build_run_tags(),
            "execution_profile": self.config.execution_profile,
            "adapter_metadata": {
                **self.correlation(),
                "source": "agentzero-control-plane-adapter",
                "source_framework": "agentzero",
                "source_adapter": "control_plane_adapter",
                "source_context_id": str(getattr(self.agent.context, "id", "") or ""),
                "source_thread_id": str(getattr(self.agent.context, "id", "") or ""),
            },
        }
        if self.config.project_id:
            payload["project_id"] = self.config.project_id

        _, body = self.client.request_json("POST", "/v1/runs", token=self._runner_token(), payload=payload)
        run_id = self._pick_id(body, keys=("run_id", "id"))
        if not run_id:
            raise ControlPlaneClientError("control-plane run creation returned no run_id", body=str(body))

        state["run_id"] = run_id
        state["event_seq"] = 0
        self._set_state(state)

        correlation_payload = {
            "cp_run_id": run_id,
            "adapter_version": self._adapter_version(),
            "correlation": self.correlation(),
            "correlation_tags": self._build_run_tags(),
        }
        self.emit_event(
            "run.started",
            {"execution_profile": self.config.execution_profile, **correlation_payload},
        )
        self.emit_event("run.correlation", correlation_payload)
        return run_id

    def _adapter_version(self) -> str:
        try:
            with open("VERSION", "r", encoding="utf-8") as fh:
                return str(fh.read().strip() or "unknown")
        except Exception:
            return "unknown"

    def _build_run_tags(self) -> list[str]:
        tags = ["agentzero", "adapter:control-plane"]
        context_id = str(getattr(self.agent.context, "id", "") or "").strip()
        prefix = str(self.config.run_tag_prefix or "agentzero").strip().lower()
        if prefix:
            if context_id:
                tags.append(f"{prefix}:{context_id}")
            else:
                tags.append(prefix)
        if self.config.canary_correlation_tag:
            tags.append(self.config.canary_correlation_tag)
        # preserve order while removing duplicates/empties
        unique: list[str] = []
        for tag in tags:
            candidate = str(tag or "").strip()
            if candidate and candidate not in unique:
                unique.append(candidate)
        return unique

    def run_tags(self) -> list[str]:
        return self._build_run_tags()

    def run_id(self) -> str:
        return str(self._state().get("run_id", "") or "")

    def next_sequence(self) -> int:
        state = self._state()
        seq = int(state.get("event_seq", 0)) + 1
        state["event_seq"] = seq
        self._set_state(state)
        return seq

    def _event_envelope(self, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        run_id = self.run_id()
        if not run_id:
            raise ControlPlaneClientError("cannot emit events before run_id is initialized")
        return {
            "tenant_id": self.config.tenant_id,
            "deployment_id": self.config.deployment_id,
            "run_id": run_id,
            "sequence_number": self.next_sequence(),
            "event_type": event_type,
            "event_ts": now_iso(),
            "payload": sanitize_payload(payload),
        }

    def emit_event(self, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.enabled:
            return {"accepted": 0, "rejected": 0}

        run_id = self.ensure_run_started()
        request_payload = {
            "tenant_id": self.config.tenant_id,
            "deployment_id": self.config.deployment_id,
            "run_id": run_id,
            "events": [self._event_envelope(event_type, payload)],
        }
        _, body = self.client.request_json(
            "POST",
            "/v1/events:ingest",
            token=self._ingestor_token(),
            payload=request_payload,
        )
        return body if isinstance(body, dict) else {"accepted": 0, "rejected": 1}

    def emit_events(self, events: list[dict[str, Any]]) -> dict[str, Any]:
        if not self.enabled or not events:
            return {"accepted": 0, "rejected": 0}

        run_id = self.ensure_run_started()
        payload_events = [
            self._event_envelope(str(item.get("event_type", "governance.event")), dict(item.get("payload", {})))
            for item in events
        ]
        request_payload = {
            "tenant_id": self.config.tenant_id,
            "deployment_id": self.config.deployment_id,
            "run_id": run_id,
            "events": payload_events,
        }
        _, body = self.client.request_json(
            "POST",
            "/v1/events:ingest",
            token=self._ingestor_token(),
            payload=request_payload,
        )
        return body if isinstance(body, dict) else {"accepted": 0, "rejected": len(payload_events)}

    def infer_tool_risk(self, tool_name: str, tool_args: dict[str, Any]) -> str:
        name = str(tool_name or "").strip().lower()
        if name in {"browser_agent", "input"}:
            return "critical"
        if name in {"slack", "a2a_chat", "memory_delete", "memory_save"}:
            return "medium"
        if name == "code_execution_tool":
            runtime = str((tool_args or {}).get("runtime", "")).strip().lower()
            if runtime == "terminal":
                return "critical"
            return "high"
        if name in {"search_engine", "document_query", "vision_load", "gh"}:
            return "low"
        return "high"

    def compute_tool_call_hash(self, tool_name: str, tool_args: dict[str, Any]) -> str:
        return self.build_tool_dedupe_key(tool_name=tool_name, tool_args=tool_args)

    def build_tool_dedupe_key(self, *, tool_name: str, tool_args: dict[str, Any]) -> str:
        """Best-effort in-process dedupe key for exactly-once tool execution.

        Guarantees apply within this process/context lifetime only. Cross-process recovery
        still requires control-plane-side idempotency and persistent command handling.
        """
        run_id = self.ensure_run_started() or self.run_id() or "unscoped"
        context_id = str(getattr(self.agent.context, "id", "") or "")
        normalized = {
            "run_id": run_id,
            "context_id": context_id,
            "tool_name": str(tool_name or "").strip().lower(),
            "tool_args": sanitize_payload(tool_args or {}),
        }
        import hashlib

        return hashlib.sha256(compact_json(normalized).encode("utf-8")).hexdigest()

    def mark_tool_executed_once(self, call_hash: str) -> bool:
        state = self._state()
        seen = state.get("executed_tool_calls")
        if not isinstance(seen, list):
            seen = []
        if call_hash in seen:
            return False
        seen.append(call_hash)
        state["executed_tool_calls"] = seen[-500:]
        self._set_state(state)
        return True

    def mark_approval_consumed_once(self, approval_id: str) -> bool:
        key = str(approval_id or "").strip()
        if not key:
            return False
        state = self._state()
        consumed = state.get("consumed_approvals")
        if not isinstance(consumed, list):
            consumed = []
        if key in consumed:
            return False
        consumed.append(key)
        state["consumed_approvals"] = consumed[-500:]
        self._set_state(state)
        return True

    def decide_tool(
        self,
        *,
        tool_name: str,
        tool_args: dict[str, Any],
        action: str,
        risk: str,
    ) -> ToolDecisionResult:
        run_id = self.ensure_run_started()
        payload: dict[str, Any] = {
            "tenant_id": self.config.tenant_id,
            "deployment_id": self.config.deployment_id,
            "run_id": run_id,
            "action": action,
            "tool_name": tool_name,
            "tool_args": sanitize_payload(tool_args),
            "risk": risk,
            "profile": self.config.execution_profile,
        }
        _, body = self.client.request_json(
            "POST",
            "/v1/runtime/tool-decisions",
            token=self._runner_token(),
            payload=payload,
        )
        obj = body if isinstance(body, dict) else {}
        return ToolDecisionResult(
            decision=str(obj.get("decision", "deny") or "deny"),
            status=str(obj.get("status", "denied") or "denied"),
            run_status=str(obj.get("run_status", "") or ""),
            approval_id=str(obj.get("approval_id", "") or ""),
            raw=obj,
        )

    def wait_for_approval(self, approval_id: str) -> str:
        if not approval_id:
            return "denied"

        delay = self.config.poll_initial_seconds
        deadline = time.time() + self.config.poll_timeout_seconds
        while time.time() < deadline:
            _, body = self.client.request_json(
                "GET",
                f"/v1/approvals/{approval_id}",
                token=self._runner_token(),
            )
            status = str((body or {}).get("status", "pending")).strip().lower()
            self.record_approval_status(approval_id=approval_id, status=status)
            if status in {"approved", "denied", "cancelled", "canceled", "expired", "timed_out", "timeout"}:
                return status
            time.sleep(delay)
            delay = min(self.config.poll_max_seconds, max(0.2, delay * 1.5))

        return "timeout"

    def record_approval_status(self, *, approval_id: str, status: str) -> bool:
        key = str(approval_id or "").strip()
        if not key:
            return False
        normalized = str(status or "").strip().lower()
        if normalized not in {"approved", "denied", "cancelled", "canceled", "expired", "timed_out", "timeout"}:
            return False
        state = self._state()
        observed = state.get("approval_terminal")
        if not isinstance(observed, dict):
            observed = {}
        previous = str(observed.get(key, "")).strip().lower()
        observed[key] = normalized
        state["approval_terminal"] = observed
        self._set_state(state)
        return previous != normalized

    def complete_run(self, *, reason: str = "") -> None:
        if not self.enabled or not self.run_id():
            return
        self.emit_event("run.completed", {"reason": reason or "completed"})

    def fail_run(self, *, reason: str) -> None:
        if not self.enabled or not self.run_id():
            return
        self.emit_event("run.failed", {"reason": reason})

    def route_llm_call(
        self,
        *,
        model: str,
        prompt: str,
        risk: str,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[bool, str, str]:
        """Returns (handled, output, decision)."""
        if not self.enabled:
            return False, "", ""
        if not self.config.llm_gateway_url:
            return False, "", ""

        payload = {
            "tenant_id": self.config.tenant_id,
            "run_id": self.ensure_run_started(),
            "model": model,
            "prompt": prompt,
            "risk": risk,
            "profile": self.config.execution_profile,
            "metadata": sanitize_payload(metadata or {}),
        }
        token = self.config.llm_gateway_token or self._runner_token()
        headers_token = token

        from urllib.request import Request, urlopen
        from urllib.error import HTTPError, URLError
        import json

        req = Request(
            f"{self.config.llm_gateway_url}/v1/llm/request",
            method="POST",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {headers_token}",
                "Content-Type": "application/json; charset=utf-8",
            },
        )
        try:
            with urlopen(req, timeout=45) as resp:
                parsed = json.loads(resp.read().decode("utf-8"))
        except (HTTPError, URLError, json.JSONDecodeError):
            return False, "", ""

        if not isinstance(parsed, dict):
            return False, "", ""
        status = str(parsed.get("status", "")).lower()
        decision = str(parsed.get("decision", "")).lower()
        if status == "ok" and decision == "allow":
            return True, str(parsed.get("output", "")), decision
        return True, "", decision

    @staticmethod
    def _pick_id(payload: Any, *, keys: tuple[str, ...]) -> str:
        if isinstance(payload, dict):
            for key in keys:
                value = payload.get(key)
                if isinstance(value, str) and value:
                    return value
            for value in payload.values():
                found = ControlPlaneAdapter._pick_id(value, keys=keys)
                if found:
                    return found
        if isinstance(payload, list):
            for item in payload:
                found = ControlPlaneAdapter._pick_id(item, keys=keys)
                if found:
                    return found
        return ""
