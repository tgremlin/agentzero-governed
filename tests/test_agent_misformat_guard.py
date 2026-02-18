import asyncio

from agent import Agent
from python.helpers import extract_tools
from python.helpers import governance_gate


class _DummyLog:
    def __init__(self) -> None:
        self.entries: list[tuple[str, str]] = []

    def log(self, type: str, content: str = "", **kwargs):
        self.entries.append((type, content))


class _DummyContext:
    def __init__(self) -> None:
        self.log = _DummyLog()


def _build_agent_for_process_tools() -> Agent:
    agent = Agent.__new__(Agent)
    agent.data = {}
    agent.agent_name = "A0"
    agent.context = _DummyContext()
    agent.read_prompt = lambda _name: "misformat"
    agent.hist_add_warning = lambda _msg: None
    agent.set_data = lambda k, v: agent.data.__setitem__(k, v)
    agent.get_data = lambda k: agent.data.get(k)
    return agent


def test_process_tools_breaks_after_repeated_misformat(monkeypatch):
    monkeypatch.setattr(extract_tools, "json_parse_dirty", lambda _msg: None)
    emitted: list[dict] = []
    monkeypatch.setattr(governance_gate, "emit_governance_runtime_event", lambda _agent, event: emitted.append(event))
    agent = _build_agent_for_process_tools()

    # First two malformed responses should continue.
    assert asyncio.run(agent.process_tools("bad-1")) is None
    assert asyncio.run(agent.process_tools("bad-2")) is None

    # Third malformed response should break the loop with explicit message.
    out = asyncio.run(agent.process_tools("bad-3"))
    assert isinstance(out, str)
    assert "Stopping due to repeated malformed tool outputs" in out

    # Streak resets after break to avoid sticky state.
    assert agent.get_data(Agent.DATA_NAME_MISFORMAT_STREAK) == 0
    parse_failed = [e for e in emitted if e.get("type") == "llm.response.parse_failed"]
    assert len(parse_failed) == 3
    assert parse_failed[-1]["misformat_streak"] == 3


def test_process_tools_resets_misformat_streak_on_valid_tool_request(monkeypatch):
    agent = _build_agent_for_process_tools()
    agent.set_data(Agent.DATA_NAME_MISFORMAT_STREAK, 2)
    emitted: list[dict] = []
    monkeypatch.setattr(governance_gate, "emit_governance_runtime_event", lambda _agent, event: emitted.append(event))

    # Return a parseable request with unknown tool so method takes structured path.
    monkeypatch.setattr(
        extract_tools,
        "json_parse_dirty",
        lambda _msg: {"tool_name": "tool_that_does_not_exist", "tool_args": {}},
    )
    monkeypatch.setattr(agent, "get_tool", lambda **_kwargs: None)

    asyncio.run(agent.process_tools("valid-json"))

    assert agent.get_data(Agent.DATA_NAME_MISFORMAT_STREAK) == 0
    assert any(
        "misformat streak reset after 2 malformed output(s)" in content
        for _type, content in agent.context.log.entries
    )
    assert any(e.get("type") == "llm.response.parsed" for e in emitted)
