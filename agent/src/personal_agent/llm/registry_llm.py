from langchain_core.language_models import LanguageModelInput
from langchain_core.messages import AIMessage
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI

from personal_agent.config.settings import Settings
from personal_agent.llm.define_llm import ChatModelName, ModelParameters
from personal_agent.llm.granite.mlx_chat_model import GraniteMLXChatModel


class ChatModels:
    """선택한 모델만 초기화하고 재사용한다."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._models = {}
        self._parameters = {}

    def get(self, name: ChatModelName):
        if name not in self._models:
            if name == ChatModelName.GRANITE:
                model, config = GraniteMLXChatModel.from_settings(self._settings)
                self._models[name] = model
                self._parameters[name] = config.parameters
            elif name == ChatModelName.GPT6_LUNA:
                if not self._settings.openai_api_key or not self._settings.openai_api_key.get_secret_value().strip():
                    raise ValueError("OpenAI API 키가 없습니다. agent/.env에 OPENAI_API_KEY를 설정한 뒤 앱을 다시 실행하세요.")
                self._models[name] = ChatOpenAI(
                    model=name.value,
                    api_key=self._settings.openai_api_key,
                    reasoning_effort="none",
                    use_responses_api=False,
                    max_completion_tokens=2048,
                    timeout=60,
                    max_retries=1,
                )
                # Bound history for latency and cost rather than filling the API context window.
                self._parameters[name] = ModelParameters(
                    context_window=16_384, max_new_tokens=2048, summary_max_new_tokens=256,
                )
            else:
                raise ValueError(f"Unsupported model: {name}")
        return self._models[name]

    def get_parameters(self, name: ChatModelName) -> ModelParameters:
        self.get(name)
        return self._parameters[name]

    def get_summary_model(self, name: ChatModelName = ChatModelName.GRANITE) -> tuple[Runnable[LanguageModelInput, AIMessage], ModelParameters]:
        parameters = self.get_parameters(name)
        return self.get_with_max_new_tokens(name, parameters.summary_max_new_tokens), parameters

    def get_with_max_new_tokens(self, name: ChatModelName, max_new_tokens: int) -> Runnable:
        model = self.get(name)
        if name == ChatModelName.GRANITE:
            return model.with_max_new_tokens(max_new_tokens)
        return model.bind(max_completion_tokens=max_new_tokens)

    def get_with_tools(self, name: ChatModelName, tools: list[BaseTool]) -> Runnable:
        model = self.get(name)
        if name == ChatModelName.GRANITE:
            return model.bind_tools(tools)
        # Existing proposal tools rely on omitted fields for partial updates.
        return model.bind_tools(tools, strict=False, parallel_tool_calls=False)
