#!/usr/bin/env python3
"""
Static governance bypass sentinel for Agent Zero.

Fails if:
1) Agent canonical dispatcher does not call evaluate_tool_gate before tool.execute.
2) input.py does direct CodeExecution(...) without governance gate.
3) Any direct CodeExecution(...) usage exists without a nearby gate call.
4) create_subprocess_shell appears without governance provenance assertion.
5) CodeExecution.execute misses runtime provenance assertion guard.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEARCH_ROOT = ROOT if (ROOT / "python").exists() else ROOT / "data/a0"
AGENT_PY = SEARCH_ROOT / "agent.py"
INPUT_PY = SEARCH_ROOT / "python/tools/input.py"
GATE_PY = SEARCH_ROOT / "python/helpers/governance_gate.py"
CODE_EXEC_TOOL_PY = SEARCH_ROOT / "python/tools/code_execution_tool.py"
EXCLUDED_PARTS = {
    "__pycache__",
    ".venv",
    "venv",
    "site-packages",
    "node_modules",
    ".git",
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _is_excluded(path: Path) -> bool:
    return any(part in EXCLUDED_PARTS for part in path.parts)


def check_agent_dispatcher() -> list[str]:
    errors: list[str] = []
    text = _read(AGENT_PY)

    gate_idx = text.find("evaluate_tool_gate(")
    execute_idx = text.find("response = await tool.execute(")

    if execute_idx == -1:
        errors.append("agent.py: canonical tool.execute call not found")
        return errors

    if gate_idx == -1:
        errors.append(
            "agent.py: missing evaluate_tool_gate(...) in canonical dispatcher before tool.execute"
        )
        return errors

    if gate_idx > execute_idx:
        errors.append("agent.py: evaluate_tool_gate appears after tool.execute (invalid order)")

    if "__governance_gate_evaluated" not in text:
        errors.append("agent.py: missing provenance token stamping in dispatcher")

    return errors


def check_input_bypass() -> list[str]:
    errors: list[str] = []
    text = _read(INPUT_PY)
    if "CodeExecution(" in text and "evaluate_tool_gate(" not in text:
        errors.append("input.py: CodeExecution path missing governance gate")
    return errors


def check_direct_codeexecution_calls() -> list[str]:
    errors: list[str] = []
    candidates = list(SEARCH_ROOT.rglob("*.py"))
    for path in candidates:
        if _is_excluded(path):
            continue
        text = _read(path)
        if "CodeExecution(" not in text:
            continue

        # Ignore class definition file itself
        if path.as_posix().endswith("/python/tools/code_execution_tool.py"):
            continue

        # Require a governance gate call in same file if CodeExecution is instantiated.
        if "evaluate_tool_gate(" not in text and "enforce_tool_gate_or_raise(" not in text:
            errors.append(
                f"{path}: direct CodeExecution(...) usage without governance gate call"
            )

    return errors



def check_codeexecution_provenance_assertion() -> list[str]:
    errors: list[str] = []
    text = _read(CODE_EXEC_TOOL_PY)
    if "assert_governance_provenance(" not in text:
        errors.append("code_execution_tool.py: missing assert_governance_provenance(...) runtime guard")
    return errors

def check_subprocess_shell_classification() -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    gate_text = _read(GATE_PY)
    if "_risk_for_tool(" not in gate_text:
        errors.append("governance_gate.py: risk classification function not found")

    for path in SEARCH_ROOT.rglob("*.py"):
        if _is_excluded(path):
            continue
        text = _read(path)
        if "create_subprocess_shell" not in text:
            continue
        # TTY helper is expected, but it must assert provenance before spawn.
        if "assert_tty_session_provenance(" not in text and "assert_governance_provenance(" not in text:
            errors.append(
                f"{path}: create_subprocess_shell used without provenance assertion"
            )

    return errors, warnings


def main() -> int:
    errs = []
    warns = []
    errs.extend(check_agent_dispatcher())
    errs.extend(check_input_bypass())
    errs.extend(check_direct_codeexecution_calls())
    errs.extend(check_codeexecution_provenance_assertion())
    sub_errs, sub_warns = check_subprocess_shell_classification()
    errs.extend(sub_errs)
    warns.extend(sub_warns)

    if errs:
        print("Governance sentinel FAILED:")
        for e in errs:
            print(f"- {e}")
        for w in warns:
            print(w)
        return 1

    print("Governance sentinel PASSED")
    for w in warns:
        print(w)
    return 0


if __name__ == "__main__":
    sys.exit(main())
