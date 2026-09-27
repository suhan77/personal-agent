from personal_agent.common.timing import log_timed
import logging
from langchain_core.messages import BaseMessage
from langchain_core.tools import BaseTool

from personal_agent.llm.registry_llm import ChatModels
from personal_agent.common.log_messages import LogMessages
from personal_agent.graph.state import AgentState
from personal_agent.llm.define_llm import ChatModelName

logger = logging.getLogger(__name__)


class GenerationNode:
    def __init__(self, models: ChatModels, tools: list[BaseTool]) -> None:
        self.models = models
        self.tools = tools

    @log_timed(LogMessages.GENERATION)
    async def run(
        self,
        state: AgentState,
    ) -> dict[str, list[BaseMessage]]:
        model = self.models.get_with_tools(ChatModelName(state["model"]), self.tools)
        response = await model.ainvoke(state["messages"])
        logger.info(LogMessages.MODEL_RAW_RESPONSE, response.content)
        tool_calls = getattr(response, "tool_calls", [])
        logger.info(
            LogMessages.TOOL_CALLS_DETECTED,
            len(tool_calls),
            [call.get("name") for call in tool_calls],
        )
        return {"messages": [response]}
