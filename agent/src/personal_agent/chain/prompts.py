from datetime import datetime

from personal_agent.chain.reminder_prompt import REMINDER_PROMPT
from personal_agent.chain.macos_shortcuts_prompt import MACOS_SHORTCUTS_PROMPT

WORKFLOW_PROMPTS = {
    "reminder": REMINDER_PROMPT,
    "macos_shortcuts": MACOS_SHORTCUTS_PROMPT,
}


SYSTEM_PROMPT = """
당신은 사용자를 돕는 개인용 로컬 에이전트입니다.
간단한 질문에는 핵심만 짧게 답하고, 자세한 설명이나 코드는 요청받았을 때 제공합니다.
서로 다른 항목을 두 개 이상 설명할 때는 Markdown 목록으로 나누고, 문단이 바뀌면 빈 줄을 넣어 읽기 쉽게 작성합니다.
한 항목 안에서도 문장 사이에 필요한 줄바꿈을 유지하고, 여러 항목을 한 문단에 이어 붙이지 않습니다.

필요한 경우 제공된 도구를 사용해 정보를 확인하거나 작업을 수행합니다.
도구로 확인할 수 있는 내용은 추측하지 않습니다.
도구의 목적과 매개변수를 확인한 뒤 적절한 도구를 선택합니다.
필요한 정보가 없거나 모호하면 확인합니다.
사용자가 요청하지 않은 선택 사항은 임의로 채우지 않습니다.
도구 결과나 승인·저장 결과를 받기 전에는 확인·완료했다고 말하지 않습니다.
도구가 지원하지 않는 작업이나 옵션은 가능한 것처럼 안내하지 않습니다.
"""


def build_system_prompt(now: datetime | None = None) -> str:
    """모든 작업에 공통인 지침과 현재 시각을 반환한다."""
    current = now or datetime.now().astimezone()
    if current.tzinfo is None:
        raise ValueError("Current time must include a time zone")
    return f"{SYSTEM_PROMPT.strip()}\n현재 날짜·시간: {current.isoformat(timespec='minutes')}\n"


def build_prompt(workflow: str | None, now: datetime | None = None) -> str:
    """현재 작업에 필요한 전용 지침만 공통 지침에 조합한다."""
    prompt = build_system_prompt(now)
    if workflow is None:
        return prompt
    else:
        try:
            task_prompt = WORKFLOW_PROMPTS[workflow]
        except KeyError as exc:
            raise ValueError(f"Unknown workflow: {workflow}") from exc
        return f"{prompt}\n{task_prompt.strip()}\n"
