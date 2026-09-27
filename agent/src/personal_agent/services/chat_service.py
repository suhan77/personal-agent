from uuid import uuid4

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.types import Command

from personal_agent.common.errors import AgentError
from personal_agent.common.log_messages import LogMessages
from personal_agent.common.timing import log_timed
from personal_agent.llm.registry_llm import ChatModels
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
                    "messages": [HumanMessage(content=request.message)],
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

    async def resume_reminder(self, conversation_id, result: dict) -> AgentResponse | dict:
        status = result.get("status")
        if status not in {"saved", "rejected", "failed", "confirmed_saved", "confirmed_not_saved"}:
            raise ValueError("Invalid reminder status")
        if status == "saved" and not result.get("identifier"):
            raise ValueError("Saved reminder identifier is required")
        if status == "failed" and not result.get("error"):
            raise ValueError("Reminder error is required")
        proposal_id = result.get("proposal_id")
        if not isinstance(proposal_id, str) or not proposal_id:
            raise ValueError("Reminder proposal id is required")
        config = {"configurable": {"thread_id": str(conversation_id)}}
        state = await self.graph.aget_state(config)
        proposal = state.values.get("reminder_proposal") or {}
        if proposal.get("call_id") != proposal_id:
            raise ValueError("Reminder proposal does not match the pending review")
        if state.values.get("reminder_result") == result and "review_reminder" not in state.next:
            from personal_agent.llm.define_llm import ChatModelName
            if not state.next:
                return self._response(state.values, conversation_id, ChatModelName(state.values["model"]))
            if set(state.next).issubset({"finish_reminder", "generate"}):
                continued = await self.graph.ainvoke(None, config=config)
                return self._response(continued, conversation_id, ChatModelName(state.values["model"]))
        if not state.next or "review_reminder" not in state.next:
            raise ValueError("No reminder is awaiting review")
        graph_result = await self.graph.ainvoke(Command(resume=result), config=config)
        from personal_agent.llm.define_llm import ChatModelName
        return self._response(graph_result, conversation_id, ChatModelName(state.values["model"]))

    @staticmethod
    def _response(result, conversation_id, model):
        if "__interrupt__" in result:
            proposal = result["__interrupt__"][0].value
            if proposal["kind"] == "reminder_proposal":
                return {"type": "reminder_proposal", "conversation_id": str(conversation_id), "model": model.value, "reminder": proposal["reminder"]}
            return {"type": "file_edit_proposal", "conversation_id": str(conversation_id), "model": model.value, **proposal}
        response = result["messages"][-1]
        return AgentResponse(
            answer=response.text,
            conversation_id=conversation_id,
            model=model,
        )
