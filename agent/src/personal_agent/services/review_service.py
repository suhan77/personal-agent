"""중단된 승인 흐름을 동일한 LangGraph 체크포인트에서 재개한다."""

from uuid import UUID

from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from personal_agent.llm.define_llm import ChatModelName
from personal_agent.schemas.agent import AgentResponse
from personal_agent.services.graph_response import to_agent_response


class ReviewService:
    """파일 변경과 미리 알림 등록·수정·삭제의 승인 결과를 검증하고 재개한다."""

    def __init__(self, graph: CompiledStateGraph) -> None:
        self.graph = graph

    async def resume_file_change(self, conversation_id: UUID, decision: str) -> AgentResponse | dict:
        if decision not in {"approve", "reject"}:
            raise ValueError("Decision must be approve or reject")
        config = {"configurable": {"thread_id": str(conversation_id)}}
        state = await self.graph.aget_state(config)
        if not state.next or "review_file_change" not in state.next:
            raise ValueError("No file change is awaiting review")
        result = await self.graph.ainvoke(Command(resume=decision), config=config)
        return to_agent_response(result, conversation_id, ChatModelName(state.values["model"]))

    async def resume_reminder_creation(self, conversation_id: UUID, result: dict) -> AgentResponse | dict:
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
        return await self._resume_reminder_result(conversation_id, config, state, result,
                                                  result_key="reminder_result", review_node="review_reminder",
                                                  finish_node="finish_reminder")

    async def resume_reminder_change(self, conversation_id: UUID, result: dict) -> AgentResponse | dict:
        status = result.get("status")
        proposal_id = result.get("proposal_id")
        if not isinstance(proposal_id, str) or not proposal_id:
            raise ValueError("Reminder change proposal id is required")
        config = {"configurable": {"thread_id": str(conversation_id)}}
        state = await self.graph.aget_state(config)
        proposal = state.values.get("reminder_update_proposal") or {}
        if proposal.get("call_id") != proposal_id:
            raise ValueError("Reminder change proposal does not match the pending review")
        operation = proposal.get("operation", "update")
        valid_statuses = ({"deleted", "rejected", "failed", "confirmed_deleted", "confirmed_not_deleted"}
                          if operation == "delete" else
                          {"saved", "rejected", "failed", "confirmed_saved", "confirmed_not_saved"})
        if status not in valid_statuses:
            raise ValueError("Invalid reminder change status")
        if status == "failed" and not result.get("error"):
            raise ValueError("Reminder change error is required")
        if status in {"saved", "deleted"} and result.get("identifier") != proposal.get("identifier"):
            raise ValueError("Changed reminder identifier does not match the proposal")
        return await self._resume_reminder_result(conversation_id, config, state, result,
                                                  result_key="reminder_update_result",
                                                  review_node="review_reminder_update",
                                                  finish_node="finish_reminder_update")

    async def _resume_reminder_result(self, conversation_id, config, state, result,
                                      *, result_key: str, review_node: str, finish_node: str) -> AgentResponse | dict:
        model = ChatModelName(state.values["model"])
        if state.values.get(result_key) == result and review_node not in state.next:
            if not state.next:
                return to_agent_response(state.values, conversation_id, model)
            if set(state.next).issubset({finish_node, "generate"}):
                continued = await self.graph.ainvoke(None, config=config)
                return to_agent_response(continued, conversation_id, model)
        if not state.next or review_node not in state.next:
            raise ValueError("No reminder is awaiting review")
        graph_result = await self.graph.ainvoke(Command(resume=result), config=config)
        return to_agent_response(graph_result, conversation_id, model)
