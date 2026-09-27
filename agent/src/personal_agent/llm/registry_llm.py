from langchain_core.language_models import LanguageModelInput
from langchain_core.messages import AIMessage
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool

from personal_agent.config.settings import Settings
from personal_agent.llm.granite.chat_model import GraniteChatModel
from personal_agent.llm.huggingface_llm import LocalHuggingFaceChatModel
from personal_agent.llm.define_llm import ChatModelName, HuggingFaceParameters


class ChatModels:
    """등록된 모델을 생성하고 이름으로 조회한다."""

    def __init__(self, settings: Settings) -> None:
        self._summary_model_name = ChatModelName.GRANITE
        self._models = {}
        self._parameters = {}
        for name, build_model in {ChatModelName.GRANITE: GraniteChatModel.from_settings}.items():
            model, config = build_model(settings)
            self._models[name] = model
            self._parameters[name] = config.parameters

    def get(self, name: ChatModelName) -> LocalHuggingFaceChatModel:
        return self._models[name]

    def get_parameters(self, name: ChatModelName) -> HuggingFaceParameters:
        return self._parameters[name]

    def get_summary_model(self) -> tuple[Runnable[LanguageModelInput, AIMessage], HuggingFaceParameters]:
        parameters = self.get_parameters(self._summary_model_name)
        model = self.get_with_max_new_tokens(
            self._summary_model_name, parameters.summary_max_new_tokens
        )
        return model, parameters

    def get_with_max_new_tokens(
        self, name: ChatModelName, max_new_tokens: int
    ) -> Runnable[LanguageModelInput, AIMessage]:
        return self.get(name).with_max_new_tokens(max_new_tokens)

    def get_with_tools(self, name: ChatModelName, tools: list[BaseTool]) -> Runnable:
        return self.get(name).bind_tools(tools)
