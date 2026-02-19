#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.client.yml}"
SERVICE_NAME="${SERVICE_NAME:-app}"
PROJECT_NAME="${PROJECT_NAME:-governance-preflight}"
WORKDIR="${WORKDIR:-/a0/tmp/governance-preflight}"

echo "[preflight] running governed release gates in ${SERVICE_NAME} (${COMPOSE_FILE})"

docker compose -f "${COMPOSE_FILE}" exec -T "${SERVICE_NAME}" /bin/bash -lc "
set -euo pipefail
cd /a0

export A0_GOV_TRACE_DIR='${WORKDIR}/datasets'
export A0_GOV_TRAINING_EVENTS_FILE='${WORKDIR}/datasets/training-lifecycle.jsonl'
export A0_GOVERNANCE_DIR='${WORKDIR}/governance'
export GOV_PERSIST_BACKEND='file'

rm -rf '${WORKDIR}'
mkdir -p '${WORKDIR}/datasets' '${WORKDIR}/governance/events'

/opt/venv-a0/bin/python - <<'PY'
import datetime as dt
import json
import pathlib

from python.governance_runtime.audit_events import build_audit_event

root = pathlib.Path('${WORKDIR}')
project = '${PROJECT_NAME}'
now = dt.datetime.now(dt.timezone.utc)
now_iso = now.isoformat().replace('+00:00', 'Z')

records = [
    {
        'episode_id': 'ep_preflight_1',
        'run_id': 'run_preflight_1',
        'project_name': project,
        'labels': {'train_eligible': True, 'gold': True},
        'events': [
            {'type': 'tool.contract.validation', 'passed': True},
            {'type': 'policy.check.decision', 'decision': 'allow'},
            {'type': 'llm.response.parsed'},
        ],
    },
    {
        'episode_id': 'ep_preflight_2',
        'run_id': 'run_preflight_2',
        'project_name': project,
        'labels': {'train_eligible': True, 'gold': False},
        'events': [
            {'type': 'tool.contract.validation', 'passed': True},
            {'type': 'policy.check.decision', 'decision': 'allow'},
            {'type': 'llm.response.parsed'},
            {'type': 'gate.retry.scheduled'},
        ],
    },
]

dataset_jsonl = root / 'datasets' / 'episodes.preflight.jsonl'
dataset_jsonl.write_text(''.join(json.dumps(r, sort_keys=True) + '\n' for r in records), encoding='utf-8')

manifest = {
    'dataset_version': 'governance.flywheel.v1',
    'project_name': project,
    'purpose': 'training',
    'generated_at': now_iso,
    'record_count': 2,
    'gold_count': 1,
    'source_event_count': 6,
    'sha256': 'preflight',
}
(root / 'datasets' / 'dataset.preflight.manifest.json').write_text(
    json.dumps(manifest, sort_keys=True, indent=2) + '\n',
    encoding='utf-8',
)

audit_event = build_audit_event(
    base_event={
        'type': 'run.started',
        'project_name': project,
        'created_at': now_iso,
        'actor_id': 'actor_agent_runtime',
        'actor_type': 'agent',
    },
    tenant_id='tenant_default',
    deployment_id='deployment_default',
    run_id='run_preflight_1',
    sequence_number=1,
)
(root / 'governance' / 'events' / f\"events-{now.strftime('%Y%m%d')}.jsonl\").write_text(
    json.dumps(audit_event, sort_keys=True) + '\n',
    encoding='utf-8',
)
PY

/opt/venv-a0/bin/python tools/governance_training_lifecycle_event.py \
  --stage eval \
  --status succeeded \
  --project-name '${PROJECT_NAME}' \
  --run-id preflight-lifecycle \
  --details '{\"source\":\"governance_release_preflight.sh\"}'

/opt/venv-a0/bin/python tools/governance_eval_harness.py \
  --dataset-jsonl '${WORKDIR}/datasets/episodes.preflight.jsonl' \
  --output '${WORKDIR}/eval-report.json' \
  --min-tool-contract-pass-rate 0.90 \
  --max-policy-violation-rate 0.20 \
  --min-json-tool-call-validity 0.90 \
  --max-approval-reject-rate 1.00

/opt/venv-a0/bin/python tools/governance_release_gate.py \
  --eval-report '${WORKDIR}/eval-report.json' \
  --output '${WORKDIR}/release-gate.json' \
  --lifecycle-project-name '${PROJECT_NAME}' \
  --lifecycle-run-id preflight-release

/opt/venv-a0/bin/python tools/governance_trace_healthcheck.py \
  --project-name '${PROJECT_NAME}' \
  --require-artifacts \
  --max-dataset-age-hours 24 \
  --max-lifecycle-age-hours 24

/opt/venv-a0/bin/python tools/governance_audit_schema_check.py \
  --require-events

/opt/venv-a0/bin/python - <<'PY'
import json
import pathlib
import sys

decision_path = pathlib.Path('${WORKDIR}/release-gate.json')
payload = json.loads(decision_path.read_text(encoding='utf-8'))
decision = str(payload.get('decision', '')).strip().lower()
if decision == 'rollback':
    print(json.dumps({'ok': False, 'reason': 'release gate returned rollback', 'decision': payload}, sort_keys=True))
    sys.exit(1)
print(json.dumps({'ok': True, 'decision': decision, 'report_path': str(decision_path)}, sort_keys=True))
PY
"

echo "[preflight] outputs:"
echo "  ${WORKDIR}/eval-report.json"
echo "  ${WORKDIR}/release-gate.json"
