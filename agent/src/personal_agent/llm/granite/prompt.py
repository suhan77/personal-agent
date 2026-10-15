"""Granite conversation formatting and tool binding."""
import logging
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool
from personal_agent.common.log_messages import LogMessages
logger = logging.getLogger(__name__)


class GranitePromptMixin:
    def _to_chat_prompt(self, messages: list[BaseMessage]) -> str:
        """LLM 실행 직전에 Granite 입력 prompt를 만든다.

        LangChain 메시지를 Granite 역할 형식으로 변환하고, 연결된 tool 정의를
        추가한 뒤 tokenizer chat template이 만든 문자열을 반환한다.
        """
        if not messages:
            raise ValueError("At least one message is required.")

        message_dicts = [self._to_chatml_format(message) for message in messages]
        prompt = self.tokenizer.apply_chat_template(
            message_dicts,
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=self.enable_thinking,
            tools=self._bound_tools or None,
        )
        logger.info(LogMessages.MODEL_PROMPT_TOKENS, len(self.tokenizer.encode(prompt)))
        return prompt

    @staticmethod
    def _to_chatml_format(message: BaseMessage) -> dict[str, object]:
        """LangChain 메시지를 Granite chat template 입력 형식으로 변환한다."""
        if isinstance(message, SystemMessage):
            return {"role": "system", "content": message.content}
        if isinstance(message, HumanMessage):
            return {"role": "user", "content": message.content}
        if isinstance(message, ToolMessage):
            return {"role": "tool", "content": message.content}
        if isinstance(message, AIMessage):
            result: dict[str, object] = {"role": "assistant", "content": message.content}
            if message.tool_calls:
                result["tool_calls"] = [
                    {
                        "function": {
                            "name": tool_call["name"],
                            "arguments": tool_call["args"],
                        }
                    }
                    for tool_call in message.tool_calls
                ]
            return result
        raise ValueError(f"Unsupported message type: {type(message).__name__}")

    def bind_tools(self, tools: list[BaseTool], **kwargs: object) -> "GranitePromptMixin":
        """모델 프롬프트에 사용할 tool 정의를 연결한다."""
        bound_model = self.model_copy()
        bound_model._bound_tools = [convert_to_openai_tool(tool) for tool in tools]
        return bound_model

