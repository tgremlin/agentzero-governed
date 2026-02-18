import asyncio
import json
import os
import re
import threading
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import websockets

from python.helpers import files
from python.helpers.print_style import PrintStyle
from python.helpers.secrets import get_default_secrets_manager
from python.helpers.settings import get_settings


STATE_FILE = "usr/slack/socket_context_map.json"


def _is_true(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class SlackConfig:
    socket_enabled: bool
    mode: str
    reply_in_thread: bool
    app_url: str
    context_lifetime_hours: int
    project_name: str
    reconnect_delay_seconds: int

    @classmethod
    def load(cls) -> "SlackConfig":
        mode = (os.getenv("SLACK_SOCKET_MODE") or "both").strip().lower()
        if mode not in {"dm", "mentions", "both"}:
            mode = "both"
        return cls(
            socket_enabled=_is_true(os.getenv("SLACK_SOCKET_ENABLED"), default=False),
            mode=mode,
            reply_in_thread=_is_true(os.getenv("SLACK_SOCKET_REPLY_IN_THREAD"), default=True),
            app_url=(os.getenv("SLACK_A0_API_URL") or "http://app:5000").rstrip("/"),
            context_lifetime_hours=max(1, int(os.getenv("SLACK_CONTEXT_LIFETIME_HOURS", "720"))),
            project_name=(os.getenv("SLACK_PROJECT_NAME") or "").strip(),
            reconnect_delay_seconds=max(1, int(os.getenv("SLACK_SOCKET_RECONNECT_DELAY_SECONDS", "5"))),
        )


class SlackApi:
    def __init__(self, bot_token: str, app_token: str):
        self.bot_token = bot_token
        self.app_token = app_token

    def open_socket_url(self) -> str:
        payload = self._request(
            method="POST",
            endpoint="apps.connections.open",
            token=self.app_token,
            body={},
        )
        url = str(payload.get("url", "")).strip()
        if not url:
            raise RuntimeError("apps.connections.open did not return URL")
        return url

    def auth_test(self) -> dict[str, Any]:
        return self._request("POST", "auth.test", self.bot_token, body={})

    def post_message(self, channel: str, text: str, thread_ts: str | None) -> dict[str, Any]:
        body: dict[str, Any] = {"channel": channel, "text": text}
        if thread_ts:
            body["thread_ts"] = thread_ts
        return self._request("POST", "chat.postMessage", self.bot_token, body=body)

    def _request(
        self,
        method: str,
        endpoint: str,
        token: str,
        body: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        base = f"https://slack.com/api/{endpoint}"
        if query:
            base = f"{base}?{urlencode(query)}"

        data = json.dumps(body or {}).encode("utf-8") if method == "POST" else None
        req = Request(
            base,
            method=method,
            data=data,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            },
        )

        try:
            with urlopen(req, timeout=30) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Slack API HTTP {e.code}: {detail}") from e
        except URLError as e:
            raise RuntimeError(f"Slack API network error: {e}") from e

        if not isinstance(payload, dict):
            raise RuntimeError(f"Slack API returned invalid payload for {endpoint}")
        if not payload.get("ok", False):
            raise RuntimeError(f"Slack API {endpoint} failed: {payload.get('error', 'unknown_error')}")
        return payload


class ContextMapStore:
    def __init__(self, path: str):
        self.path = path
        self._lock = threading.RLock()
        self._data: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        with self._lock:
            try:
                raw = files.read_file(self.path)
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    self._data = {
                        str(k): str(v)
                        for k, v in parsed.items()
                        if isinstance(k, str) and isinstance(v, str) and k and v
                    }
            except Exception:
                self._data = {}

    def _save(self) -> None:
        with self._lock:
            files.make_dirs(self.path)
            files.write_file(self.path, json.dumps(self._data, indent=2))

    def get(self, key: str) -> str:
        with self._lock:
            return self._data.get(key, "")

    def set(self, key: str, context_id: str) -> None:
        with self._lock:
            self._data[key] = context_id
            self._save()


class AgentApi:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def send_message(
        self,
        context_id: str,
        message: str,
        lifetime_hours: int,
        project_name: str = "",
    ) -> tuple[str, str]:
        settings = get_settings()
        api_key = str(settings.get("mcp_server_token", "")).strip()
        if not api_key:
            raise RuntimeError("mcp_server_token is missing; cannot call /api_message")

        body: dict[str, Any] = {
            "context_id": context_id,
            "message": message,
            "lifetime_hours": lifetime_hours,
        }
        if project_name:
            body["project_name"] = project_name

        req = Request(
            f"{self.base_url}/api_message",
            method="POST",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "X-API-KEY": api_key,
            },
        )
        try:
            with urlopen(req, timeout=600) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"/api_message HTTP {e.code}: {detail}") from e
        except URLError as e:
            raise RuntimeError(f"/api_message network error: {e}") from e

        if not isinstance(payload, dict):
            raise RuntimeError("/api_message returned invalid payload")

        out_context_id = str(payload.get("context_id", "")).strip()
        response = str(payload.get("response", "")).strip()
        if not out_context_id:
            raise RuntimeError("/api_message returned empty context_id")
        return out_context_id, response


