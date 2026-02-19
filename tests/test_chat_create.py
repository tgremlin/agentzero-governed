import asyncio
import threading
from types import SimpleNamespace

from python.api.chat_create import CreateChat


class _DummyCreateChat(CreateChat):
    def __init__(self):
        super().__init__(app=None, thread_lock=threading.RLock())
        self.used_context_ids = []

    def use_context(self, ctxid: str, create_if_not_exists: bool = True):  # type: ignore[override]
        self.used_context_ids.append(ctxid)
        return SimpleNamespace(id=ctxid)


def test_chat_create_generates_new_id_when_requested_id_collides(monkeypatch):
    handler = _DummyCreateChat()

    taken_ids = {"taken123"}

    monkeypatch.setattr("python.api.chat_create.AgentContext.get", lambda ctxid: object() if ctxid in taken_ids else None)
    monkeypatch.setattr("python.helpers.files.exists", lambda _path: False)

    generated = iter(["taken123", "fresh456"])
    monkeypatch.setattr("python.api.chat_create.guids.generate_id", lambda: next(generated))

    out = asyncio.run(handler.process({"new_context": "taken123"}, request=SimpleNamespace()))

    assert out["ok"] is True
    assert out["ctxid"] == "fresh456"
    assert handler.used_context_ids == ["fresh456"]


def test_chat_create_avoids_ids_present_on_disk(monkeypatch):
    handler = _DummyCreateChat()

    monkeypatch.setattr("python.api.chat_create.AgentContext.get", lambda _ctxid: None)

    def _exists(path: str) -> bool:
        return path.endswith("on_disk_1")

    monkeypatch.setattr("python.helpers.files.exists", _exists)

    generated = iter(["on_disk_1", "on_disk_2"])
    monkeypatch.setattr("python.api.chat_create.guids.generate_id", lambda: next(generated))

    out = asyncio.run(handler.process({}, request=SimpleNamespace()))

    assert out["ok"] is True
    assert out["ctxid"] == "on_disk_2"
    assert handler.used_context_ids == ["on_disk_2"]
