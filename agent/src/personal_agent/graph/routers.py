import logging

from personal_agent.common.log_messages import LogMessages
from personal_agent.graph.state import AgentState

logger = logging.getLogger(__name__)


def route_after_generation(state: AgentState) -> str:
    """도구 호출 여부에 따라 다음 그래프 노드를 선택한다."""
    last_message = state["messages"][-1]
    route = "tools" if getattr(last_message, "tool_calls", None) else "end"
    logger.info(LogMessages.ROUTE_SELECTED, route)
    return route
