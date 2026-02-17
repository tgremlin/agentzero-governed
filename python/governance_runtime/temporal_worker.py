from __future__ import annotations

import asyncio
import os

from temporalio.client import Client
from temporalio.worker import Worker

from python.governance_runtime.temporal_workflow import (
    GovernedRunWorkflow,
    persist_run_signal,
    persist_run_started,
)

async def run_worker() -> None:
    host = os.environ.get("TEMPORAL_HOST", "temporal:7233")
    namespace = os.environ.get("TEMPORAL_NAMESPACE", "default")
    queue = os.environ.get("TEMPORAL_TASK_QUEUE", "agentzero-governance")
    client = await Client.connect(host, namespace=namespace)
    worker = Worker(
        client,
        task_queue=queue,
        workflows=[GovernedRunWorkflow],
        activities=[persist_run_started, persist_run_signal],
    )
    print(f"governance temporal worker running host={host} namespace={namespace} queue={queue}", flush=True)
    await worker.run()


def main() -> int:
    asyncio.run(run_worker())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
