import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import models
from python.helpers.rate_limiter import RateLimiter


def test_rate_limiter_add_and_get_total() -> None:
    limiter = RateLimiter(seconds=60, requests=10)
    limiter.add(requests=3)
    limiter.add(requests=2)

    total = asyncio.run(limiter.get_total("requests"))
    assert total == 5


def test_apply_rate_limiter_returns_configured_limiter() -> None:
    cfg = models.ModelConfig(
        type=models.ModelType.CHAT,
        provider="demo",
        name="demo/model",
        limit_requests=5,
        limit_input=1000,
        limit_output=500,
    )

    limiter = asyncio.run(models.apply_rate_limiter(cfg, "hello world"))
    assert limiter is not None
    assert limiter.limits["requests"] == 5
    assert limiter.limits["input"] == 1000
    assert limiter.limits["output"] == 500

    requests_total = asyncio.run(limiter.get_total("requests"))
    input_total = asyncio.run(limiter.get_total("input"))
    assert requests_total >= 1
    assert input_total >= 1
