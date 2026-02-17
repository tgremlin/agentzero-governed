from python.helpers.api import ApiHandler, Request, Response


class SystemTrace(ApiHandler):
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

        return {
            "ok": True,
            "coming_soon": True,
            "message": "System/trace datasets are not wired yet. UI and API contract are scaffolded.",
            "count": 0,
            "total": 0,
            "offset": offset,
            "limit": limit,
            "items": [],
            "types": [
                {"key": "trace_spans", "label": "Trace Spans", "status": "coming_soon"},
                {"key": "trace_events", "label": "Trace Events", "status": "coming_soon"},
                {"key": "trace_scores", "label": "Trace Scores", "status": "coming_soon"},
                {"key": "dataset_exports", "label": "Dataset Exports", "status": "coming_soon"},
            ],
        }
