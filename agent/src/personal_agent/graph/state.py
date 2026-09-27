from typing import Annotated, Any, NotRequired, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    model: str
    working_directory: str | None
    context: NotRequired[dict[str, Any]]
    file_change: NotRequired[dict[str, Any]]
    file_decision: NotRequired[str]
    reminder_proposal: NotRequired[dict[str, Any]]
    reminder_result: NotRequired[dict[str, Any]]
    active_workflow: NotRequired[str | None]
