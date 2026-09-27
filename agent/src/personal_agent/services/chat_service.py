from uuid import uuid4

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.types import Command

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

        return self._response(result, conversation_id, request.model)

    async def resume(self, conversation_id, decision: str) -> AgentResponse | dict:
        if decision not in {"approve", "reject"}:
            raise ValueError("Decision must be approve or reject")
        config = {"configurable": {"thread_id": str(conversation_id)}}
        state = await self.graph.aget_state(config)
        if not state.next or "review_file_change" not in state.next:
            raise ValueError("No file change is awaiting review")
        result = await self.graph.ainvoke(Command(resume=decision), config=config)
        from personal_agent.llm.define_llm import ChatModelName
        return self._response(result, conversation_id, ChatModelName(state.values["model"]))

    @staticmethod
    def _response(result, conversation_id, model):
        if "__interrupt__" in result:
            proposal = result["__interrupt__"][0].value
            return {"type": "file_edit_proposal", "conversation_id": str(conversation_id), "model": model.value, **proposal}
        response = result["messages"][-1]
        return AgentResponse(
            answer=response.text,
            conversation_id=conversation_id,
            model=model,
        )
