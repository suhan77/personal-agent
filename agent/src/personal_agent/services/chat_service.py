from uuid import uuid4

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.checkpoint.base import BaseCheckpointSaver

from personal_agent.common.errors import AgentError
from personal_agent.common.log_messages import LogMessages
from personal_agent.common.timing import log_timed
from personal_agent.llm.registry_llm import ChatModels
from personal_agent.chain.prompts import SYSTEM_PROMPT
from personal_agent.graph.graph import build_agent_graph
from personal_agent.schemas.agent import AgentRequest, AgentResponse


class AgentService:
    def __init__(
        self,
        models: ChatModels,
        checkpointer: BaseCheckpointSaver,
    ) -> None:
        self.graph = build_agent_graph(models, checkpointer)

    @log_timed(LogMessages.FULL_CONVERSATION)
    async def run(self, request: AgentRequest) -> AgentResponse:
        conversation_id = request.conversation_id or uuid4()
        config = {
            "configurable": {
                "thread_id": str(conversation_id),
            }
        }

        try:
            result = await self.graph.ainvoke(
                {
                    "messages": [
                        SystemMessage(content=SYSTEM_PROMPT, id="system"),
                        HumanMessage(content=request.message),
                    ],
                    "model": request.model.value,
                    "working_directory": request.working_directory,
                },
                config=config,
            )
        except Exception as exc:
            raise AgentError(f"Agent graph execution failed: {exc}") from exc

        response = result["messages"][-1]
        return AgentResponse(
            answer=response.text,
            conversation_id=conversation_id,
            model=request.model,
        )
