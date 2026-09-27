from personal_agent.common.timing import log_timing
from personal_agent.common.log_messages import LogMessages
import asyncio
from copy import deepcopy

import torch
from langchain_core.language_models import LanguageModelInput
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult, LLMResult
from langchain_core.tools import BaseTool
from langchain_core.runnables import Runnable, RunnableConfig
from langchain_core.utils.function_calling import convert_to_openai_tool
from langchain_huggingface import ChatHuggingFace, HuggingFacePipeline
from pydantic import PrivateAttr
from transformers import AutoModelForCausalLM, AutoTokenizer, GenerationConfig, pipeline

from personal_agent.config.settings import Settings
from personal_agent.llm.model_definitions import ChatModelName, get_model_definition
from personal_agent.llm.tool_call_parser import parse_tool_calls


class LocalHuggingFaceChatModel(ChatHuggingFace):
    """로컬 Transformers 모델을 LangChain/LangGraph에서 호출하는 adapter.

    모델 경로와 생성 설정은 ``llm/model_definitions.py``에서 관리하고,
    이 클래스는 메시지 변환과 비동기 모델 호출을 담당한다.
    """

    enable_thinking: bool = False
    _invocation_lock: asyncio.Lock = PrivateAttr(default_factory=asyncio.Lock)
    _bound_tools: list[dict[str, object]] = PrivateAttr(default_factory=list)

    def _to_chat_prompt(self, messages: list[BaseMessage]) -> str:
        """LLM 실행 직전에 Granite 입력 prompt를 만든다.

        LangChain 메시지를 Granite 역할 형식으로 변환하고, 연결된 tool 정의를
        추가한 뒤 tokenizer chat template이 만든 문자열을 반환한다.
        """
        if not messages:
            raise ValueError("At least one message is required.")

        message_dicts = [self._to_chatml_format(message) for message in messages]
        return self.tokenizer.apply_chat_template(
            message_dicts,
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=self.enable_thinking,
            tools=self._bound_tools or None,
        )

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

    def bind_tools(
        self,
        tools: list[BaseTool],
        **kwargs: object,
    ) -> "LocalHuggingFaceChatModel":
        """모델 프롬프트에 사용할 tool 정의를 연결한다."""
        bound_model = self.model_copy()
        bound_model._bound_tools = [convert_to_openai_tool(tool) for tool in tools]
        return bound_model

    @staticmethod
    def _to_chat_result(llm_result: LLMResult) -> ChatResult:
        chat_generations = []
        for generation in llm_result.generations[0]:
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

    async def ainvoke(
        self,
        input: LanguageModelInput,
        config: RunnableConfig | None = None,
        *,
        stop: list[str] | None = None,
        **kwargs: object,
    ) -> AIMessage:
        async with self._invocation_lock:
            return await asyncio.to_thread(
                self.invoke,
                input,
                config,
                stop=stop,
                **kwargs,
            )

    def with_max_new_tokens(
        self,
        max_new_tokens: int,
    ) -> Runnable[LanguageModelInput, AIMessage]:
        generation_config = deepcopy(self.llm.pipeline.generation_config)
        generation_config.max_length = None
        generation_config.max_new_tokens = max_new_tokens
        return self.bind(
            pipeline_kwargs={"generation_config": generation_config}
        )


class ChatModels:
    """등록된 채팅 모델을 생성하고 이름으로 조회하는 모델 레지스트리.

    각 모델의 실제 실행은 ``LocalHuggingFaceChatModel``이 담당하고,
    이 클래스는 모델 정의를 읽어 생성한 인스턴스를 보관·제공한다.
    """

    def __init__(self, settings: Settings) -> None:
        self._models = {
            name: self._build(settings, name)
            for name in ChatModelName
        }

    def get(self, name: ChatModelName) -> BaseChatModel:
        return self._models[name]

    def get_with_max_new_tokens(
        self,
        name: ChatModelName,
        max_new_tokens: int,
    ) -> Runnable[LanguageModelInput, AIMessage]:
        model = self._models[name]
        if not isinstance(model, LocalHuggingFaceChatModel):
            raise TypeError(f"Unsupported local model type: {type(model).__name__}")
        return model.with_max_new_tokens(max_new_tokens)

    def get_with_tools(self, name: ChatModelName, tools: list[BaseTool]) -> BaseChatModel:
        return self._models[name].bind_tools(tools)

    @staticmethod
    def _build(settings: Settings, name: ChatModelName) -> BaseChatModel:
        definition = get_model_definition(name)
        parameters = definition.parameters
        model_path = settings.model_dir / definition.directory_name
        if not model_path.is_dir():
            raise FileNotFoundError(f"Local model directory not found: {model_path}")

        with log_timing(LogMessages.TOKENIZER_LOADING):
            tokenizer = AutoTokenizer.from_pretrained(
                model_path,
                local_files_only=True,
            )
        with log_timing(LogMessages.MODEL_LOADING):
            transformer_model = AutoModelForCausalLM.from_pretrained(
                model_path,
                dtype=getattr(torch, parameters.dtype),
                device_map=parameters.device,
                local_files_only=True,
            )
            transformer_model.eval()

        with log_timing(LogMessages.PIPELINE_INITIALIZATION):
            generation_config = GenerationConfig.from_pretrained(
                model_path,
                local_files_only=True,
            )
            generation_config.max_length = None
            generation_config.max_new_tokens = parameters.max_new_tokens
            generation_config.do_sample = parameters.do_sample
            generation_config.temperature = parameters.temperature
            generation_config.top_p = parameters.top_p

            text_generation_pipeline = pipeline(
                task="text-generation",
                model=transformer_model,
                tokenizer=tokenizer,
                return_full_text=False,
                clean_up_tokenization_spaces=False,
                generation_config=generation_config,
            )
            text_generation_pipeline.generation_config.max_length = None
            local_pipeline = HuggingFacePipeline(
                pipeline=text_generation_pipeline,
                model_id=str(model_path),
            )
        return LocalHuggingFaceChatModel(
            llm=local_pipeline,
            tokenizer=tokenizer,
            model_id=str(model_path),
            enable_thinking=parameters.enable_thinking,
        )
