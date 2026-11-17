
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

    # Existing video output
    video_url: str
    video_filename: str

    # Existing execution and monitoring
    tool_events: list[dict[str, Any]]
    activity_events: list[dict[str, Any]]
