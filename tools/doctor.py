#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen


REQUIRED_SERVICES = ("app", "postgres", "temporal", "governance-worker")
DATA_SUBDIRS = ("usr", "tmp", "logs", "knowledge")


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def resolve_data_dir(repo_root: Path, env: dict[str, str]) -> Path:
    candidate = Path(env.get("A0_DATA_DIR", "./client-data"))
    if not candidate.is_absolute():
        candidate = repo_root / candidate
    return candidate.resolve()


def parse_compose_ps_json(raw: str) -> dict[str, str]:
    raw = raw.strip()
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
        if isinstance(payload, dict):
            payload = [payload]
    except Exception:
        payload = []
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
                payload.append(item)
            except Exception:
                continue
    out: dict[str, str] = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        service = str(item.get("Service", "")).strip() or str(item.get("service", "")).strip()
        state = str(item.get("State", "")).strip() or str(item.get("state", "")).strip()
        if service:
            out[service] = state
    return out


def run_compose_ps(repo_root: Path, compose_file: str) -> dict[str, str]:
    cmd = ["docker", "compose", "-f", compose_file, "ps", "--format", "json"]
    proc = subprocess.run(
        cmd,
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=True,
    )
    return parse_compose_ps_json(proc.stdout)


def check_api_ready(base_url: str) -> CheckResult:
    headers = {"Origin": base_url, "Referer": f"{base_url}/"}
    req = Request(f"{base_url}/csrf_token", headers=headers)
    try:
        with urlopen(req, timeout=8) as resp:
            raw = resp.read().decode("utf-8")
        payload = json.loads(raw)
        token = str(payload.get("token", "")).strip()
        if token:
            return CheckResult("api_csrf_ready", True, "csrf_token endpoint reachable")
        return CheckResult("api_csrf_ready", False, "csrf_token returned empty token")
    except URLError as e:
        return CheckResult("api_csrf_ready", False, f"request failed: {e}")
    except Exception as e:
        return CheckResult("api_csrf_ready", False, f"unexpected error: {e}")


def check_allowed_origins(base_url: str, env: dict[str, str]) -> CheckResult:
    default = "http://localhost:50001,http://127.0.0.1:50001"
    origins = str(env.get("ALLOWED_ORIGINS", default)).split(",")
    origins = [x.strip() for x in origins if x.strip()]
    if base_url in origins:
        return CheckResult("allowed_origins", True, f"{base_url} present")
    return CheckResult(
        "allowed_origins",
        False,
        f"{base_url} not present in ALLOWED_ORIGINS ({','.join(origins)})",
    )


def check_scheduler_stale(
    repo_root: Path, compose_file: str, stale_seconds: int
) -> CheckResult:
    py = "\n".join(
        [
            "import asyncio, json",
            "from python.helpers.task_scheduler import TaskScheduler",
            "async def main():",
            "    s = TaskScheduler.get()",
            "    await s.reload()",
            "    out = await s.recover_stale_running_tasks()",
            "    print(json.dumps({'recovered': out, 'count': len(out)}))",
            "asyncio.run(main())",
        ]
    )
    cmd = [
        "docker",
        "compose",
        "-f",
        compose_file,
        "exec",
        "-T",
        "app",
        "/opt/venv-a0/bin/python",
        "-c",
        py,
    ]
    env = os.environ.copy()
    env["SCHEDULER_STALE_RUNNING_SECONDS"] = str(stale_seconds)
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(repo_root),
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        line = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else "{}"
        payload = json.loads(line)
        count = int(payload.get("count", 0))
        if count == 0:
            return CheckResult("scheduler_stale_recovery", True, "no stale tasks found")
        return CheckResult(
            "scheduler_stale_recovery",
            False,
            f"recovered stale tasks: {payload.get('recovered', [])}",
        )
    except Exception as e:
        return CheckResult("scheduler_stale_recovery", False, f"check failed: {e}")


def run_deep_smoke(repo_root: Path, base_url: str) -> CheckResult:
    cmd = ["python3", "tools/smoke_client_stack.py", base_url]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=True,
        )
        return CheckResult("deep_smoke", True, proc.stdout.strip().splitlines()[-1])
    except subprocess.CalledProcessError as e:
        detail = (e.stdout or e.stderr or "").strip()[-800:]
        return CheckResult("deep_smoke", False, detail or f"exit {e.returncode}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Client stack health checks.")
    parser.add_argument("--repo-root", default=".", help="Repo root path")
    parser.add_argument(
        "--compose-file",
        default="docker-compose.client.yml",
        help="Compose file path (repo-relative)",
    )
    parser.add_argument("--env-file", default=".env", help="Env file path (repo-relative)")
    parser.add_argument("--base-url", default="http://127.0.0.1:50001", help="App URL")
    parser.add_argument(
        "--stale-seconds", type=int, default=600, help="Stale running scheduler threshold"
    )
    parser.add_argument(
        "--deep-smoke", action="store_true", help="Run governance temporal smoke check"
    )
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    env_file = (repo_root / args.env_file).resolve()
    env = parse_env_file(env_file)

    checks: list[CheckResult] = []
    checks.append(CheckResult("env_file", env_file.exists(), str(env_file)))

    data_dir = resolve_data_dir(repo_root, env)
    missing = [sub for sub in DATA_SUBDIRS if not (data_dir / sub).exists()]
    checks.append(
        CheckResult(
            "data_dirs",
            len(missing) == 0,
            f"data_dir={data_dir}; missing={missing}",
        )
    )
    checks.append(check_allowed_origins(args.base_url, env))

    try:
        states = run_compose_ps(repo_root, args.compose_file)
        for service in REQUIRED_SERVICES:
            state = states.get(service, "missing")
            checks.append(
                CheckResult(
                    f"service_{service}",
                    state.lower().startswith("running"),
                    f"state={state}",
                )
            )
    except Exception as e:
        checks.append(CheckResult("compose_ps", False, str(e)))

    checks.append(check_api_ready(args.base_url))
    checks.append(check_scheduler_stale(repo_root, args.compose_file, args.stale_seconds))

    if args.deep_smoke:
        checks.append(run_deep_smoke(repo_root, args.base_url))

    ok = all(c.ok for c in checks)
    payload = {"ok": ok, "checks": [asdict(c) for c in checks]}
    print(json.dumps(payload, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
