import json
import sys

import tools.governance_system_trace_export as trace_export_mod


def test_governance_system_trace_export_cli_filters_and_pages(tmp_path, monkeypatch):
    monkeypatch.setattr(
        trace_export_mod,
        "load_system_trace_items",
        lambda type_filter="", project_name="": [
            {"kind": "dataset_exports", "id": "a", "project_name": "p1"},
            {"kind": "training_decisions", "id": "b", "project_name": "p1"},
        ],
    )
    monkeypatch.setattr(
        trace_export_mod,
        "load_system_trace_summary",
        lambda project_name="": {
            "project_name": project_name or None,
            "sources": {"dataset_exports": 1, "training_decisions": 1, "training_lifecycle": 0},
        },
    )

    output = tmp_path / "trace-export.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "governance_system_trace_export.py",
            "--project-name",
            "p1",
            "--type",
            "dataset_exports",
            "--limit",
            "1",
            "--offset",
            "0",
            "--output",
            str(output),
        ],
    )

    rc = trace_export_mod.main()
    assert rc == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["project_name"] == "p1"
    assert payload["type_filter"] == "dataset_exports"
    assert payload["count"] == 1
    assert payload["summary"]["sources"]["dataset_exports"] == 1
