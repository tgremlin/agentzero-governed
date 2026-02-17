#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import time
from urllib.parse import urlparse
from typing import Any

import requests


def wait_for_ready(
    session: requests.Session, base_url: str, timeout_seconds: int = 120
) -> tuple[str, str]:
    headers = {"Origin": base_url, "Referer": f"{base_url}/"}
    end = time.time() + timeout_seconds
    while time.time() < end:
        try:
            response = session.get(f"{base_url}/csrf_token", headers=headers, timeout=5)
            if response.status_code == 200:
                payload = response.json()
                token = str(payload.get("token", "")).strip()
                runtime_id = str(payload.get("runtime_id", "")).strip()
                if token:
                    return token, runtime_id
        except Exception:
            pass
        time.sleep(1)
    raise RuntimeError(f"App was not ready at {base_url} within {timeout_seconds}s")


def must_ok(response: requests.Response, label: str) -> dict[str, Any]:
    if response.status_code != 200:
        raise RuntimeError(f"{label} failed ({response.status_code}): {response.text}")
    try:
        return response.json()
    except Exception as exc:
        raise RuntimeError(f"{label} returned non-JSON payload: {response.text}") from exc


def main() -> int:
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:50001"
    session = requests.Session()

    token, runtime_id = wait_for_ready(session, base_url)
    if runtime_id:
        host = urlparse(base_url).hostname or "127.0.0.1"
        session.cookies.set(f"csrf_token_{runtime_id}", token, domain=host, path="/")
    headers = {
        "Origin": base_url,
        "Referer": f"{base_url}/",
        "X-CSRF-Token": token,
        "Content-Type": "application/json",
    }

    start = session.post(
        f"{base_url}/governance_run_start",
        headers=headers,
        json={"context_id": ""},
        timeout=30,
    )
    start_payload = must_ok(start, "governance_run_start")
    run_id = str(start_payload.get("run_id", "")).strip()
    if not run_id:
        raise RuntimeError("governance_run_start did not return run_id")
    if not bool(start_payload.get("temporal")):
        raise RuntimeError(f"Temporal execution not used: {json.dumps(start_payload)}")

    for signal in ("pause", "resume", "cancel"):
        response = session.post(
            f"{base_url}/governance_run_signal",
            headers=headers,
            json={"run_id": run_id, "signal": signal},
            timeout=30,
        )
        payload = must_ok(response, f"governance_run_signal({signal})")
        if not bool(payload.get("temporal")):
            raise RuntimeError(f"Temporal signal path not used ({signal}): {json.dumps(payload)}")

    print(json.dumps({"ok": True, "run_id": run_id, "base_url": base_url}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
