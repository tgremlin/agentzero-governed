import json
from pathlib import Path

from tools.governance_phase3_rollback_drill import run_rollback_drill


def test_run_rollback_drill_generates_rollback_artifacts(tmp_path: Path):
    out = run_rollback_drill(output_dir=tmp_path)
    assert out["ok"] is True
    assert out["actual_decision"] == "rollback"
    for path in out["paths"].values():
        assert Path(path).exists()

    decision_payload = json.loads(Path(out["paths"]["release_gate"]).read_text(encoding="utf-8"))
    assert decision_payload["decision"] == "rollback"
