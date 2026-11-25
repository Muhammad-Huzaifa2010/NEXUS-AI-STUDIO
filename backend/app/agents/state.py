
from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    request: str
    workflow: str
    selected_agent: str
    response: str

    # Multi-agent orchestration
    task_plan: list[str]
    current_step: int
    agent_outputs: dict[str, str]
    research_sources: list[dict[str, Any]]
    research_limitations: list[str]

    # Existing execution and monitoring
    tool_events: list[dict[str, Any]]
    activity_events: list[dict[str, Any]]
