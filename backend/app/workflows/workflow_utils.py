"""Pure helpers for NEXUS multi-agent workflow routing and shared context."""

import json
import re
from typing import Any, Mapping
from urllib.parse import quote, urlsplit


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
        f"Retrieved research sources (JSON):\n"
        f"{json.dumps(state.get('research_sources', []) or [], ensure_ascii=False, indent=2)}\n\n"
        "Continue the original task using previous outputs. Do not repeat "
        "completed work. Distinguish sourced information from assumptions and "
        "state limitations clearly."
    )

def remove_sources_section(report: str) -> str:
    """Remove a generated Sources section before appending canonical sources."""
    if not isinstance(report, str) or not report:
        return ""

    match = re.search(
        r"(?im)^[ \t]{0,3}#{1,6}[ \t]+"
        r"(?:\d+[.)]?[ \t]+)?(?:Sources|Source Links)[ \t]*$",
        report,
    )
    return report[:match.start()].rstrip() if match else report.rstrip()


def _markdown_url(url: str) -> str:
    return quote(url, safe=":/?&=#%+;,@!$'*~-._")


def render_research_sources(response: str, sources: list[dict]) -> str:
    """Append links from retrieved sources and discard model-invented links."""
    body = remove_sources_section(response)
    if not sources:
        return body

    source_by_id = {}
    for source in sources:
        url = str(source.get("url") or "")
        try:
            parsed = urlsplit(url)
        except ValueError:
            continue
        if (
            parsed.scheme.lower() not in {"https", "http"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or not isinstance(source.get("id"), int)
        ):
            continue
        source_by_id[source["id"]] = source

    if not source_by_id:
        return body

    canonical_urls = {source["url"] for source in source_by_id.values()}
    link_pattern = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
    body = link_pattern.sub(
        lambda match: (
            f"[{match.group(1)}]({_markdown_url(match.group(2))})"
            if match.group(2) in canonical_urls
            else match.group(1)
        ),
        body,
    )

    entries = []
    for source_id in sorted(source_by_id):
        source = source_by_id[source_id]
        title = str(source.get("title") or source.get("domain") or "Source")
        for character in ("[", "]", "(", ")"):
            title = title.replace(character, f"\\{character}")
        details = [str(source.get("domain") or "")]
        if source.get("published_date"):
            details.append(f"Published: {source['published_date']}")
        if source.get("source_type"):
            details.append(f"Type: {source['source_type']}")
        entries.append(
            f"- [{title}]({_markdown_url(source['url'])})"
            f" — {' · '.join(details)}"
        )

    return body + "\n\n## Sources\n\n" + "\n".join(entries)


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
