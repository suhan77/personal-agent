from typing import Literal

from pydantic import BaseModel

from personal_agent.llm.define_llm import ChatModelName, HuggingFaceParameters


class GraniteLLMConfig(BaseModel):
    key: Literal[ChatModelName.GRANITE] = ChatModelName.GRANITE
    directory_name: Literal["granite-4.2-3b"] = "granite-4.2-3b"
    enable_thinking: bool = False
    parameters: HuggingFaceParameters = HuggingFaceParameters(
        temperature=1.0,
        top_p=0.95,
        context_window=16_384,
        max_new_tokens=2_048,
        summary_max_new_tokens=256,
    )
