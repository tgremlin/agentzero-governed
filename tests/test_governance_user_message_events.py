from __future__ import annotations

from agent import Agent, UserMessage


def _build_agent_for_user_message() -> Agent:
    agent = Agent.__new__(Agent)
    agent.history = type("_History", (), {"new_topic": lambda self: None})()
    agent.parse_prompt = lambda *_args, **_kwargs: {"message": "ok"}
    agent.hist_add_message = lambda _ai, content=None, tokens=0, **_kwargs: {"id": "m1", "content": content, "tokens": tokens}
    agent.last_user_message = None
    return agent


def test_hist_add_user_message_emits_user_message_created(monkeypatch):
    from python.helpers import governance_gate

    emitted: list[dict] = []
    monkeypatch.setattr(
        governance_gate,
        "emit_governance_runtime_event",
        lambda _agent, event: emitted.append(event),
    )

    agent = _build_agent_for_user_message()
    msg = UserMessage(
        message="hello governed world",
        attachments=["file://a.txt", "file://b.txt"],
        system_message=["sys-1"],
    )
    agent.hist_add_user_message(msg, intervention=False)

    assert emitted
    event = emitted[0]
    assert event["type"] == "user.message.created"
    assert event["message_length"] == len("hello governed world")
    assert event["attachments_count"] == 2
    assert event["system_message_count"] == 1
    assert event["intervention"] is False
