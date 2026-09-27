"""미리 알림 제안을 만드는 도구. macOS 저장은 별도 승인 단계에서 수행한다."""

from langchain_core.tools import tool

from personal_agent.schemas.reminder import ReminderProposal


@tool("propose_reminder", args_schema=ReminderProposal)
def propose_reminder(**fields: object) -> dict[str, object]:
    """
    제목과 날짜가 확정된 macOS 미리 알림 등록안을 제안한다.
    이 도구는 실제 미리 알림을 저장하지 않는다.
    """
    proposal = ReminderProposal.model_validate(fields)
    if proposal.unsupported_options:
        raise ValueError("자동 등록할 수 없는 옵션: " + ", ".join(proposal.unsupported_options))
    return proposal.model_dump(mode="json")
