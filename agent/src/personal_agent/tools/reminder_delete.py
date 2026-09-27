"""기존 미리 알림 삭제안을 제안하는 도구."""

from langchain_core.tools import tool

from personal_agent.schemas.reminder_delete import ReminderDeleteRequest


@tool("propose_delete_reminder", args_schema=ReminderDeleteRequest)
def propose_delete_reminder(identifier: str) -> dict[str, str]:
    """
    find_reminders로 정확한 대상 식별자를 확인한 뒤 삭제 승인을 요청한다.
    이 도구는 실제 미리 알림을 삭제하지 않는다.
    """
    request = ReminderDeleteRequest.model_validate({"identifier": identifier})
    return request.model_dump()
