from python.helpers.api import ApiHandler, Request, Response
from python.helpers.system_trace_store import load_system_trace_items


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
        type_filter = str(input.get("type", "")).strip().lower()

        items = load_system_trace_items(type_filter=type_filter)
        total = len(items)
        page = items[offset : offset + limit]

        return {
            "ok": True,
            "coming_soon": False,
            "message": "System trace datasets",
            "count": len(page),
            "total": total,
            "offset": offset,
            "limit": limit,
            "items": page,
            "types": [
                {"key": "trace_spans", "label": "Trace Spans", "status": "planned"},
                {"key": "trace_events", "label": "Trace Events", "status": "planned"},
                {"key": "trace_scores", "label": "Trace Scores", "status": "planned"},
                {"key": "dataset_exports", "label": "Dataset Exports", "status": "active"},
                {"key": "training_decisions", "label": "Training Decisions", "status": "active"},
                {"key": "training_lifecycle", "label": "Training Lifecycle", "status": "active"},
            ],
        }
