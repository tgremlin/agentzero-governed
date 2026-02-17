from python.helpers.api import ApiHandler, Request, Response
from python.governance_runtime.temporal_client import is_temporal_enabled, signal_governed_run


class GovernanceRunSignal(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict | Response:
        if not is_temporal_enabled():
            return Response(
                '{"error":"temporal governance is disabled (set GOV_TEMPORAL_ENABLED=true)"}',
                status=409,
                mimetype="application/json",
            )

        run_id = str(input.get("run_id", "")).strip()
        signal = str(input.get("signal", "")).strip().lower()
        payload = input.get("payload") if isinstance(input.get("payload"), dict) else {}

        if not run_id:
            return Response('{"error":"run_id is required"}', status=400, mimetype="application/json")

        if signal not in {"pause", "resume", "cancel"}:
            return Response(
                '{"error":"signal must be one of pause|resume|cancel"}',
                status=400,
                mimetype="application/json",
            )

        result = await signal_governed_run(run_id=run_id, signal=signal, payload=payload)
        return {
            "ok": True,
            **result,
        }
