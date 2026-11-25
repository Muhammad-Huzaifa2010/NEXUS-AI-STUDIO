from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TaskRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    request: str = Field(min_length=3, max_length=12000)


class TaskResponse(BaseModel):
    task_id: str | None = None
    status: str
    workflow: str
    selected_agent: str
    response: str
    tool_events: list[dict[str, Any]] = Field(default_factory=list)
    activity_events: list[dict[str, Any]] = Field(default_factory=list)
