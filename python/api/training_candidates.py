import csv
import datetime as dt
import hashlib
import io
import json
from typing import Any

from python.helpers.api import ApiHandler, Request, Response
from python.helpers import projects
from python.helpers.governance_gate import load_governance_events
from python.helpers.training_candidates_store import apply_candidate_overrides


ALLOWED_CONSENT_SCOPES = {"audit_only", "eval_allowed", "training_allowed"}
ALLOWED_CANDIDATE_TRACKS = {"llm_training", "agent_tooling", "harness_improvement"}


def _parse_iso_dt(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        return dt.datetime.fromisoformat(raw)
    except Exception:
        return None


def _event_ts(event: dict[str, Any]) -> dt.datetime | None:
    for key in ("event_ts", "created_at", "updated_at"):
        parsed = _parse_iso_dt(event.get(key))
        if parsed is not None:
            return parsed
    return None


def _candidate_from_event(event: dict[str, Any]) -> dict[str, Any] | None:
    event_type = str(event.get("type", "")).strip().lower()
    status = "pending_review"
    summary = ""
    candidate_track = "harness_improvement"
    score = 0.4

    if event_type == "approval.resolved":
        decision = str(event.get("status", "")).strip().lower()
        candidate_track = "llm_training"
        if decision == "approved":
            status = "ready"
            score = 0.9
            summary = "Approved governance decision candidate (LLM track)"
        elif decision in {"denied", "rejected", "reject"}:
            status = "exclude"
            score = 0.2
            summary = "Denied governance decision candidate (LLM track)"
        else:
            score = 0.6
            summary = "Governance decision candidate (LLM track)"
    elif event_type == "tool.contract.validation":
        candidate_track = "agent_tooling"
        passed = bool(event.get("passed", False))
        status = "ready" if not passed else "pending_review"
        score = 0.85 if not passed else 0.5
        summary = "Tool contract candidate (agent tooling track)"
    elif event_type == "policy.check.decision":
        candidate_track = "agent_tooling"
        decision = str(event.get("decision", "")).strip().lower()
        status = "ready" if decision == "deny" else "pending_review"
        score = 0.8 if decision == "deny" else 0.45
        summary = "Policy decision candidate (agent tooling track)"
    elif event_type in {"llm.response.parse_failed", "llm.parse_failed"}:
        candidate_track = "harness_improvement"
        status = "ready"
        score = 0.9
        summary = "LLM parse failure candidate (harness track)"
    elif event_type in {"run.signaled", "run.started"}:
        candidate_track = "harness_improvement"
        status = "pending_review"
        score = 0.45 if event_type == "run.signaled" else 0.4
        summary = "Run lifecycle candidate (harness track)"
    elif event_type == "run.outcome":
        candidate_track = "llm_training"
        outcome = str(event.get("outcome", "")).strip().lower()
        status = "ready" if outcome == "success" else "pending_review"
        score = 0.7 if outcome == "success" else 0.35
        summary = "Run outcome candidate (LLM track)"
    else:
        return None

    candidate_payload = {
        "event_type": event_type,
        "tool_name": event.get("tool_name"),
        "risk": event.get("risk"),
        "status": event.get("status"),
        "signal": event.get("signal"),
        "decision": event.get("decision"),
        "passed": event.get("passed"),
    }
    consent_scope = str(event.get("consent_scope", "")).strip().lower()
    if consent_scope not in ALLOWED_CONSENT_SCOPES:
        consent_scope = "eval_allowed"

    base = {
        "project_name": event.get("project_name"),
        "context_id": event.get("context_id"),
        "run_id": event.get("run_id"),
        "event_type": event_type,
        "created_at": event.get("event_ts") or event.get("created_at") or "",
        "training_status": status,
        "score": score,
        "candidate_track": candidate_track,
        "score_by_track": {
            "llm_training": score if candidate_track == "llm_training" else 0.0,
            "agent_tooling": score if candidate_track == "agent_tooling" else 0.0,
            "harness_improvement": score if candidate_track == "harness_improvement" else 0.0,
        },
        "summary": summary,
        "source_event": event,
        "payload": candidate_payload,
        "consent_scope": consent_scope,
    }

    unique_material = json.dumps(
        {
            "project": base.get("project_name"),
            "run_id": base.get("run_id"),
            "event_type": base.get("event_type"),
            "created_at": base.get("created_at"),
            "payload": candidate_payload,
            "candidate_track": candidate_track,
        },
        sort_keys=True,
        default=str,
    )
    base["candidate_id"] = "cand_" + hashlib.sha256(unique_material.encode("utf-8")).hexdigest()[:16]
    return base


def _matches_filters(
    candidate: dict[str, Any],
    *,
    q: str,
    event_type: str,
    candidate_track: str,
    training_status: str,
    run_id: str,
    consent_scope: str,
    from_ts: dt.datetime | None,
    to_ts: dt.datetime | None,
) -> bool:
    if event_type and str(candidate.get("event_type", "")).strip().lower() != event_type:
        return False
    if candidate_track and str(candidate.get("candidate_track", "")).strip().lower() != candidate_track:
        return False
    if training_status and str(candidate.get("training_status", "")).strip().lower() != training_status:
        return False
    if run_id and str(candidate.get("run_id", "")).strip() != run_id:
        return False
    if consent_scope and str(candidate.get("consent_scope", "")).strip().lower() != consent_scope:
        return False

    ts = _parse_iso_dt(candidate.get("created_at"))
    if from_ts and ts and ts < from_ts:
        return False
    if to_ts and ts and ts > to_ts:
        return False
    if (from_ts or to_ts) and ts is None:
        return False

    if q:
        haystack = json.dumps(candidate, sort_keys=True, default=str).lower()
        if q not in haystack:
            return False
    return True


def _candidates_to_csv(candidates: list[dict[str, Any]]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(
        buf,
        fieldnames=[
            "candidate_id",
            "created_at",
            "event_type",
            "candidate_track",
            "training_status",
            "score",
            "project_name",
            "context_id",
            "run_id",
            "summary",
        ],
        extrasaction="ignore",
    )
    writer.writeheader()
    for item in candidates:
        writer.writerow(item)
    return buf.getvalue()


class TrainingCandidates(ApiHandler):
    @classmethod
    def get_methods(cls) -> list[str]:
        return ["GET", "POST"]

    async def process(self, input: dict, request: Request) -> dict | Response:
        if request.method == "GET":
            input = dict(request.args)

        limit = int(input.get("limit", 200) or 200)
        limit = max(1, min(limit, 5000))
        offset = int(input.get("offset", 0) or 0)
        offset = max(0, offset)

        project_name = str(input.get("project_name", "")).strip() or None
        q = str(input.get("q", "")).strip().lower()
        event_type = str(input.get("event_type", "")).strip().lower()
        candidate_track = str(input.get("candidate_track", "")).strip().lower()
        if candidate_track and candidate_track not in ALLOWED_CANDIDATE_TRACKS:
            candidate_track = ""
        training_status = str(input.get("training_status", input.get("status", ""))).strip().lower()
        run_id = str(input.get("run_id", "")).strip()
        consent_scope = str(input.get("consent_scope", "")).strip().lower()
        if consent_scope and consent_scope not in ALLOWED_CONSENT_SCOPES:
            consent_scope = ""
        export_purpose = str(input.get("export_purpose", "eval")).strip().lower() or "eval"
        export_format = str(input.get("export_format", "")).strip().lower()
        from_ts = _parse_iso_dt(input.get("from_ts"))
        to_ts = _parse_iso_dt(input.get("to_ts"))

        ctxid = str(input.get("context_id", input.get("context", ""))).strip()
        if not project_name and ctxid:
            context = self.use_context(ctxid, create_if_not_exists=False)
            project_name = projects.get_context_project_name(context)

        raw_events = load_governance_events(project_name=project_name, limit=max(10000, limit + offset))
        candidates = []
        for event in raw_events:
            if not isinstance(event, dict):
                continue
            cand = _candidate_from_event(event)
            if cand is None:
                continue
            if not _matches_filters(
                cand,
                q=q,
                event_type=event_type,
                candidate_track=candidate_track,
                training_status=training_status,
                run_id=run_id,
                consent_scope=consent_scope,
                from_ts=from_ts,
                to_ts=to_ts,
            ):
                continue
            candidates.append(cand)

        track_counts = {
            "llm_training": 0,
            "agent_tooling": 0,
            "harness_improvement": 0,
        }
        for item in candidates:
            track = str(item.get("candidate_track", "")).strip().lower()
            if track in track_counts:
                track_counts[track] += 1

        if export_purpose == "training":
            allowed_export_scopes = {"training_allowed"}
        else:
            allowed_export_scopes = {"eval_allowed", "training_allowed"}

        total = len(candidates)
        page = candidates[offset : offset + limit]
        page = apply_candidate_overrides(project_name, page)

        if export_format in {"jsonl", "csv"}:
            page = [item for item in page if str(item.get("consent_scope", "")).strip().lower() in allowed_export_scopes]
            if export_format == "jsonl":
                body = "".join(json.dumps(item, sort_keys=True, default=str) + "\n" for item in page)
                return Response(
                    body,
                    status=200,
                    mimetype="application/x-ndjson",
                    headers={
                        "Content-Disposition": "attachment; filename=training-candidates.jsonl",
                    },
                )
            body = _candidates_to_csv(page)
            return Response(
                body,
                status=200,
                mimetype="text/csv",
                headers={
                    "Content-Disposition": "attachment; filename=training-candidates.csv",
                },
            )

        return {
            "ok": True,
            "project_name": project_name,
            "count": len(page),
            "total": total,
            "offset": offset,
            "limit": limit,
            "items": page,
            "track_counts": track_counts,
        }
