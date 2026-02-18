import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from python.helpers.tool import Response, Tool


class SlackTool(Tool):
    API_BASE = "https://slack.com/api"

    async def execute(self, **kwargs):
        method = str(kwargs.get("method") or self.method or "").strip().lower()
        token = str(kwargs.get("token") or os.getenv("SLACK_BOT_TOKEN") or "").strip()

        if not method:
            return Response(
                message="Missing method. Supported: post_message, post_dm, list_channels",
                break_loop=False,
            )
        if not token:
            return Response(
                message="Missing Slack token. Set SLACK_BOT_TOKEN or pass token in tool args.",
                break_loop=False,
            )

        try:
            if method == "post_message":
                result = self._post_message(kwargs, token)
            elif method == "post_dm":
                result = self._post_dm(kwargs, token)
            elif method == "list_channels":
                result = self._list_channels(kwargs, token)
            else:
                return Response(
                    message=f"Unknown method '{method}'. Supported: post_message, post_dm, list_channels",
                    break_loop=False,
                )
            return Response(message=json.dumps(result, indent=2), break_loop=False)
        except Exception as exc:
            return Response(message=f"Slack tool error: {exc}", break_loop=False)

    def _post_message(self, args: dict[str, Any], token: str) -> dict[str, Any]:
        channel = str(args.get("channel", "")).strip()
        text = str(args.get("text", "")).strip()
        thread_ts = str(args.get("thread_ts", "")).strip()
        if not channel:
            raise ValueError("channel is required for post_message")
        if not text:
            raise ValueError("text is required for post_message")

        payload: dict[str, Any] = {"channel": channel, "text": text}
        if thread_ts:
            payload["thread_ts"] = thread_ts
        return self._api_post("chat.postMessage", payload, token)

    def _post_dm(self, args: dict[str, Any], token: str) -> dict[str, Any]:
        user_id = str(args.get("user", "")).strip()
        email = str(args.get("email", "")).strip()
        text = str(args.get("text", "")).strip()
        if not text:
            raise ValueError("text is required for post_dm")
        if not user_id and not email:
            raise ValueError("user or email is required for post_dm")

        if not user_id:
            lookup = self._api_get("users.lookupByEmail", {"email": email}, token)
            user = lookup.get("user", {})
            user_id = str(user.get("id", "")).strip()
            if not user_id:
                raise RuntimeError(f"Slack user not found for email '{email}'")

        dm = self._api_post("conversations.open", {"users": user_id}, token)
        channel = dm.get("channel", {})
        channel_id = str(channel.get("id", "")).strip()
        if not channel_id:
            raise RuntimeError("Could not open DM channel")

        sent = self._api_post(
            "chat.postMessage",
            {"channel": channel_id, "text": text},
            token,
        )
        return {"ok": True, "user": user_id, "channel": channel_id, "message": sent}

    def _list_channels(self, args: dict[str, Any], token: str) -> dict[str, Any]:
        limit = int(args.get("limit", 20))
        channel_types = str(args.get("types", "public_channel,private_channel")).strip()
        exclude_archived = bool(args.get("exclude_archived", True))
        return self._api_get(
            "conversations.list",
            {
                "limit": max(1, min(limit, 200)),
                "types": channel_types,
                "exclude_archived": "true" if exclude_archived else "false",
            },
            token,
        )

    def _api_post(self, endpoint: str, payload: dict[str, Any], token: str) -> dict[str, Any]:
        url = f"{self.API_BASE}/{endpoint}"
        body = json.dumps(payload).encode("utf-8")
        req = Request(
            url,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            },
        )
        return self._read_response(req)

    def _api_get(self, endpoint: str, query: dict[str, Any], token: str) -> dict[str, Any]:
        qs = urlencode(query)
        url = f"{self.API_BASE}/{endpoint}?{qs}" if qs else f"{self.API_BASE}/{endpoint}"
        req = Request(
            url,
            method="GET",
            headers={"Authorization": f"Bearer {token}"},
        )
        return self._read_response(req)

    def _read_response(self, req: Request) -> dict[str, Any]:
        try:
            with urlopen(req, timeout=30) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Slack API HTTP {e.code}: {detail}") from e
        except URLError as e:
            raise RuntimeError(f"Slack API network error: {e}") from e

        if not isinstance(payload, dict):
            raise RuntimeError("Slack API returned non-object response")
        if not payload.get("ok", False):
            error = str(payload.get("error", "unknown_error"))
            raise RuntimeError(f"Slack API error: {error}")
        return payload
