from __future__ import annotations

import os
from dataclasses import dataclass


def _is_true(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class ControlPlaneConfig:
    adapter_enabled: bool
    strict_mode: bool
    api_url: str
    deployment_id: str
    tenant_id: str
    project_id: str
    runner_token: str
    ingestor_token: str
    execution_profile: str
    run_tag_prefix: str
    canary_correlation_tag: str
    llm_gateway_url: str
    llm_gateway_token: str
    tool_gateway_url: str
    poll_initial_seconds: float
    poll_max_seconds: float
    poll_timeout_seconds: float

    @classmethod
    def load(cls) -> "ControlPlaneConfig":
        execution_profile = (os.getenv("CP_EXECUTION_PROFILE") or "standard").strip().lower()
        if execution_profile not in {"standard", "regulated"}:
            execution_profile = "standard"

        return cls(
            adapter_enabled=_is_true(os.getenv("CP_ADAPTER_ENABLED"), default=False),
            strict_mode=_is_true(os.getenv("CP_ADAPTER_STRICT_MODE"), default=False),
            api_url=(os.getenv("CP_API_URL") or "").strip().rstrip("/"),
            deployment_id=(os.getenv("CP_DEPLOYMENT_ID") or "").strip(),
            tenant_id=(os.getenv("CP_TENANT_ID") or "").strip(),
            project_id=(os.getenv("CP_PROJECT_ID") or "").strip(),
            runner_token=(os.getenv("CP_RUNNER_TOKEN") or "").strip(),
            ingestor_token=(os.getenv("CP_INGESTOR_TOKEN") or "").strip(),
            execution_profile=execution_profile,
            run_tag_prefix=(os.getenv("CP_RUN_TAG_PREFIX") or "agentzero").strip() or "agentzero",
            canary_correlation_tag=(os.getenv("CP_CANARY_CORRELATION_TAG") or "").strip(),
            llm_gateway_url=(os.getenv("CP_LLM_GATEWAY_URL") or "").strip().rstrip("/"),
            llm_gateway_token=(os.getenv("CP_LLM_GATEWAY_TOKEN") or "").strip(),
            tool_gateway_url=(os.getenv("CP_TOOL_GATEWAY_URL") or "").strip().rstrip("/"),
            poll_initial_seconds=max(0.1, float(os.getenv("CP_APPROVAL_POLL_INITIAL_SECONDS", "1.0"))),
            poll_max_seconds=max(0.2, float(os.getenv("CP_APPROVAL_POLL_MAX_SECONDS", "5.0"))),
            poll_timeout_seconds=max(5.0, float(os.getenv("CP_APPROVAL_POLL_TIMEOUT_SECONDS", "300"))),
        )

    def validate(self) -> None:
        if not self.adapter_enabled:
            return
        missing: list[str] = []
        if not self.api_url:
            missing.append("CP_API_URL")
        if not self.deployment_id:
            missing.append("CP_DEPLOYMENT_ID")
        if not self.tenant_id:
            missing.append("CP_TENANT_ID")
        if not self.runner_token:
            missing.append("CP_RUNNER_TOKEN")

        if self.strict_mode:
            if not self.ingestor_token:
                missing.append("CP_INGESTOR_TOKEN")
            elif self.ingestor_token == self.runner_token:
                missing.append("CP_INGESTOR_TOKEN(distinct-from-runner)")

        if missing:
            raise ValueError(f"missing control-plane config: {', '.join(missing)}")
