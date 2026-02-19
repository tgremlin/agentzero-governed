import datetime as dt

from tools.governance_trace_healthcheck import evaluate_trace_health


def _summary(*, dataset_at: str | None, lifecycle_at: str | None, active_runs: int) -> dict:
    return {
        "project_name": "p1",
        "sources": {"dataset_exports": 1 if dataset_at else 0, "training_lifecycle": 1 if lifecycle_at else 0},
        "dataset_summary": {"latest_generated_at": dataset_at},
        "lifecycle_summary": {"latest_generated_at": lifecycle_at, "active_run_count": active_runs},
    }


def test_trace_health_ok_with_fresh_artifacts_and_no_active_runs():
    now = dt.datetime(2026, 2, 19, 12, 0, tzinfo=dt.timezone.utc)
    dataset_at = "2026-02-19T11:00:00Z"
    lifecycle_at = "2026-02-19T10:30:00Z"
    report = evaluate_trace_health(
        _summary(dataset_at=dataset_at, lifecycle_at=lifecycle_at, active_runs=0),
        require_artifacts=True,
        max_dataset_age_hours=24,
        max_lifecycle_age_hours=24,
        allow_active_runs=False,
        now=now,
    )
    assert report["ok"] is True
    assert all(item["ok"] for item in report["checks"])


def test_trace_health_fails_on_missing_and_stale_data_and_active_runs():
    now = dt.datetime(2026, 2, 19, 12, 0, tzinfo=dt.timezone.utc)
    report = evaluate_trace_health(
        _summary(dataset_at=None, lifecycle_at="2026-02-10T11:00:00Z", active_runs=2),
        require_artifacts=True,
        max_dataset_age_hours=24,
        max_lifecycle_age_hours=24,
        allow_active_runs=False,
        now=now,
    )
    assert report["ok"] is False
    failed = [item["name"] for item in report["checks"] if not item["ok"]]
    assert "dataset_exports_present" in failed
    assert "dataset_freshness" in failed
    assert "lifecycle_freshness" in failed
    assert "active_run_count" in failed
