import json
import os
import uuid

from python.helpers.api import ApiHandler, Request, Response
from python.helpers import projects
from python.governance_runtime.temporal_client import is_temporal_enabled, start_governed_run
from python.integrations.control_plane_config import ControlPlaneConfig
from python.integrations.control_plane_events import now_iso


def _json_error(payload: dict, status: int) -> Response:
    return Response(
        json.dumps(payload),
        status=status,
        mimetype="application/json",
    )


def _is_true(value: str | None) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _safe_log(context, level: str, message: str) -> None:
    log = getattr(context, "log", None)
    if log and hasattr(log, "log"):
        try:
            log.log(type=level, content=message)
        except Exception:
            pass


class GovernanceRunStart(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict | Response:
        if not is_temporal_enabled():
            return Response(
                '{"error":"temporal governance is disabled (set GOV_TEMPORAL_ENABLED=true)"}',
                status=409,
                mimetype="application/json",
            )

        ctxid = str(input.get("context_id", input.get("context", ""))).strip()
        context = self.use_context(ctxid)
        project_name = projects.get_context_project_name(context)

        result = await start_governed_run(context_id=context.id, project_name=project_name)
        trigger_id = str(uuid.uuid4())
        started_at = now_iso()
        cp_required_requested = not str(input.get("cp_required", "true")).strip().lower() in {"0", "false", "no", "off"}
        allow_trigger_cp_bypass = _is_true(os.getenv("CP_ALLOW_TRIGGER_CP_BYPASS"))
        config = ControlPlaneConfig.load()
        strict_guard = bool(
            config.strict_mode
            or str(config.execution_profile or "standard").lower() == "regulated"
            or bool(config.canary_correlation_tag)
        )

        warnings: list[str] = []
        cp_run_id: str | None = None
        adapter_enabled = False
        execution_profile = str(config.execution_profile or "standard")
        tags_applied: list[str] = []
        correlation_tag = ""

        if not cp_required_requested:
            _safe_log(context, "warning", "governance trigger requested cp_required=false")
            if strict_guard:
                return _json_error(
                    {
                        "ok": False,
                        "error": "cp_required=false is not permitted in strict, canary, or regulated mode",
                        "cp_run_id_required": True,
                        "cp_required_override_allowed": False,
                        "execution_profile": execution_profile,
                        "strict_mode": bool(config.strict_mode),
                        "canary_correlation_tag_present": bool(config.canary_correlation_tag),
                        "trigger_id": trigger_id,
                        "started_at": started_at,
                    },
                    status=400,
                )
            if not allow_trigger_cp_bypass:
                return _json_error(
                    {
                        "ok": False,
                        "error": "cp_required=false is disabled; set CP_ALLOW_TRIGGER_CP_BYPASS=true for dev/debug only",
                        "cp_run_id_required": True,
                        "cp_required_override_allowed": False,
                        "trigger_id": trigger_id,
                        "started_at": started_at,
                    },
                    status=400,
                )
            warnings.append("Compatibility mode: cp_required=false accepted via CP_ALLOW_TRIGGER_CP_BYPASS=true (dev/debug only).")
            _safe_log(context, "warning", "governance trigger accepted cp_required=false via CP_ALLOW_TRIGGER_CP_BYPASS=true")

        agent = getattr(context, "agent0", None)
        adapter = None
        if agent is not None and hasattr(agent, "_cp_adapter"):
            try:
                adapter = agent._cp_adapter()
                execution_profile = str(getattr(getattr(adapter, "config", None), "execution_profile", "standard") or "standard")
                adapter_enabled = bool(getattr(adapter, "enabled", False))
            except Exception as exc:
                if cp_required_requested:
                    return _json_error(
                        {
                            "ok": False,
                            "error": "control-plane adapter initialization failed",
                            "message": str(exc),
                            "cp_run_id_required": True,
                            "adapter_enabled": True,
                            "context_id": context.id,
                            "trigger_id": trigger_id,
                            "started_at": started_at,
                        },
                        status=502,
                    )
                warnings.append(f"control-plane adapter unavailable: {exc}")

        if adapter_enabled:
            try:
                cp_run_id = str(agent._cp_ensure_run_started() or "").strip() if agent is not None else ""
                if hasattr(adapter, "run_tags"):
                    tags_applied = [str(tag) for tag in (adapter.run_tags() or []) if str(tag).strip()]
            except Exception as exc:
                return _json_error(
                    {
                        "ok": False,
                        "error": "control-plane run start failed",
                        "message": str(exc),
                        "cp_run_id_required": True,
                        "adapter_enabled": True,
                        "context_id": context.id,
                        "trigger_id": trigger_id,
                        "started_at": started_at,
                        },
                        status=502,
                    )
            if not cp_run_id:
                if cp_required_requested:
                    return _json_error(
                        {
                            "ok": False,
                            "error": "control-plane adapter enabled but cp_run_id is unavailable",
                            "cp_run_id_required": True,
                            "adapter_enabled": True,
                            "context_id": context.id,
                            "trigger_id": trigger_id,
                            "started_at": started_at,
                        },
                        status=502,
                    )
                warnings.append("control-plane adapter enabled but cp_run_id unavailable; compatibility mode continued.")
            static_tags = {"agentzero", "adapter:control-plane"}
            correlation_tag = next((tag for tag in tags_applied if tag not in static_tags), "")

        governance_run_id = str(result.get("run_id", "")).strip()
        correlation = {
            "tag": correlation_tag or None,
            "tags_applied": tags_applied,
            "context_id": context.id,
            "thread_id": context.id,
            "source_framework": "agentzero",
            "source_adapter": "control_plane_adapter",
        }
        return {
            "ok": True,
            "trigger_id": trigger_id,
            "started_at": started_at,
            "context_id": context.id,
            "project_name": project_name,
            "agentzero_run_id": governance_run_id,
            "governance_run_id": governance_run_id,
            "run_id": governance_run_id,
            "cp_run_id": cp_run_id,
            "adapter_enabled": adapter_enabled,
            "execution_profile": execution_profile,
            "correlation": correlation,
            "warnings": warnings,
            **result,
        }
