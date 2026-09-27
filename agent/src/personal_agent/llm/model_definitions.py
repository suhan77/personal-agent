from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class ChatModelName(str, Enum):
    GRANITE = "granite"


class HuggingFaceParameters(BaseModel):
    """
    로컬 Hugging Face 모델의 로딩 및 생성 파라미터입니다.
    """

    temperature: float = Field(ge=0.0, le=2.0)
    top_p: float = Field(gt=0.0, le=1.0)
    context_window: int = Field(gt=0)
    max_new_tokens: int = Field(gt=0)
    summary_max_new_tokens: int = Field(gt=0)
    do_sample: bool = True
    enable_thinking: bool = False
    dtype: Literal["bfloat16"] = "bfloat16"
    device: Literal["mps"] = "mps"


class GraniteModelDefinition(BaseModel):
    key: Literal[ChatModelName.GRANITE] = ChatModelName.GRANITE
    directory_name: Literal["granite-4.2-3b"] = "granite-4.2-3b"
    parameters: HuggingFaceParameters = HuggingFaceParameters(
        temperature=1.0,
        top_p=0.95,
        context_window=16_384,
        max_new_tokens=2_048,
        summary_max_new_tokens=256,
    )


ModelDefinition = GraniteModelDefinition

MODEL_DEFINITIONS: dict[ChatModelName, ModelDefinition] = {
    ChatModelName.GRANITE: GraniteModelDefinition(),
}


def get_model_definition(model: ChatModelName) -> ModelDefinition:
    return MODEL_DEFINITIONS[model]
