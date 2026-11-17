"""Pure helpers for NEXUS multi-agent workflow routing and shared context."""

import json
import re
from typing import Any, Mapping


APPROVED_AGENTS = frozenset({"research", "execution", "content", "deep_analysis"})


def build_agent_context(state: Mapping[str, Any]) -> str:
    """Build the shared context passed from one specialist to the next."""
    original_request = state.get("request", "")
    agent_outputs = state.get("agent_outputs", {}) or {}
    previous_outputs = json.dumps(
        agent_outputs,
        ensure_ascii=False,
        indent=2,
    )
    return (
        f"Original user request:\n{original_request}\n\n"
        f"Previous specialist outputs (JSON):\n{previous_outputs}\n\n"
        "Continue the original task using previous outputs. Do not repeat "
        "completed work. Distinguish verified results from assumptions and "
        "state limitations clearly."
    )



def extract_sources_section(report: str) -> str:
    """Extract the original Sources section without rewriting it."""
    if not isinstance(report, str) or not report:
        return ""

    match = re.search(
        r"(?im)^[ \t]{0,3}#{1,6}[ \t]+"
        r"(?:\d+[.)]?[ \t]+)?Sources[ \t]*$",
        report,
    )
    return report[match.start():].strip() if match else ""


def remove_sources_section(report: str) -> str:
    """Remove a generated Sources section before appending canonical sources."""
    if not isinstance(report, str) or not report:
        return ""

    match = re.search(
        r"(?im)^[ \t]{0,3}#{1,6}[ \t]+"
        r"(?:\d+[.)]?[ \t]+)?Sources[ \t]*$",
        report,
    )
    return report[:match.start()].rstrip() if match else report.rstrip()


def save_agent_output(
    state: Mapping[str, Any],
    key: str,
    response: str,
) -> dict[str, str]:
    """Return a new output map while preserving earlier specialist results."""
    outputs = dict(state.get("agent_outputs", {}) or {})
    outputs[key] = response
    return outputs


async def advance_workflow(state: Mapping[str, Any]) -> dict[str, int]:
    """Advance the index after the current specialist has completed."""
    return {"current_step": int(state.get("current_step", 0)) + 1}


def select_agent(state: Mapping[str, Any]) -> str:
    """Select the first agent from the validated plan, with a safe fallback."""
    plan = state.get("task_plan") or ["content"]
    first_agent = plan[0] if isinstance(plan, list) and plan else "content"
    return first_agent if first_agent in APPROVED_AGENTS else "content"


def route_after_agent(state: Mapping[str, Any]) -> str:
    """Route to the next planned specialist or to final synthesis."""
    plan = state.get("task_plan", []) or []
    index = int(state.get("current_step", 0))
    if index < len(plan) and plan[index] in APPROVED_AGENTS:
        return plan[index]
    return "finalize"
