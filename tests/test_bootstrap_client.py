import json
import subprocess
from pathlib import Path


def _run_bootstrap(repo_root: Path, extra_args: list[str] | None = None) -> dict:
    args = [
        "/opt/venv-a0/bin/python",
        "/a0/tools/bootstrap_client.py",
        "--repo-root",
        str(repo_root),
        "--env-file",
        ".env",
        "--example-file",
        ".env.client.example",
    ]
    if extra_args:
        args.extend(extra_args)
    proc = subprocess.run(args, check=True, text=True, capture_output=True)
    return json.loads(proc.stdout)


def test_bootstrap_creates_env_and_data_dirs(tmp_path: Path):
    (tmp_path / ".env.client.example").write_text(
        "A0_DATA_DIR=./client-data-test\n", encoding="utf-8"
    )
    out = _run_bootstrap(tmp_path)

    assert out["ok"] is True
    assert out["env"]["created"] is True
    assert (tmp_path / ".env").exists()
    for sub in ("usr", "tmp", "logs", "knowledge"):
        assert (tmp_path / "client-data-test" / sub).exists()


def test_bootstrap_preserves_existing_env(tmp_path: Path):
    (tmp_path / ".env.client.example").write_text(
        "A0_DATA_DIR=./example-data\n", encoding="utf-8"
    )
    (tmp_path / ".env").write_text("A0_DATA_DIR=./custom-data\n", encoding="utf-8")

    out = _run_bootstrap(tmp_path)
    assert out["env"]["created"] is False
    for sub in ("usr", "tmp", "logs", "knowledge"):
        assert (tmp_path / "custom-data" / sub).exists()
