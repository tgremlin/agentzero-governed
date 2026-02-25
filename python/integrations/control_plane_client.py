from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class ControlPlaneClientError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, body: str = ""):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


@dataclass(frozen=True)
class ControlPlaneClient:
    base_url: str

    def request_json(
        self,
        method: str,
        path: str,
        *,
        token: str,
        payload: dict[str, Any] | None = None,
    ) -> tuple[int, Any]:
        url = f"{self.base_url}{path}"
        data = json.dumps(payload or {}).encode("utf-8") if method.upper() in {"POST", "PUT", "PATCH"} else None
        req = Request(
            url,
            method=method.upper(),
            data=data,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            },
        )

        try:
            with urlopen(req, timeout=30) as resp:
                status = int(getattr(resp, "status", 200) or 200)
                body_text = resp.read().decode("utf-8")
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise ControlPlaneClientError(
                f"control-plane {method.upper()} {path} failed with HTTP {exc.code}",
                status_code=exc.code,
                body=body,
            ) from exc
        except URLError as exc:
            raise ControlPlaneClientError(f"control-plane {method.upper()} {path} network error: {exc}") from exc

        try:
            parsed = json.loads(body_text) if body_text else {}
        except json.JSONDecodeError:
            parsed = {"raw": body_text}

        return status, parsed
