"""기존 미리 알림의 수정·삭제안을 같은 승인 경로에서 처리한다."""

import ast
import json

from langchain_core.messages import ToolMessage
from langgraph.types import interrupt

from personal_agent.schemas.reminder_delete import ReminderDeleteRequest
from personal_agent.schemas.reminder_update import ReminderUpdateRequest
from personal_agent.services.native_tool_bridge import call_native_tool


def _was_found(messages, identifier: str) -> bool:
    search_call_ids = {
        call["id"] for message in messages
        for call in getattr(message, "tool_calls", [])
        if call["name"] == "find_reminders"
    }
    for message in messages:
        if not isinstance(message, ToolMessage) or message.tool_call_id not in search_call_ids:
            continue
        try:
            result = json.loads(message.content) if isinstance(message.content, str) else message.content
        except (json.JSONDecodeError, TypeError):
            try:
                result = ast.literal_eval(message.content)
            except (ValueError, SyntaxError, TypeError):
                continue
        if isinstance(result, dict) and any(
            isinstance(item, dict) and item.get("identifier") == identifier
            for item in result.get("items", [])
        ):
            return True
    return False


async def prepare_reminder_change(state):
    calls = state["messages"][-1].tool_calls
    if len(calls) != 1 or calls[0]["name"] not in {"propose_update_reminder", "propose_delete_reminder"}:
        raise ValueError("미리 알림 수정·삭제는 한 번에 하나씩 제안해야 합니다")
    operation = "delete" if calls[0]["name"] == "propose_delete_reminder" else "update"
    request = (ReminderDeleteRequest if operation == "delete" else ReminderUpdateRequest).model_validate(calls[0]["args"])
    if not _was_found(state["messages"][:-1], request.identifier):
        raise ValueError("먼저 find_reminders로 대상 미리 알림을 조회해 주세요")
    snapshot = await call_native_tool("get_reminder", {"identifier": request.identifier}, timeout=120)
    if not isinstance(snapshot, dict) or snapshot.get("identifier") != request.identifier or not snapshot.get("revision"):
        raise ValueError("대상 미리 알림을 확인할 수 없습니다")
    before = {key: value for key, value in snapshot.items() if key != "revision"}
    changes = request.set.model_dump(mode="json", exclude_unset=True) if operation == "update" else {}
    clear = request.clear if operation == "update" else []
    after = dict(before)
    after.update(changes)
    after.update({key: None for key in clear})
    if operation == "update" and after == before:
        raise ValueError("이미 요청한 값으로 설정돼 있어 변경할 내용이 없습니다")
    return {"reminder_update_proposal": {"call_id": calls[0]["id"], "operation": operation,
                                         "identifier": request.identifier, "revision": snapshot["revision"],
                                         "before": before, "after": after, "set": changes, "clear": clear}}


def review_reminder_change(state):
    proposal = state["reminder_update_proposal"]
    visible = {key: value for key, value in proposal.items() if key != "call_id"}
    return {"reminder_update_result": interrupt({"kind": "reminder_update_proposal", "reminder_update": {
        **visible, "proposal_id": proposal["call_id"]}})}


def finish_reminder_change(state):
    result = state["reminder_update_result"]
    operation = state["reminder_update_proposal"].get("operation", "update")
    status = result["status"]
    if operation == "delete":
        messages = {
            "deleted": "사용자 승인 후 macOS 미리 알림 삭제에 성공했습니다.",
            "rejected": "사용자가 미리 알림 삭제를 거부했습니다. 항목을 유지했습니다.",
            "confirmed_deleted": "삭제 결과를 자동 확인할 수 없어 사용자가 미리 알림 앱에서 삭제됨을 직접 확인했습니다.",
            "confirmed_not_deleted": "삭제 결과를 자동 확인할 수 없어 사용자가 미리 알림 앱에서 삭제되지 않았음을 직접 확인했습니다.",
        }
        content = messages.get(status, f"macOS 미리 알림 삭제에 실패했습니다: {result.get('error', '알 수 없는 오류')}")
    else:
        messages = {
            "saved": "사용자 승인 후 macOS 미리 알림 수정에 성공했습니다.",
            "rejected": "사용자가 미리 알림 수정을 거부했습니다. 변경되지 않았습니다.",
            "confirmed_saved": "수정 결과를 자동 확인할 수 없어 사용자가 미리 알림 앱에서 수정을 직접 확인했습니다.",
            "confirmed_not_saved": "수정 결과를 자동 확인할 수 없어 사용자가 미리 알림 앱에서 수정되지 않았음을 직접 확인했습니다.",
        }
        content = messages.get(status, f"macOS 미리 알림 수정에 실패했습니다: {result.get('error', '알 수 없는 오류')}")
    return {"messages": [ToolMessage(content=content, tool_call_id=state["reminder_update_proposal"]["call_id"])],
            "active_workflow": None}
