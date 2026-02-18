from __future__ import annotations

from agent import Agent


def _build_agent_for_read_prompt() -> Agent:
    agent = Agent.__new__(Agent)
    return agent


def test_read_prompt_emits_prompt_template_selected(monkeypatch):
    from python.helpers import governance_gate
    from python.helpers import files
    from python.helpers import subagents

    emitted: list[dict] = []
    monkeypatch.setattr(
        governance_gate,
        "emit_governance_runtime_event",
        lambda _agent, event: emitted.append(event),
    )
    monkeypatch.setattr(subagents, "get_paths", lambda *_args, **_kwargs: ["/tmp/prompts"])
    monkeypatch.setattr(
        files,
        "read_prompt_file",
        lambda _file, _directories=None, _agent=None, **_kwargs: "prompt-body",
    )
    monkeypatch.setattr(files, "is_full_json_template", lambda _prompt: False)

    agent = _build_agent_for_read_prompt()
    out = agent.read_prompt("fw.msg_misformat.md", a=1, b="x")

    assert out == "prompt-body"
    assert emitted
    event = emitted[0]
    assert event["type"] == "prompt.template.selected"
    assert event["template"] == "fw.msg_misformat.md"
    assert event["kwargs_keys"] == ["a", "b"]

