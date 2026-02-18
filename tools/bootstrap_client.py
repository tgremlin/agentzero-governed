#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any


REQUIRED_DATA_SUBDIRS = ("usr", "tmp", "logs", "knowledge")


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def ensure_env_file(env_file: Path, example_file: Path) -> dict[str, Any]:
    if env_file.exists():
        return {"created": False, "path": str(env_file)}
    if not example_file.exists():
        raise RuntimeError(f"Cannot create env file: missing example {example_file}")
    env_file.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(example_file, env_file)
    return {"created": True, "path": str(env_file), "source": str(example_file)}


def resolve_data_dir(
    repo_root: Path, env_file: Path, override: str | None = None
) -> Path:
    if override:
        candidate = Path(override)
    else:
        env_map = parse_env_file(env_file)
        candidate = Path(env_map.get("A0_DATA_DIR", "./client-data"))
    if not candidate.is_absolute():
        candidate = repo_root / candidate
    return candidate.resolve()


def ensure_data_dirs(data_dir: Path) -> list[str]:
    created: list[str] = []
    for sub in REQUIRED_DATA_SUBDIRS:
        path = data_dir / sub
        path.mkdir(parents=True, exist_ok=True)
        created.append(str(path))
    return created


def _run_command(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        check=True,
        text=True,
        capture_output=True,
    )


def start_stack(repo_root: Path, compose_file: str) -> dict[str, Any]:
    cmd = ["docker", "compose", "-f", compose_file, "up", "-d", "--build"]
    proc = _run_command(cmd, repo_root)
    return {"command": " ".join(cmd), "stdout_tail": proc.stdout[-800:]}


def apply_scheduler_manifest(
    repo_root: Path, compose_file: str, manifest_path: str, apply: bool = True
) -> dict[str, Any]:
    manifest_rel = Path(manifest_path)
    if manifest_rel.is_absolute():
        raise RuntimeError("Manifest path for container apply must be repo-relative")
    cmd = [
        "docker",
        "compose",
        "-f",
        compose_file,
        "exec",
        "-T",
        "app",
        "/opt/venv-a0/bin/python",
        f"/a0/tools/scheduler_sync.py",
        "--path",
        f"/a0/{manifest_rel.as_posix()}",
    ]
    if apply:
        cmd.append("--apply")
    proc = _run_command(cmd, repo_root)
    parsed = {}
    try:
        parsed = json.loads(proc.stdout.strip().splitlines()[-1])
    except Exception:
        pass
    return {
        "command": " ".join(cmd),
        "stdout_tail": proc.stdout[-800:],
        "result": parsed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Bootstrap AgentZero client install files and directories."
    )
    parser.add_argument("--repo-root", default=".", help="Repo root path")
    parser.add_argument("--env-file", default=".env", help="Target env file")
    parser.add_argument(
        "--example-file", default=".env.client.example", help="Env template source file"
    )
    parser.add_argument("--data-dir", default="", help="Override A0_DATA_DIR")
    parser.add_argument(
        "--compose-file",
        default="docker-compose.client.yml",
        help="Compose file path (repo-relative)",
    )
    parser.add_argument(
        "--start-stack", action="store_true", help="Start stack after bootstrap."
    )
    parser.add_argument(
        "--apply-scheduler-manifest",
        action="store_true",
        help="Apply scheduler manifest through running app container.",
    )
    parser.add_argument(
        "--manifest-path",
        default="scheduler/tasks.seed.json",
        help="Scheduler manifest path (repo-relative).",
    )
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    env_file = (repo_root / args.env_file).resolve()
    example_file = (repo_root / args.example_file).resolve()

    env_result = ensure_env_file(env_file, example_file)
    data_dir = resolve_data_dir(
        repo_root=repo_root,
        env_file=env_file,
        override=args.data_dir or None,
    )
    created_dirs = ensure_data_dirs(data_dir)

    summary: dict[str, Any] = {
        "ok": True,
        "repo_root": str(repo_root),
        "env": env_result,
        "data_dir": str(data_dir),
        "created_dirs": created_dirs,
    }

    if args.start_stack:
        summary["stack"] = start_stack(repo_root=repo_root, compose_file=args.compose_file)
    if args.apply_scheduler_manifest:
        summary["scheduler_manifest"] = apply_scheduler_manifest(
            repo_root=repo_root,
            compose_file=args.compose_file,
            manifest_path=args.manifest_path,
            apply=True,
        )

    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
