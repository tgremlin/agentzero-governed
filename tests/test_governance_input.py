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


def _policy(enabled: bool, mode: str):
    return {
        "governance_enabled": enabled,
        "governance_mode": mode,
        "policy_config": {
            "require_approval_for": ["high", "critical"],
            "default_policy": "allow",
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
