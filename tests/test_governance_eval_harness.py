import json
import sys
from pathlib import Path

import tools.governance_eval_harness as harness_mod


def test_eval_harness_outputs_report(tmp_path: Path, monkeypatch):
    dataset = tmp_path / "episodes.jsonl"
    dataset.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "labels": {"train_eligible": True, "gold": False},
                        "events": [
                            {"type": "tool.contract.validation", "passed": True},
                            {"type": "policy.check.decision", "decision": "allow"},
                            {"type": "llm.response.parsed"},
                        ],
                    }
                ),
                json.dumps(
                    {
                        "labels": {"train_eligible": False, "gold": False},
                        "events": [
                            {"type": "tool.contract.validation", "passed": False},
                            {"type": "policy.check.decision", "decision": "deny"},
                            {"type": "llm.parse_failed"},
                        ],
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    report = tmp_path / "eval-report.json"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "governance_eval_harness.py",
            "--dataset-jsonl",
            str(dataset),
            "--output",
            str(report),
            "--min-tool-contract-pass-rate",
            "0.40",
            "--max-policy-violation-rate",
            "0.60",
            "--min-json-tool-call-validity",
            "0.40",
            "--max-approval-reject-rate",
            "1.00",
        ],
    )
    rc = harness_mod.main()
    assert rc == 0
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert payload["metrics"]["total_episodes"] == 2
    assert payload["metrics"]["tool_contract_pass_rate"] == 0.5
