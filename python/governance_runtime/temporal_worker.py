from __future__ import annotations

import os
import time


def main() -> int:
    """Placeholder worker entrypoint until Temporal workflows are wired.

    Keeping this module allows docker compose service wiring and staged rollout.
    """
    host = os.environ.get("TEMPORAL_HOST", "temporal:7233")
    namespace = os.environ.get("TEMPORAL_NAMESPACE", "agentzero")
    queue = os.environ.get("TEMPORAL_TASK_QUEUE", "agentzero-governance")
    print(
        "governance temporal worker placeholder running "
        f"host={host} namespace={namespace} queue={queue}",
        flush=True,
    )
    while True:
        time.sleep(60)


if __name__ == "__main__":
    raise SystemExit(main())
