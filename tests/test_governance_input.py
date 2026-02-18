import pytest

from python.helpers.errors import RepairableException
from python.helpers.governance_gate import evaluate_tool_gate
from python.tools.code_execution_tool import CodeExecution
from python.tools.input import Input


class _DummyLog:
    def log(self, **kwargs):
        return self

    def update(self, **kwargs):
        return self


class _DummyContext:
    def __init__(self):
        self.paused = False
        self.log = _DummyLog()


class _DummyAgent:
    def __init__(self):
        self.context = _DummyContext()
        self.agent_name = "A0"

    async def handle_intervention(self):
        return None

    def read_prompt(self, *_args, **_kwargs):
        return ""


@pytest.mark.asyncio
async def test_input_requires_approval_when_governed(monkeypatch):
    from python.helpers import governance_gate

    monkeypatch.setattr(
        governance_gate,
        "evaluate_tool_gate",
        lambda *_args, **_kwargs: {
            "decision": "require_approval",
            "risk": "critical",
            "approval_id": "apv_123",
            "token": "",
            "tool_call_hash": "abc",
        },
    )

    called = {"execute": False}

    async def _execute(*_args, **_kwargs):
        called["execute"] = True
        raise AssertionError("CodeExecution.execute must not run when approval is required")

    monkeypatch.setattr(CodeExecution, "execute", _execute)

    agent = _DummyAgent()
    tool = Input(agent, "input", None, {"session": 0}, "", None)
    resp = await tool.execute(keyboard="echo hi")

    assert resp.message.startswith("Governance approval requested")
    assert called["execute"] is False


def _policy(enabled: bool, mode: str, *, allow_readonly_terminal_without_approval: bool = False):
    return {
        "governance_enabled": enabled,
        "governance_mode": mode,
        "policy_config": {
            "require_approval_for": ["high", "critical"],
            "default_policy": "allow",
            "allow_readonly_terminal_without_approval": allow_readonly_terminal_without_approval,
            "tool_overrides": {},
        },
    }


def test_unknown_tool_semantics_by_mode(monkeypatch):
    from python.helpers import projects

    agent = _DummyAgent()

    monkeypatch.setattr(projects, "get_context_project_name", lambda _ctx: "p1")

    monkeypatch.setattr(projects, "load_basic_project_data", lambda _name: _policy(True, "standard"))
    standard = evaluate_tool_gate(agent, "unknown_tool", {})
    assert standard["decision"] == "require_approval"
    assert agent.context.paused is True

    agent.context.paused = False
    monkeypatch.setattr(projects, "load_basic_project_data", lambda _name: _policy(True, "strict"))
    strict = evaluate_tool_gate(agent, "unknown_tool", {})
    assert strict["decision"] == "deny"
    assert agent.context.paused is False

    monkeypatch.setattr(projects, "load_basic_project_data", lambda _name: _policy(True, "autonomy"))
    autonomy = evaluate_tool_gate(agent, "unknown_tool", {})
    assert autonomy["decision"] == "allow"


@pytest.mark.asyncio
async def test_code_execution_provenance_assertion(monkeypatch):
    from python.helpers import governance_gate

    monkeypatch.setattr(governance_gate, "is_governance_enabled", lambda _agent: True)

    agent = _DummyAgent()
    tool = CodeExecution(
        agent,
        "code_execution_tool",
        None,
        {"runtime": "terminal", "code": "echo hi"},
        "",
        None,
    )

    with pytest.raises(RepairableException, match="missing gate token"):
        await tool.execute()


def test_custom_mode_tool_overrides_take_precedence(monkeypatch):
    from python.helpers import projects

    agent = _DummyAgent()
    monkeypatch.setattr(projects, "get_context_project_name", lambda _ctx: "p1")

    monkeypatch.setattr(
        projects,
        "load_basic_project_data",
        lambda _name: {
            "governance_enabled": True,
            "governance_mode": "custom",
            "policy_config": {
                "require_approval_for": ["high", "critical"],
                "default_policy": "allow",
                "tool_overrides": {
                    "browser_agent": {"decision": "deny"},
                    "search_engine": {"decision": "allow"},
                },
            },
        },
    )

    denied = evaluate_tool_gate(agent, "browser_agent", {})
    assert denied["decision"] == "deny"

    allowed = evaluate_tool_gate(agent, "search_engine", {})
    assert allowed["decision"] == "allow"


def test_terminal_read_only_auto_allowed_when_toggle_enabled(monkeypatch):
    from python.helpers import projects

    agent = _DummyAgent()
    monkeypatch.setattr(projects, "get_context_project_name", lambda _ctx: "p1")
    monkeypatch.setattr(
        projects,
        "load_basic_project_data",
        lambda _name: _policy(True, "standard", allow_readonly_terminal_without_approval=True),
    )

    result = evaluate_tool_gate(
        agent,
        "code_execution_tool",
        {"runtime": "terminal", "code": "ls -la /tmp && rg governance /opt/agentzero"},
    )
    assert result["decision"] == "allow"
    assert result["readonly_terminal"] is True
    assert result["risk"] == "low"
    assert agent.context.paused is False


def test_terminal_mutating_still_requires_approval_with_read_only_toggle(monkeypatch):
    from python.helpers import projects

    agent = _DummyAgent()
    monkeypatch.setattr(projects, "get_context_project_name", lambda _ctx: "p1")
    monkeypatch.setattr(
        projects,
        "load_basic_project_data",
        lambda _name: _policy(True, "standard", allow_readonly_terminal_without_approval=True),
    )

    result = evaluate_tool_gate(
        agent,
        "code_execution_tool",
        {"runtime": "terminal", "code": "ls -la /tmp && touch /tmp/governance_test_file"},
    )
    assert result["decision"] == "require_approval"
    assert result["readonly_terminal"] is False
    assert result["risk"] == "critical"
    assert agent.context.paused is True


def test_gh_read_methods_are_low_risk(monkeypatch):
    from python.helpers import projects

    agent = _DummyAgent()
    monkeypatch.setattr(projects, "get_context_project_name", lambda _ctx: "p1")
    monkeypatch.setattr(projects, "load_basic_project_data", lambda _name: _policy(True, "standard"))

    by_args = evaluate_tool_gate(agent, "gh", {"method": "pr_list"})
    assert by_args["risk"] == "low"
    assert by_args["decision"] == "allow"

    by_suffix = evaluate_tool_gate(agent, "gh:pr_view", {})
    assert by_suffix["risk"] == "low"
    assert by_suffix["decision"] == "allow"


def test_gh_write_methods_require_approval(monkeypatch):
    from python.helpers import projects

    agent = _DummyAgent()
    monkeypatch.setattr(projects, "get_context_project_name", lambda _ctx: "p1")
    monkeypatch.setattr(projects, "load_basic_project_data", lambda _name: _policy(True, "standard"))

    result = evaluate_tool_gate(agent, "gh", {"method": "pr_create"})
    assert result["risk"] == "high"
    assert result["decision"] == "require_approval"
    assert agent.context.paused is True
