from python.helpers.api import ApiHandler, Request, Response
from python.helpers import projects
from python.governance_runtime.temporal_client import is_temporal_enabled, start_governed_run


class GovernanceRunStart(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict | Response:
        if not is_temporal_enabled():
            return Response(
                '{"error":"temporal governance is disabled (set GOV_TEMPORAL_ENABLED=true)"}',
                status=409,
                mimetype="application/json",
            )

        ctxid = str(input.get("context_id", input.get("context", ""))).strip()
        context = self.use_context(ctxid)
        project_name = projects.get_context_project_name(context)

        result = start_governed_run(context_id=context.id, project_name=project_name)
        return {
            "ok": True,
            "context_id": context.id,
            "project_name": project_name,
            **result,
        }
