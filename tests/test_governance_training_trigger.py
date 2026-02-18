import datetime as dt
import json
import sys

import tools.governance_training_trigger as trigger_mod
from tools.governance_training_trigger import evaluate_training_trigger


def _iso(days_ago: int) -> str:
    return (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days_ago)).isoformat()


def test_evaluate_training_trigger_emits_true_when_thresholds_met():
    manifests = [
        {
            "purpose": "training",
            "generated_at": _iso(1),
            "record_count": 150,
            "gold_count": 30,
            "sha256": "abc",
            "_path": "/tmp/a.manifest.json",
        },
        {
            "purpose": "training",
            "generated_at": _iso(1),
            "record_count": 120,
            "gold_count": 25,
            "sha256": "def",
            "_path": "/tmp/b.manifest.json",
        },
    ]
    out = evaluate_training_trigger(
        manifests,
        min_record_count=200,
        min_gold_count=50,
        max_manifest_age_days=7,
    )
    assert out["trigger_training"] is True
    assert out["eligible_manifests"] == 2
    assert out["total_records"] == 270
    assert out["total_gold"] == 55


def test_evaluate_training_trigger_ignores_stale_and_eval_manifests():
    manifests = [
        {
            "purpose": "eval",
            "generated_at": _iso(1),
            "record_count": 1000,
            "gold_count": 1000,
            "_path": "/tmp/eval.manifest.json",
        },
        {
            "purpose": "training",
            "generated_at": _iso(30),
            "record_count": 1000,
            "gold_count": 1000,
            "_path": "/tmp/stale.manifest.json",
        },
        {
            "purpose": "training",
            "generated_at": _iso(1),
            "record_count": 30,
            "gold_count": 2,
            "_path": "/tmp/fresh.manifest.json",
        },
    ]
    out = evaluate_training_trigger(
        manifests,
        min_record_count=100,
        min_gold_count=10,
        max_manifest_age_days=7,
    )
    assert out["trigger_training"] is False
    assert out["eligible_manifests"] == 1
    assert out["total_records"] == 30
    assert out["total_gold"] == 2


def test_training_trigger_cli_emits_lifecycle_event(tmp_path, monkeypatch):
    manifest = tmp_path / "sample.manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "purpose": "training",
                "generated_at": _iso(0),
                "record_count": 100,
                "gold_count": 20,
                "sha256": "abc",
            }
        ),
        encoding="utf-8",
    )
    out_file = tmp_path / "trigger.json"
    lifecycle = tmp_path / "training-lifecycle.jsonl"

    monkeypatch.setenv("A0_GOV_TRAINING_EVENTS_FILE", str(lifecycle))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "governance_training_trigger.py",
            "--datasets-dir",
            str(tmp_path),
            "--min-record-count",
            "50",
            "--min-gold-count",
            "10",
            "--max-manifest-age-days",
            "7",
            "--output",
            str(out_file),
            "--lifecycle-project-name",
            "p1",
            "--lifecycle-run-id",
            "trigger-run-1",
        ],
    )

    rc = trigger_mod.main()
    assert rc == 0
    rows = [json.loads(line) for line in lifecycle.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert rows
    assert rows[-1]["event_type"] == "training.trigger.decision"
    assert rows[-1]["status"] == "triggered"
