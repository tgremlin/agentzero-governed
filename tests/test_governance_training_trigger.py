import datetime as dt

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
