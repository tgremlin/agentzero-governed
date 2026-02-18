# Repository Guidelines

## Project Structure & Module Organization
- Backend Python code: `python/`.
- Governance/Temporal runtime: `python/governance_runtime/`.
- API handlers: `python/api/`.
- Frontend assets: `webui/`.
- Tests: `tests/`.
- Documentation: `docs/`.
- Client deployment stack (this fork): `docker-compose.client.yml`, `Dockerfile.client`, `start.sh`, `stop.sh`, `tools/smoke_client_stack.py`.
- External integration tools: `python/tools/slack.py` and `python/tools/gh.py` with prompt specs in `prompts/agent.system.tool.*.md`.

## Build, Test, and Development Commands
Run from repository root:
- `./start.sh`: build and start app + Postgres + Temporal + governance worker.
- `./stop.sh`: stop client stack.
- `python3 tools/smoke_client_stack.py`: verifies `/governance_run_start` and `/governance_run_signal` via Temporal path.
- `PYTHONPATH=$(pwd) .venv/bin/pytest -q tests/`: run Python tests.
- `docker compose -f docker-compose.client.yml ps`: check service health.

## Coding Style & Naming Conventions
- Python: 4-space indentation, `snake_case`, prefer type hints on changed/new code.
- JavaScript: follow existing module style in `webui/js/` with clear names.
- Keep changes scoped and explicit; avoid broad refactors in feature/fix PRs.

## Testing Guidelines
- Framework: `pytest`.
- Test files: `tests/test_*.py`.
- Async tests: always `await` async calls before subscripting results.
- Add regression tests for governance/Temporal/API behavior when fixing bugs.
- Always run tests inside the Docker app container used by CI/CD. Do not run tests on the host.
- Default test command pattern: `docker compose -f docker-compose.client.yml exec -T app /opt/venv-a0/bin/python -m pytest ...`

## Commit & Pull Request Guidelines
- Use short imperative commit subjects (e.g., `Fix governance async test await`).
- PRs should include:
  - change summary and rationale
  - exact validation commands run
  - env/config deltas (`A0_DATA_DIR`, `ALLOWED_ORIGINS`, governance flags)
- Include logs or screenshots for UI/runtime behavior changes.

## Security & Configuration Tips
- Never commit secrets or machine-specific credentials.
- Use `.env.client.example` as template and create local `.env`.
- For LAN/remote browser access with login disabled, set `ALLOWED_ORIGINS` in `.env`.
- Persist user data with `A0_DATA_DIR` so settings/chats survive rebuilds.
- Slack integration token: `SLACK_BOT_TOKEN`.
- GitHub integration token for write actions: `GH_TOKEN` or `GITHUB_TOKEN`.
