import json
from types import SimpleNamespace

import pytest

from python.tools.gh import GhTool


def _tool(method: str | None = None) -> GhTool:
    agent = SimpleNamespace(context=None)
    return GhTool(agent=agent, name="gh", method=method, args={}, message="", loop_data=None)


def test_resolve_repo_from_repo_arg():
    tool = _tool()
    assert tool._resolve_repo({"repo": "acme/repo"}) == ("acme", "repo")


def test_resolve_token_prefers_secrets(monkeypatch):
    tool = _tool()
    monkeypatch.setattr(
        "python.tools.gh.get_secrets_manager",
        lambda _ctx: SimpleNamespace(load_secrets=lambda: {"GH_TOKEN": "secret_token"}),
    )
    monkeypatch.setenv("GH_TOKEN", "env_token")
    assert tool._resolve_token() == "secret_token"


@pytest.mark.asyncio
async def test_execute_repo_view_dispatches_and_serializes(monkeypatch):
    tool = _tool(method="repo_view")
    monkeypatch.setattr(tool, "_resolve_repo", lambda _args: ("acme", "repo"))
    monkeypatch.setattr(
        tool,
        "_api_request",
        lambda method, path, query=None, body=None, auth_required=False: {
            "method": method,
            "path": path,
        },
    )
    result = await tool.execute()
    payload = json.loads(result.message)
    assert payload["method"] == "GET"
    assert payload["path"] == "/repos/acme/repo"


@pytest.mark.asyncio
async def test_execute_issue_create_requires_title():
    tool = _tool(method="issue_create")
    result = await tool.execute(repo="acme/repo", body="missing title")
    assert "title is required for issue_create" in result.message
