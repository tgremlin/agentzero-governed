#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar


def _build_client() -> urllib.request.OpenerDirector:
    jar = CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def _request_json(
    opener: urllib.request.OpenerDirector,
    method: str,
    url: str,
    payload: dict | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict]:
    body = None
    req_headers = {"Accept": "application/json"}
    if headers:
        req_headers.update(headers)
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        req_headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url=url, data=body, method=method, headers=req_headers)
    try:
        with opener.open(req, timeout=20) as resp:
            status = getattr(resp, "status", 200)
            raw = resp.read().decode("utf-8", errors="replace")
            return status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as err:
        raw = err.read().decode("utf-8", errors="replace")
        data = {}
        if raw:
            try:
                data = json.loads(raw)
            except Exception:
                data = {"raw": raw}
        return int(err.code), data


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    base = os.getenv("E2E_BASE_URL", "http://127.0.0.1:5000").rstrip("/")
    opener = _build_client()
    origin = urllib.parse.urlsplit(base)
    origin_header = f"{origin.scheme}://{origin.netloc}"

    status, _ = _request_json(
        opener,
        "GET",
        f"{base}/csrf_token",
        headers={"Origin": origin_header},
    )
    _assert(status == 200, f"/csrf_token failed: {status}")

    status, csrf = _request_json(
        opener,
        "GET",
        f"{base}/csrf_token",
        headers={"Origin": origin_header},
    )
    _assert(status == 200 and csrf.get("ok") is True, f"/csrf_token response invalid: {status} {csrf}")
    token = str(csrf.get("token", "")).strip()
    _assert(bool(token), "csrf token missing")

    auth_headers = {"X-CSRF-Token": token}

    status, events = _request_json(
        opener,
        "POST",
        f"{base}/governance_events",
        payload={"project_name": "e2e-project", "limit": 10, "offset": 0},
        headers=auth_headers,
    )
    _assert(status == 200 and events.get("ok") is True, f"/governance_events failed: {status} {events}")

    status, candidates = _request_json(
        opener,
        "POST",
        f"{base}/training_candidates",
        payload={"project_name": "e2e-project", "limit": 10, "offset": 0},
        headers=auth_headers,
    )
    _assert(
        status == 200 and candidates.get("ok") is True,
        f"/training_candidates failed: {status} {candidates}",
    )

    status, trace = _request_json(
        opener,
        "POST",
        f"{base}/system_trace",
        payload={"project_name": "e2e-project"},
        headers=auth_headers,
    )
    _assert(status == 200 and trace.get("ok") is True, f"/system_trace failed: {status} {trace}")
    _assert(trace.get("coming_soon") is True, "/system_trace missing coming_soon=true")

    status, update = _request_json(
        opener,
        "POST",
        f"{base}/training_candidates_update",
        payload={"project_name": "e2e-project", "candidate_ids": []},
        headers=auth_headers,
    )
    _assert(status == 400, f"/training_candidates_update validation should be 400, got {status} {update}")

    print("e2e smoke checks passed")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"e2e smoke FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)
