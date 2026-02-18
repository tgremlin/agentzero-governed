from pathlib import Path


def test_local_image_services_use_pull_policy_never():
    text = Path("/a0/docker-compose.client.yml").read_text(encoding="utf-8")
    assert "app:\n" in text
    assert "governance-worker:\n" in text
    assert "slack-socket-listener:\n" in text
    assert text.count("pull_policy: never") >= 3
