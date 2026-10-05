"""명확한 사용자 요청과 진행 중 상태로 전용 프롬프트 사용 여부를 결정한다."""

from langchain_core.messages import HumanMessage

from personal_agent.graph.state import AgentState

REMINDER_NAMES = ("미리 알림", "미리알림", "리마인더", "알림")
REMINDER_ACTIONS = ("등록", "추가", "만들", "생성", "설정", "걸어", "넣어", "수정", "변경", "바꿔", "고쳐", "삭제", "지워", "제거")
SHORTCUT_TERMS = (
    "단축키", "keyboard shortcut", "keyboard shortcuts", "macos shortcut", "mac shortcut",
)
SHORTCUT_DESIGN_TERMS = ("도구", "tool", "설계", "구현", "만들")
SHORTCUT_FOLLOW_UPS = (
    "그중", "그거", "그건", "그 항목", "그 키", "그 조합", "위에", "더 알려", "더 추천", "자세히",
    "finder", "파인더", "safari", "사파리", "spotlight", "스포트라이트", "스크린샷", "화면 캡처",
)
CANCEL_WORDS = ("취소", "그만", "하지 마", "하지마")
EXPLANATION_WORDS = ("방법", "어떻게", "설명", "뭐야", "무엇")


def select_workflow(state: AgentState) -> dict[str, str | None]:
    """사용자 요청과 진행 중 상태에 맞는 작업 지침을 선택한다."""
    message = next((item.content for item in reversed(state["messages"]) if isinstance(item, HumanMessage)), "")
    if not isinstance(message, str):
        return {}
    if state.get("active_workflow") == "reminder" and any(word in message for word in CANCEL_WORDS):
        return {"active_workflow": None}
    normalized = message.casefold()
    if (any(name in normalized for name in SHORTCUT_TERMS)
            and not any(term in normalized for term in SHORTCUT_DESIGN_TERMS)):
        return {"active_workflow": "macos_shortcuts"}
    if state.get("active_workflow") == "macos_shortcuts":
        if any(word in message for word in CANCEL_WORDS):
            return {"active_workflow": None}
        if any(word in message for word in SHORTCUT_FOLLOW_UPS):
            return {}
        return {"active_workflow": None}
    if (not any(word in message for word in EXPLANATION_WORDS)
            and any(name in message for name in REMINDER_NAMES)
            and any(action in message for action in REMINDER_ACTIONS)):
        return {"active_workflow": "reminder"}
    if state.get("active_workflow") == "reminder":
        return {}
    return {}
