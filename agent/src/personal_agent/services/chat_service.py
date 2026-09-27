from uuid import uuid4

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.base import BaseCheckpointSaver

from personal_agent.common.errors import AgentError
from personal_agent.common.log_messages import LogMessages
from personal_agent.common.timing import log_timed
from personal_agent.llm.registry_llm import ChatModels
from personal_agent.graph.graph import build_agent_graph
from personal_agent.schemas.agent import AgentRequest, AgentResponse
from personal_agent.services.graph_response import to_agent_response


class AgentService:
    """새 사용자 메시지를 기존 대화 그래프에 전달한다."""

    def __init__(
        self,
        models: ChatModels,
        checkpointer: BaseCheckpointSaver,
    ) -> None:
        self.graph = build_agent_graph(models, checkpointer)

    @log_timed(LogMessages.FULL_CONVERSATION)
    async def run(self, request: AgentRequest) -> AgentResponse | dict:
        conversation_id = request.conversation_id or uuid4()
        config = {
            "configurable": {
                "thread_id": str(conversation_id),
            }
        }

        try:
            result = await self.graph.ainvoke(
                {
                    "messages": [HumanMessage(content=request.message)],
                    "model": request.model.value,
                    "working_directory": request.working_directory,
                },
                config=config,
            )
        except Exception as exc:
            raise AgentError(f"Agent graph execution failed: {exc}") from exc

        return to_agent_response(result, conversation_id, request.model)
