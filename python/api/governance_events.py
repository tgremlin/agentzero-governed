import csv
import datetime as dt
import io
import json

from python.helpers.api import ApiHandler, Request, Response
from python.helpers import projects
from python.helpers.governance_gate import load_governance_events


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


def _event_ts(event: dict) -> dt.datetime | None:
    for key in ("event_ts", "created_at", "updated_at"):
        parsed = _parse_iso_dt(event.get(key))
        if parsed is not None:
            return parsed
    return None


def _matches_filters(
    event: dict,
    *,
    q: str,
    event_type: str,
    status: str,
    run_id: str,
    from_ts: dt.datetime | None,
    to_ts: dt.datetime | None,
) -> bool:
    if event_type and str(event.get("type", "")).strip().lower() != event_type:
        return False
    if status and str(event.get("status", "")).strip().lower() != status:
        return False
    if run_id and str(event.get("run_id", "")).strip() != run_id:
        return False

    ts = _event_ts(event)
    if from_ts and ts and ts < from_ts:
        return False
    if to_ts and ts and ts > to_ts:
        return False
    if (from_ts or to_ts) and ts is None:
        return False

    if q:
        haystack = json.dumps(event, sort_keys=True, default=str).lower()
        if q not in haystack:
            return False
    return True


def _events_to_csv(events: list[dict]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(
        buf,
        fieldnames=[
            "event_ts",
            "created_at",
            "type",
            "status",
            "project_name",
            "context_id",
            "run_id",
            "approval_id",
            "tool_name",
            "risk",
            "signal",
        ],
        extrasaction="ignore",
    )
    writer.writeheader()
    for event in events:
        writer.writerow(event)
    return buf.getvalue()


class GovernanceEvents(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict | Response:
        limit = int(input.get("limit", 200) or 200)
        limit = max(1, min(limit, 5000))
        offset = int(input.get("offset", 0) or 0)
        offset = max(0, offset)

        project_name = str(input.get("project_name", "")).strip() or None
        q = str(input.get("q", "")).strip().lower()
        event_type = str(input.get("event_type", "")).strip().lower()
        status = str(input.get("status", "")).strip().lower()
        run_id = str(input.get("run_id", "")).strip()
        export_format = str(input.get("export_format", "")).strip().lower()
        from_ts = _parse_iso_dt(input.get("from_ts"))
        to_ts = _parse_iso_dt(input.get("to_ts"))

        ctxid = str(input.get("context_id", input.get("context", ""))).strip()
        if not project_name and ctxid:
            context = self.use_context(ctxid, create_if_not_exists=False)
            project_name = projects.get_context_project_name(context)

        # Pull a wider window first, then filter/paginate in API layer.
        raw_events = load_governance_events(project_name=project_name, limit=max(10000, limit + offset))
        filtered = [
            event
            for event in raw_events
            if isinstance(event, dict)
            and _matches_filters(
                event,
                q=q,
                event_type=event_type,
                status=status,
                run_id=run_id,
                from_ts=from_ts,
                to_ts=to_ts,
            )
        ]

        total = len(filtered)
        events = filtered[offset : offset + limit]

        if export_format in {"jsonl", "csv"}:
            if export_format == "jsonl":
                body = "".join(json.dumps(event, sort_keys=True, default=str) + "\n" for event in events)
                return Response(
                    body,
                    status=200,
                    mimetype="application/x-ndjson",
                    headers={
                        "Content-Disposition": "attachment; filename=governance-events.jsonl",
                    },
                )
            body = _events_to_csv(events)
            return Response(
                body,
                status=200,
                mimetype="text/csv",
                headers={
                    "Content-Disposition": "attachment; filename=governance-events.csv",
                },
            )

        return {
            "ok": True,
            "project_name": project_name,
            "total": total,
            "offset": offset,
            "limit": limit,
            "count": len(events),
            "events": events,
        }
