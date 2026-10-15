from personal_agent.common.timing import log_timed
import logging
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from langchain_core.tools import BaseTool

from personal_agent.llm.registry_llm import ChatModels
from personal_agent.common.log_messages import LogMessages
from personal_agent.graph.state import AgentState
from personal_agent.llm.define_llm import ChatModelName
from personal_agent.chain.prompts import build_prompt

logger = logging.getLogger(__name__)


class GenerationNode:
    def __init__(self, models: ChatModels, tools: list[BaseTool]) -> None:
        self.models = models
        self.tools = tools

    @log_timed(LogMessages.GENERATION)
    async def run(
        self,
        state: AgentState,
    ) -> dict[str, list[BaseMessage]]:
        workflow = state.get("active_workflow")
        selected_tools = self.tools
        if workflow == "calendar":
            selected_tools = [tool for tool in self.tools if tool.name in {
                "find_calendar_events", "create_calendar_event", "update_calendar_event"
            }]
        model = self.models.get_with_tools(ChatModelName(state["model"]), selected_tools)
        history = [
            message for message in state["messages"]
            if not (isinstance(message, SystemMessage) and message.id == "system")
        ]
        messages = [SystemMessage(content=build_prompt(state.get("active_workflow")), id="system"), *history]
        response = await model.ainvoke(messages)
        latest_user_index = next(
            (i for i in range(len(history) - 1, -1, -1) if history[i].type == "human"), -1
        )
        has_tool_result = any(message.type == "tool" for message in history[latest_user_index + 1:])
        if workflow == "calendar" and not has_tool_result and self._unexecuted_calendar_action(response):
            logger.warning("캘린더 실행 예고만 반환해 실제 호출 또는 확인 질문을 다시 요청합니다")
            response = await model.ainvoke([
                *messages,
                response,
                SystemMessage(content=(
                    "방금 응답은 도구 호출 없이 실행을 예고했습니다. 실제 실행되지 않았습니다. "
                    "제목·시작·종료가 모두 확정됐다면 실제 도구를 호출하세요. "
                    "종료가 빠졌다면 임의로 정하지 말고 몇 시까지인지 질문만 하세요. "
                    "실행 예고나 성공 주장은 쓰지 마세요."
                )),
            ])
            if self._unexecuted_calendar_action(response):
                response = AIMessage(content="캘린더 도구가 호출되지 않아 일정을 변경하지 못했습니다. 제목과 시작·종료 시각을 포함해 다시 요청해 주세요.")
        logger.info(LogMessages.MODEL_RAW_RESPONSE, response.content)
        tool_calls = getattr(response, "tool_calls", [])
        logger.info(
            LogMessages.TOOL_CALLS_DETECTED,
            len(tool_calls),
            [call.get("name") for call in tool_calls],
        )
        return {"messages": [response]}

    @staticmethod
    def _unexecuted_calendar_action(response: BaseMessage) -> bool:
        if getattr(response, "tool_calls", []):
            return False
        content = response.content
        return isinstance(content, str) and any(phrase in content for phrase in (
            "생성합니다", "추가합니다", "수정합니다", "조회합니다", "사용하겠습니다",
            "호출하겠습니다", "생성하겠습니다", "추가하겠습니다", "수정하겠습니다",
            "생성했습니다", "추가했습니다", "수정했습니다", "등록했습니다",
        ))