class SlackSocketListener:
    def __init__(self):
        self.config = SlackConfig.load()
        self.map_store = ContextMapStore(STATE_FILE)
        self.agent_api = AgentApi(self.config.app_url)
        self.context_locks: dict[str, asyncio.Lock] = {}
        self.bot_user_id = ""
        self.bot_name = "agentzero"

    def _load_tokens(self) -> tuple[str, str]:
        try:
            secrets = get_default_secrets_manager().load_secrets()
        except Exception:
            secrets = {}
        bot_token = (
            str(secrets.get("SLACK_BOT_TOKEN", "")).strip()
            or str(os.getenv("SLACK_BOT_TOKEN", "")).strip()
        )
        app_token = (
            str(secrets.get("SLACK_APP_TOKEN", "")).strip()
            or str(os.getenv("SLACK_APP_TOKEN", "")).strip()
        )
        return bot_token, app_token

    async def run_forever(self) -> None:
        PrintStyle(font_color="cyan", padding=True).print("Slack socket listener starting...")
        while True:
            self.config = SlackConfig.load()
            if not self.config.socket_enabled:
                PrintStyle(font_color="yellow", padding=True).print(
                    "Slack socket listener disabled (SLACK_SOCKET_ENABLED=false)."
                )
                await asyncio.sleep(10)
                continue

            bot_token, app_token = self._load_tokens()
            if not bot_token or not app_token:
                PrintStyle(font_color="yellow", padding=True).print(
                    "Slack socket listener waiting for SLACK_BOT_TOKEN and SLACK_APP_TOKEN."
                )
                await asyncio.sleep(10)
                continue

            try:
                api = SlackApi(bot_token=bot_token, app_token=app_token)
                auth = api.auth_test()
                self.bot_user_id = str(auth.get("user_id", "")).strip()
                self.bot_name = str(auth.get("user", "agentzero")).strip() or "agentzero"
                await self._connect_and_consume(api)
            except Exception as exc:
                PrintStyle.error(f"Slack socket listener error: {exc}")
                await asyncio.sleep(self.config.reconnect_delay_seconds)

    async def _connect_and_consume(self, api: SlackApi) -> None:
        socket_url = api.open_socket_url()
        PrintStyle(font_color="cyan", padding=True).print("Slack socket connected, waiting for events...")
        async with websockets.connect(socket_url, ping_interval=20, ping_timeout=20) as ws:
            while True:
                raw = await ws.recv()
                envelope = json.loads(raw)
                if not isinstance(envelope, dict):
                    continue

                envelope_id = str(envelope.get("envelope_id", "")).strip()
                if envelope_id:
                    await ws.send(json.dumps({"envelope_id": envelope_id}))

                event_type = str(envelope.get("type", "")).strip()
                if event_type == "hello":
                    PrintStyle(font_color="green").print("Slack socket hello received.")
                    continue
                if event_type == "disconnect":
                    PrintStyle.warning("Slack socket disconnect event received.")
                    return

                payload = envelope.get("payload", {})
                if not isinstance(payload, dict):
                    continue
                if payload.get("type") != "events_api":
                    continue
                event = payload.get("event", {})
                if not isinstance(event, dict):
                    continue
                asyncio.create_task(self._handle_event(api, event))

    async def _handle_event(self, api: SlackApi, event: dict[str, Any]) -> None:
        parsed = self._parse_event(event)
        if not parsed:
            return

        context_key = parsed["context_key"]
        context_id = self.map_store.get(context_key)
        if not context_id:
            context_id = ""

        lock = self.context_locks.setdefault(context_key, asyncio.Lock())
        async with lock:
            try:
                out_context_id, response = await asyncio.to_thread(
                    self.agent_api.send_message,
                    context_id,
                    parsed["agent_message"],
                    self.config.context_lifetime_hours,
                    self.config.project_name,
                )
                if out_context_id != context_id:
                    self.map_store.set(context_key, out_context_id)

                reply = response.strip() or "Acknowledged."
                thread_ts = parsed["thread_ts"] if self.config.reply_in_thread else None
                await asyncio.to_thread(
                    api.post_message,
                    parsed["channel"],
                    self._trim_reply(reply),
                    thread_ts,
                )
            except Exception as exc:
                PrintStyle.error(f"Slack event handling failed: {exc}")
                err_reply = f"Slack listener error: {exc}"
                thread_ts = parsed["thread_ts"] if self.config.reply_in_thread else None
                try:
                    await asyncio.to_thread(
                        api.post_message,
                        parsed["channel"],
                        self._trim_reply(err_reply),
                        thread_ts,
                    )
                except Exception:
                    pass

    def _parse_event(self, event: dict[str, Any]) -> dict[str, str] | None:
        event_type = str(event.get("type", "")).strip()
        subtype = str(event.get("subtype", "")).strip()
        user = str(event.get("user", "")).strip()
        channel = str(event.get("channel", "")).strip()
        text = str(event.get("text", "")).strip()
        channel_type = str(event.get("channel_type", "")).strip()
        thread_ts = str(event.get("thread_ts", "")).strip() or str(event.get("ts", "")).strip()
        bot_id = str(event.get("bot_id", "")).strip()

        if not channel or not thread_ts:
            return None
        if subtype:
            return None
        if bot_id:
            return None
        if not user:
            return None
        if self.bot_user_id and user == self.bot_user_id:
            return None

        allow_dm = self.config.mode in {"dm", "both"}
        allow_mentions = self.config.mode in {"mentions", "both"}

        if event_type == "message" and channel_type == "im" and allow_dm:
            context_key = f"dm:{user}"
            return {
                "context_key": context_key,
                "channel": channel,
                "thread_ts": thread_ts,
                "agent_message": text,
            }

        if event_type == "app_mention" and allow_mentions:
            cleaned = self._strip_bot_mentions(text)
            context_key = f"channel:{channel}:thread:{thread_ts}"
            return {
                "context_key": context_key,
                "channel": channel,
                "thread_ts": thread_ts,
                "agent_message": cleaned or text,
            }
        return None

    def _strip_bot_mentions(self, text: str) -> str:
        return re.sub(r"<@[^>]+>", "", text).strip()

    def _trim_reply(self, text: str) -> str:
        text = text.strip()
        if len(text) <= 39000:
            return text
        return text[:39000] + "\n\n[truncated]"


async def _main() -> None:
    listener = SlackSocketListener()
    await listener.run_forever()


if __name__ == "__main__":
    while True:
        try:
            asyncio.run(_main())
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            PrintStyle.error(f"Slack listener crashed: {exc}")
            time.sleep(3)
