import asyncio

from python.helpers import dotenv, runtime


def test_call_development_function_falls_back_to_local_without_rfc_password(monkeypatch):
    monkeypatch.setattr(runtime, "is_development", lambda: True)
    monkeypatch.setattr(dotenv, "get_dotenv_value", lambda key, default=None: "")

    called = {"rfc": False}

    async def _fail_if_called(**kwargs):
        called["rfc"] = True
        raise AssertionError("RFC should not be called without RFC_PASSWORD")

    monkeypatch.setattr(runtime.rfc, "call_rfc", _fail_if_called)

    def add(a: int, b: int) -> int:
        return a + b

    result = asyncio.run(runtime.call_development_function(add, 2, 3))

    assert result == 5
    assert called["rfc"] is False
