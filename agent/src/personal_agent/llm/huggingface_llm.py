import asyncio
from copy import deepcopy
from pathlib import Path

import torch
from langchain_core.language_models import LanguageModelInput
from langchain_core.messages import AIMessage
from langchain_core.runnables import Runnable, RunnableConfig
from langchain_huggingface import ChatHuggingFace, HuggingFacePipeline
from pydantic import PrivateAttr
from transformers import AutoModelForCausalLM, AutoTokenizer, GenerationConfig, pipeline

from personal_agent.common.log_messages import LogMessages
from personal_agent.common.timing import log_timed
from personal_agent.llm.define_llm import HuggingFaceParameters


class LocalHuggingFaceChatModel(ChatHuggingFace):
    """로컬 Hugging Face 모델의 비동기 호출과 생성 길이를 관리한다."""

    _invocation_lock: asyncio.Lock = PrivateAttr(default_factory=asyncio.Lock)

    async def ainvoke(
        self,
        input: LanguageModelInput,
        config: RunnableConfig | None = None,
        *,
        stop: list[str] | None = None,
        **kwargs: object,
    ) -> AIMessage:
        async with self._invocation_lock:
            return await asyncio.to_thread(self.invoke, input, config, stop=stop, **kwargs)

    def with_max_new_tokens(
        self, max_new_tokens: int
    ) -> Runnable[LanguageModelInput, AIMessage]:
        generation_config = deepcopy(self.llm.pipeline.generation_config)
        generation_config.max_length = None
        generation_config.max_new_tokens = max_new_tokens
        return self.bind(pipeline_kwargs={"generation_config": generation_config})


def load_local_pipeline(model_path: Path, parameters: HuggingFaceParameters):
    """로컬 가중치와 토크나이저로 Transformers 텍스트 생성 pipeline을 만든다.

    pipeline은 입력 토큰화, 모델 추론, 출력 문자열 변환을 묶고,
    HuggingFacePipeline은 이를 LangChain에서 호출할 수 있게 감싼다.
    """
    if not model_path.is_dir():
        raise FileNotFoundError(f"Local model directory not found: {model_path}")

    tokenizer = _load_tokenizer(model_path)
    transformer_model = _load_model(model_path, parameters)
    local_pipeline = _create_pipeline(model_path, parameters, transformer_model, tokenizer)
    return local_pipeline, tokenizer


@log_timed(LogMessages.TOKENIZER_LOADING)
def _load_tokenizer(model_path: Path):
    return AutoTokenizer.from_pretrained(model_path, local_files_only=True)


@log_timed(LogMessages.MODEL_LOADING)
def _load_model(model_path: Path, parameters: HuggingFaceParameters):
    model = AutoModelForCausalLM.from_pretrained(
        model_path,
        dtype=getattr(torch, parameters.dtype),
        device_map=parameters.device,
        local_files_only=True,
    )
    model.eval()
    return model


@log_timed(LogMessages.PIPELINE_INITIALIZATION)
def _create_pipeline(model_path: Path, parameters: HuggingFaceParameters, model, tokenizer):
    generation_config = GenerationConfig.from_pretrained(model_path, local_files_only=True)
    generation_config.max_length = None
    generation_config.max_new_tokens = parameters.max_new_tokens
    generation_config.do_sample = parameters.do_sample
    generation_config.temperature = parameters.temperature
    generation_config.top_p = parameters.top_p

    text_generation_pipeline = pipeline(
        task="text-generation",
        model=model,
        tokenizer=tokenizer,
        return_full_text=False,
        clean_up_tokenization_spaces=False,
        generation_config=generation_config,
    )
    text_generation_pipeline.generation_config.max_length = None
    return HuggingFacePipeline(
        pipeline=text_generation_pipeline,
        model_id=str(model_path),
    )
