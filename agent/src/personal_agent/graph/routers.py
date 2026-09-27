import logging

from personal_agent.common.log_messages import LogMessages
from personal_agent.graph.state import AgentState

logger = logging.getLogger(__name__)


def route_after_generation(state: AgentState) -> str:
    """도구 호출 여부에 따라 다음 그래프 노드를 선택한다."""
    last_message = state["messages"][-1]
    calls = getattr(last_message, "tool_calls", None) or []
    tool_names = {call["name"] for call in calls}

    if tool_names & {"create_file", "update_file"}:
        route = "review_file_change"
    elif "propose_reminder" in tool_names:
        route = "review_reminder"
    elif tool_names & {"propose_update_reminder", "propose_delete_reminder"}:
        route = "review_reminder_update"
    elif tool_names:
        route = "tools"
    else:
        route = "end"

    logger.info(LogMessages.ROUTE_SELECTED, route)
    return route
