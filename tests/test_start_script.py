import os
import shutil
import subprocess
from pathlib import Path


def _make_fake_docker(bin_dir: Path) -> Path:
    fake = bin_dir / "docker"
    fake.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
echo "$*" >> "${FAKE_DOCKER_LOG}"
if [[ "${1:-}" == "image" && "${2:-}" == "inspect" ]]; then
  if [[ "${FAKE_IMAGE_EXISTS:-0}" == "1" ]]; then
    exit 0
  fi
  exit 1
fi
exit 0
""",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    return fake


def _run_start_script(tmp_path: Path, *, image_exists: bool, force_rebuild: bool) -> str:
    repo = tmp_path / "repo"
    repo.mkdir()
    shutil.copy("/a0/start.sh", repo / "start.sh")
    (repo / "docker-compose.client.yml").write_text("services: {}\n", encoding="utf-8")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _make_fake_docker(bin_dir)

    log_path = tmp_path / "docker.log"
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["FAKE_DOCKER_LOG"] = str(log_path)
    env["FAKE_IMAGE_EXISTS"] = "1" if image_exists else "0"
    env["A0_DATA_DIR"] = str(tmp_path / "client-data")
    if force_rebuild:
        env["FORCE_REBUILD"] = "true"

    subprocess.run(
        ["/bin/bash", str(repo / "start.sh")],
        env=env,
        check=True,
        text=True,
        capture_output=True,
    )

    return log_path.read_text(encoding="utf-8")


def test_start_script_skips_rebuild_when_image_exists(tmp_path: Path):
    log = _run_start_script(tmp_path, image_exists=True, force_rebuild=False)
    assert "image inspect agentzero-governed:latest" in log
    assert "compose -f docker-compose.client.yml build app" not in log
    assert "compose -f docker-compose.client.yml up -d --no-build" in log
    assert (tmp_path / "repo/data/temporal/dynamicconfig/development.yaml").exists()


def test_start_script_builds_when_image_missing(tmp_path: Path):
    log = _run_start_script(tmp_path, image_exists=False, force_rebuild=False)
    assert "compose -f docker-compose.client.yml build app" in log
    assert "compose -f docker-compose.client.yml up -d --no-build" in log


def test_start_script_honors_force_rebuild(tmp_path: Path):
    log = _run_start_script(tmp_path, image_exists=True, force_rebuild=True)
    assert "compose -f docker-compose.client.yml build app" in log
    assert "compose -f docker-compose.client.yml up -d --no-build" in log
