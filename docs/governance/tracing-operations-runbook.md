# Governed Tracing Operations Runbook

## Purpose
Operational guide for day-to-day governed tracing health, incident response, and model promotion safety checks.

## Daily checks
Run from `data/a0/`:

```bash
python3 tools/governance_trace_healthcheck.py --project-name <project_slug> --require-artifacts
python3 tools/governance_training_dashboard.py --project-name <project_slug>
```

Expected:
- Healthcheck exits `0`
- Dashboard JSON has non-zero `sources.training_lifecycle` once pipelines are active

## Pre-release gate sequence
1. Build eval report:
```bash
python3 tools/governance_eval_harness.py --dataset-jsonl <dataset.jsonl> --output <eval-report.json>
```
2. Run promotion decision:
```bash
python3 tools/governance_release_gate.py --eval-report <eval-report.json> --baseline-report <baseline-report.json>
```
3. If decision is `rollback`, stop rollout and investigate before retry.

## Incident response: secret scan or policy failure
1. Freeze promotion:
- Do not run release gate promotion until issue is resolved.
2. Confirm latest lifecycle/policy events:
```bash
python3 tools/governance_system_trace_export.py --type training_lifecycle
```
3. Rotate impacted credentials from secrets manager.
4. Re-run healthcheck and eval harness.
5. Record incident summary in PR/issue with affected run IDs.

## Stuck scheduler task recovery
If a scheduled governance task is stuck in `running`, force-reset it:

```bash
docker exec -i agentzero /opt/venv-a0/bin/python - <<'PY'
import asyncio
from python.helpers.task_scheduler import TaskScheduler, TaskState
TASK_UUID = "<task_uuid>"
async def main():
    s = TaskScheduler.get()
    await s.cancel_task_by_uuid(TASK_UUID, terminate_thread=True)
    await s.update_task(TASK_UUID, state=TaskState.IDLE, last_result="Reset by operator")
    await s.save()
asyncio.run(main())
PY
```

## Escalation triggers
Open/track an issue immediately when any are true:
- `secret_leak_persisted_count > 0`
- `policy_decision_capture_rate < 100%`
- Release gate decision is `rollback` for candidate adapter
- Healthcheck exits non-zero for two consecutive runs
