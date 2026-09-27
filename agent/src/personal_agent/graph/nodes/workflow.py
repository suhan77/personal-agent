"""명확한 사용자 요청과 진행 중 상태로 전용 프롬프트 사용 여부를 결정한다."""

from langchain_core.messages import HumanMessage

from personal_agent.graph.state import AgentState

REMINDER_NAMES = ("미리 알림", "미리알림", "리마인더", "알림")
REMINDER_ACTIONS = ("등록", "추가", "만들", "생성", "설정", "걸어", "넣어", "수정", "변경", "바꿔", "고쳐", "삭제", "지워", "제거")
CANCEL_WORDS = ("취소", "그만", "하지 마", "하지마")
EXPLANATION_WORDS = ("방법", "어떻게", "설명", "뭐야", "무엇")


def select_workflow(state: AgentState) -> dict[str, str | None]:
    """미리 알림 등록·수정의 후속 입력에도 같은 작업 지침을 적용한다."""
    message = next((item.content for item in reversed(state["messages"]) if isinstance(item, HumanMessage)), "")
    if not isinstance(message, str):
        return {}
    if state.get("active_workflow") == "reminder":
        if any(word in message for word in CANCEL_WORDS):
            return {"active_workflow": None}
        return {}
    if (not any(word in message for word in EXPLANATION_WORDS)
            and any(name in message for name in REMINDER_NAMES)
            and any(action in message for action in REMINDER_ACTIONS)):
        return {"active_workflow": "reminder"}
    return {}
