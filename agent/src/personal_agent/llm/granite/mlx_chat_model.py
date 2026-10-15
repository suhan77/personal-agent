"""LangChain adapter for local Granite BF16 inference with MLX LM."""

from concurrent.futures import ThreadPoolExecutor
import logging
from pathlib import Path
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from mlx_lm import load, stream_generate
from mlx_lm.sample_utils import make_sampler
from pydantic import PrivateAttr

from personal_agent.config.settings import Settings
from personal_agent.llm.granite.llm_config import GraniteLLMConfig
from personal_agent.llm.granite.prompt import GranitePromptMixin
from personal_agent.llm.granite.tool_call_parser import parse_tool_calls


logger = logging.getLogger(__name__)


class MLXRunner:
    """Load and execute on one thread; bound model copies share this queue."""
    def __init__(self, path: Path):
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="granite-mlx")
        try:
            self.model, self.tokenizer = self.executor.submit(self._load, path).result()
        except Exception:
            self.executor.shutdown(wait=False)
            raise

    @staticmethod
    def _load(path):
        return load(str(path))


class GraniteMLXChatModel(GranitePromptMixin, BaseChatModel):
    model_id: str
    enable_thinking: bool = False
    max_tokens: int = 2048
    temperature: float = 1.0
    top_p: float = 0.95
    _runner: Any = PrivateAttr()
    _bound_tools: list[dict[str, object]] = PrivateAttr(default_factory=list)

    @property
    def tokenizer(self):
        return self._runner.tokenizer

    @property
    def _llm_type(self) -> str:
        return "granite-mlx"

    @property
    def _identifying_params(self):
        return {"model_id": self.model_id, "enable_thinking": self.enable_thinking}

    @classmethod
    def from_settings(cls, settings: Settings):
        config = GraniteLLMConfig()
        path = settings.model_dir / config.directory_name
        if not (path / "config.json").is_file() or not list(path.glob("*.safetensors")):
            raise FileNotFoundError(f"MLX 모델이 없습니다: {path}. README의 MLX 모델 준비 명령을 실행하세요.")
        model = cls(model_id=str(path), enable_thinking=config.enable_thinking,
                    max_tokens=config.parameters.max_new_tokens,
                    temperature=config.parameters.temperature, top_p=config.parameters.top_p)
        model._runner = MLXRunner(path)
        return model, config

    def with_max_new_tokens(self, max_new_tokens: int):
        return self.bind(max_tokens=max_new_tokens)

    def _generate(self, messages: list[BaseMessage], stop=None, run_manager=None, **kwargs) -> ChatResult:
        return self._runner.executor.submit(self._generate_serial, messages, stop, kwargs).result()

    def _generate_serial(self, messages, stop, kwargs):
        prompt = self._to_chat_prompt(messages)
        # The template already includes special tokens; avoid inserting another BOS.
        tokens = self.tokenizer.encode(prompt, add_special_tokens=False)
        sampler = make_sampler(temp=kwargs.get("temperature", self.temperature), top_p=kwargs.get("top_p", self.top_p))
        max_tokens = kwargs.get("max_tokens", self.max_tokens)
        if max_tokens <= 0:
            raise ValueError("max_tokens must be positive")
        pieces = []
        last = None
        finish = "stop"
        for response in stream_generate(self._runner.model, self.tokenizer, prompt=tokens,
                                        max_tokens=max_tokens, sampler=sampler):
            last = response
            pieces.append(response.text)
            if stop and any(marker in "".join(pieces) for marker in stop):
                break
        text = "".join(pieces)
        if stop:
            positions = [text.index(marker) for marker in stop if marker in text]
            if positions:
                text = text[:min(positions)]
        metadata = {}
        usage = None
        if last is not None:
            finish = getattr(last, "finish_reason", None) or "stop"
            metadata = {"finish_reason": finish, "prompt_tps": last.prompt_tps,
                        "generation_tps": last.generation_tps, "peak_memory_gb": last.peak_memory}
            usage = {"input_tokens": last.prompt_tokens, "output_tokens": last.generation_tokens,
                     "total_tokens": last.prompt_tokens + last.generation_tokens}
            logger.info("MLX 속도 | 입력 %.1f토큰/초 | 생성 %.1f토큰/초 | 메모리 %.2fGB",
                        last.prompt_tps, last.generation_tps, last.peak_memory)
        content, tool_calls = parse_tool_calls(text)
        if finish == "length" and "<tool_call>" in content:
            raise ValueError("도구 호출 생성이 출력 제한으로 중단됐습니다. 출력 제한을 늘려 주세요.")
        return ChatResult(generations=[ChatGeneration(message=AIMessage(
            content=content, tool_calls=tool_calls, response_metadata=metadata, usage_metadata=usage))])
