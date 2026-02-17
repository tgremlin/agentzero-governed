from python.helpers.api import ApiHandler, Request, Response
from python.helpers import projects
from python.helpers.training_candidates_store import bulk_update_candidates


class TrainingCandidatesUpdate(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict | Response:
        project_name = str(input.get("project_name", "")).strip() or None
        ctxid = str(input.get("context_id", input.get("context", ""))).strip()
        if not project_name and ctxid:
            context = self.use_context(ctxid, create_if_not_exists=False)
            project_name = projects.get_context_project_name(context)

        ids_raw = input.get("candidate_ids", [])
        if not isinstance(ids_raw, list):
            return Response('{"error":"candidate_ids must be a list"}', status=400, mimetype="application/json")

        candidate_ids = [str(x).strip() for x in ids_raw if str(x).strip()]
        if not candidate_ids:
            return Response('{"error":"candidate_ids is required"}', status=400, mimetype="application/json")

        action = str(input.get("action", "")).strip().lower()
        training_status = str(input.get("training_status", "")).strip().lower()
        note = str(input.get("note", "")).strip()

        if action == "reset":
            result = bulk_update_candidates(project_name, candidate_ids, reset=True)
            return {"ok": True, "project_name": project_name, **result}

        if not training_status:
            status_by_action = {
                "mark_ready": "ready",
                "exclude": "exclude",
                "mark_pending": "pending_review",
            }
            training_status = status_by_action.get(action, "")

        if training_status not in {"ready", "pending_review", "exclude"}:
            return Response(
                '{"error":"training_status must be ready|pending_review|exclude or use action mark_ready|mark_pending|exclude|reset"}',
                status=400,
                mimetype="application/json",
            )

        try:
            result = bulk_update_candidates(
                project_name,
                candidate_ids,
                training_status=training_status,
                note=note,
            )
        except ValueError as exc:
            return Response(
                f'{{"error":"{str(exc)}"}}',
                status=400,
                mimetype="application/json",
            )

        return {
            "ok": True,
            "project_name": project_name,
            **result,
        }
