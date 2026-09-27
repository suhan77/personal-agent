import logging

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult, LLMResult
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import PrivateAttr

from personal_agent.config.settings import Settings
from personal_agent.common.log_messages import LogMessages
from personal_agent.llm.granite.llm_config import GraniteLLMConfig
from personal_agent.llm.granite.tool_call_parser import parse_tool_calls
from personal_agent.llm.huggingface_llm import LocalHuggingFaceChatModel, load_local_pipeline

logger = logging.getLogger(__name__)


class GraniteChatModel(LocalHuggingFaceChatModel):
    """Granite의 대화 형식과 tool 호출 결과를 LangChain 메시지로 변환한다."""

    enable_thinking: bool = False
    _bound_tools: list[dict[str, object]] = PrivateAttr(default_factory=list)

    @classmethod
    def from_settings(cls, settings: Settings) -> tuple["GraniteChatModel", GraniteLLMConfig]:
        """Granite 설정에서 모델과 토크나이저를 불러온다."""
        config = GraniteLLMConfig()
        model_path = settings.model_dir / config.directory_name
        local_pipeline, tokenizer = load_local_pipeline(model_path, config.parameters)
        model = cls(
            llm=local_pipeline,
            tokenizer=tokenizer,
            model_id=str(model_path),
            enable_thinking=config.enable_thinking,
        )
        return model, config

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

    def bind_tools(self, tools: list[BaseTool], **kwargs: object) -> "GraniteChatModel":
        """모델 프롬프트에 사용할 tool 정의를 연결한다."""
        bound_model = self.model_copy()
        bound_model._bound_tools = [convert_to_openai_tool(tool) for tool in tools]
        return bound_model

    @staticmethod
    def _to_chat_result(llm_result: LLMResult) -> ChatResult:
        chat_generations = []
        for generation in llm_result.generations[0]:
            logger.info(LogMessages.MODEL_OUTPUT_LENGTH, len(generation.text))
            content, tool_calls = parse_tool_calls(generation.text)
            chat_generations.append(
                ChatGeneration(
                    message=AIMessage(content=content, tool_calls=tool_calls),
                    generation_info=generation.generation_info,
                )
            )
        return ChatResult(
            generations=chat_generations,
            llm_output=llm_result.llm_output,
        )
