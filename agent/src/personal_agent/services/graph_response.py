"""LangGraph 결과를 Swift 워커 응답으로 변환한다."""

from uuid import UUID

from personal_agent.llm.define_llm import ChatModelName
from personal_agent.schemas.agent import AgentResponse


def to_agent_response(result: dict, conversation_id: UUID, model: ChatModelName) -> AgentResponse | dict:
    if "__interrupt__" in result:
        proposal = result["__interrupt__"][0].value
        if proposal["kind"] == "reminder_proposal":
            return {"type": "reminder_proposal", "conversation_id": str(conversation_id),
                    "model": model.value, "reminder": proposal["reminder"]}
        if proposal["kind"] == "reminder_update_proposal":
            return {"type": "reminder_update_proposal", "conversation_id": str(conversation_id),
                    "model": model.value, "reminder_update": proposal["reminder_update"]}
        return {"type": "file_edit_proposal", "conversation_id": str(conversation_id),
                "model": model.value, **proposal}
    response = result["messages"][-1]
    return AgentResponse(answer=response.text, conversation_id=conversation_id, model=model)
