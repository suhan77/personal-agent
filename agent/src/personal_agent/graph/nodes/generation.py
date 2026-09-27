from personal_agent.common.timing import log_timing
import logging
from langchain_core.messages import BaseMessage
from langchain_core.tools import BaseTool

from personal_agent.llm.model_factory import ChatModels
from personal_agent.common.log_messages import LogMessages
from personal_agent.graph.state import AgentState
from personal_agent.llm.model_definitions import ChatModelName

logger = logging.getLogger(__name__)


class GenerationNode:
    def __init__(self, models: ChatModels, tools: list[BaseTool]) -> None:
        self.models = models
        self.tools = tools

    async def run(
        self,
        state: AgentState,
    ) -> dict[str, list[BaseMessage]]:
        model = self.models.get_with_tools(ChatModelName(state["model"]), self.tools)
        with log_timing(LogMessages.GENERATION):
            response = await model.ainvoke(state["messages"])
        logger.info(LogMessages.MODEL_RAW_RESPONSE, response.content)
        tool_calls = getattr(response, "tool_calls", [])
        logger.info(
            LogMessages.TOOL_CALLS_DETECTED,
            len(tool_calls),
            [call.get("name") for call in tool_calls],
        )
        return {"messages": [response]}
