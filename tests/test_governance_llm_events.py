from __future__ import annotations

import asyncio

from agent import Agent


class _DummyModel:
    async def unified_call(self, **_kwargs):
        return ("ok-response", "")


def _build_agent_for_llm_calls() -> Agent:
    agent = Agent.__new__(Agent)
    agent.call_extensions = lambda *_args, **_kwargs: asyncio.sleep(0)
    agent.get_chat_model = lambda: _DummyModel()
    agent.get_utility_model = lambda: _DummyModel()
    return agent


def test_call_chat_model_emits_llm_request_and_response_events(monkeypatch):
    from python.helpers import governance_gate

    emitted: list[dict] = []
    monkeypatch.setattr(governance_gate, "emit_governance_runtime_event", lambda _agent, event: emitted.append(event))

    agent = _build_agent_for_llm_calls()
    out, _reasoning = asyncio.run(agent.call_chat_model(messages=[], background=True))

    assert out == "ok-response"
    event_types = [e.get("type") for e in emitted]
    assert event_types == ["llm.request.sent", "llm.response.received"]
    assert emitted[0]["model_role"] == "chat"
    assert emitted[1]["model_role"] == "chat"


def test_call_utility_model_emits_llm_request_and_response_events(monkeypatch):
    from python.helpers import governance_gate

    emitted: list[dict] = []
    monkeypatch.setattr(governance_gate, "emit_governance_runtime_event", lambda _agent, event: emitted.append(event))

    agent = _build_agent_for_llm_calls()
    out = asyncio.run(agent.call_utility_model(system="sys", message="hello", background=True))

    assert out == "ok-response"
    event_types = [e.get("type") for e in emitted]
    assert event_types == ["llm.request.sent", "llm.response.received"]
    assert emitted[0]["model_role"] == "utility"
    assert emitted[1]["model_role"] == "utility"
