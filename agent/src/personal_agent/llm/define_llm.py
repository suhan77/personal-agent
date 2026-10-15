from enum import Enum
from pydantic import BaseModel, Field


class ChatModelName(str, Enum):
    GRANITE = "granite"
    GPT6_LUNA = "gpt-6-luna"


    @classmethod
    def _missing_(cls, value):
        # Preserve checkpoints and requests created while MLX had a separate ID.
        if value == "granite-mlx":
            return cls.GRANITE
        return None


class ModelParameters(BaseModel):
    context_window: int = Field(gt=0)
    max_new_tokens: int = Field(gt=0)
    summary_max_new_tokens: int = Field(gt=0)


class LocalGenerationParameters(ModelParameters):
    temperature: float = Field(ge=0.0, le=2.0)
    top_p: float = Field(gt=0.0, le=1.0)
