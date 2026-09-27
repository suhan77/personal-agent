"""Swift가 저장을 수행하도록 미리 알림 등록안을 승인 대기한다."""

from langchain_core.messages import ToolMessage
from langgraph.types import interrupt

from personal_agent.schemas.reminder import ReminderProposal


def prepare_reminder(state):
    calls = state["messages"][-1].tool_calls
    if len(calls) != 1 or calls[0]["name"] != "propose_reminder":
        raise ValueError("미리 알림은 한 번에 하나씩 제안해야 합니다")
    proposal = ReminderProposal.model_validate(calls[0]["args"])
    if proposal.unsupported_options:
        raise ValueError("자동 등록할 수 없는 옵션: " + ", ".join(proposal.unsupported_options))
    return {"reminder_proposal": {**proposal.model_dump(mode="json"), "call_id": calls[0]["id"]}}


def review_reminder(state):
    proposal = {key: value for key, value in state["reminder_proposal"].items() if key != "call_id"}
    return {"reminder_result": interrupt({"kind": "reminder_proposal", "reminder": {**proposal, "proposal_id": state["reminder_proposal"]["call_id"]}})}


def finish_reminder(state):
    result = state["reminder_result"]
    status = result["status"]
    if status == "saved":
        content = f"사용자 승인 후 macOS 미리 알림 저장에 성공했습니다. 식별자: {result['identifier']}"
    elif status == "rejected":
        content = "사용자가 미리 알림 등록을 거부했습니다. 저장되지 않았습니다."
    elif status == "confirmed_saved":
        content = "저장 결과를 자동 확인할 수 없어 사용자가 미리 알림 앱에서 등록됨을 직접 확인했습니다."
    elif status == "confirmed_not_saved":
        content = "저장 결과를 자동 확인할 수 없어 사용자가 미리 알림 앱에서 등록되지 않았음을 직접 확인했습니다."
    else:
        content = f"macOS 미리 알림 저장에 실패했습니다: {result['error']}"
    return {"messages": [ToolMessage(content=content, tool_call_id=state["reminder_proposal"]["call_id"])], "active_workflow": None}
