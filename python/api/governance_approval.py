from python.helpers.api import ApiHandler, Request, Response
from python.helpers.governance_gate import resolve_approval


class GovernanceApproval(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict | Response:
        approval_id = str(input.get("approval_id", "")).strip()
        decision = str(input.get("decision", "")).strip()
        rationale = str(input.get("rationale", "")).strip()
        ctxid = str(input.get("context_id", input.get("context", ""))).strip()

        if not approval_id:
            return Response('{"error":"approval_id is required"}', status=400, mimetype="application/json")
        if decision.lower() not in {"approved", "denied", "reject", "rejected"}:
            return Response('{"error":"decision must be approved|denied"}', status=400, mimetype="application/json")

        context = self.use_context(ctxid)
        result = resolve_approval(context.agent0, approval_id, decision, rationale)
        return {
            "ok": True,
            **result,
        }
