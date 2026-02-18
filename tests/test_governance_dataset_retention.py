import datetime as dt
import os
from pathlib import Path

from tools.governance_dataset_retention import apply_retention


def _touch_with_age(path: Path, *, days_old: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x\n", encoding="utf-8")
    ts = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days_old)).timestamp()
    os.utime(path, (ts, ts))


def test_apply_retention_dry_run_reports_without_deleting(tmp_path: Path):
    old_file = tmp_path / "exports" / "old.jsonl"
    new_file = tmp_path / "exports" / "new.jsonl"
    _touch_with_age(old_file, days_old=10)
    _touch_with_age(new_file, days_old=1)

    result = apply_retention(tmp_path, max_age_days=7, dry_run=True)
    assert result["checked"] == 2
    assert "exports/old.jsonl" in result["deleted"]
    assert "exports/new.jsonl" in result["retained"]
    assert old_file.exists()
    assert new_file.exists()


def test_apply_retention_deletes_old_artifacts(tmp_path: Path):
    old_jsonl = tmp_path / "batch-a" / "dataset.jsonl"
    old_manifest = tmp_path / "batch-a" / "dataset.manifest.json"
    fresh_manifest = tmp_path / "batch-b" / "dataset.manifest.json"
    _touch_with_age(old_jsonl, days_old=30)
    _touch_with_age(old_manifest, days_old=30)
    _touch_with_age(fresh_manifest, days_old=2)

    result = apply_retention(tmp_path, max_age_days=7, dry_run=False)
    assert sorted(result["deleted"]) == sorted(
        ["batch-a/dataset.jsonl", "batch-a/dataset.manifest.json"]
    )
    assert result["retained"] == ["batch-b/dataset.manifest.json"]
    assert not old_jsonl.exists()
    assert not old_manifest.exists()
    assert fresh_manifest.exists()


def test_apply_retention_ignores_non_dataset_json_files(tmp_path: Path):
    old_misc = tmp_path / "misc" / "notes.json"
    old_manifest = tmp_path / "misc" / "dataset.manifest.json"
    _touch_with_age(old_misc, days_old=30)
    _touch_with_age(old_manifest, days_old=30)

    result = apply_retention(tmp_path, max_age_days=7, dry_run=False)
    assert result["checked"] == 1
    assert result["deleted"] == ["misc/dataset.manifest.json"]
    assert old_misc.exists()
    assert not old_manifest.exists()
