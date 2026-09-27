"""미리 알림 수정안을 제안하는 도구."""

from langchain_core.tools import tool

from personal_agent.schemas.reminder_update import ReminderUpdateRequest


@tool("propose_update_reminder", args_schema=ReminderUpdateRequest)
def propose_update_reminder(**fields: object) -> dict:
    """
    find_reminders로 대상의 identifier를 확인한 뒤 기존 미리 알림의 부분 수정을 제안한다.
    set에는 바꿀 값만 넣고, 선택 값을 제거할 때만 clear를 쓴다.
    실제 수정은 사용자 승인 후 macOS에서 수행한다.
    """
    request = ReminderUpdateRequest.model_validate(fields)
    return request.model_dump(mode="json", exclude_unset=True)
