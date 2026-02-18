import json
import subprocess
import tarfile
from pathlib import Path


def test_package_release_creates_bundle(tmp_path: Path):
    out_dir = tmp_path / "dist"
    proc = subprocess.run(
        [
            "/bin/bash",
            "/a0/tools/package_release.sh",
            "--version",
            "9.9.9-test",
            "--output-dir",
            str(out_dir),
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    payload = json.loads(proc.stdout)
    assert payload["ok"] is True
    assert payload["version"] == "9.9.9-test"

    archive = out_dir / "agentzero-governed-v9.9.9-test.tar.gz"
    checksum = out_dir / "agentzero-governed-v9.9.9-test.sha256"
    assert archive.exists()
    assert checksum.exists()

    with tarfile.open(archive, "r:gz") as tar:
        names = tar.getnames()
    assert "agentzero-governed-v9.9.9-test/VERSION" in names
    assert "agentzero-governed-v9.9.9-test/tools/package_release.sh" in names
    assert (
        "agentzero-governed-v9.9.9-test/data/temporal/dynamicconfig/development.yaml"
        in names
    )
