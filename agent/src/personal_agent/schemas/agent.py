from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from personal_agent.llm.model_definitions import ChatModelName


class AgentRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20_000)
    conversation_id: UUID | None = None
    model: ChatModelName = ChatModelName.GRANITE
    working_directory: str | None = None

    @field_validator("message")
    @classmethod
    def message_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Message cannot be blank")
        return value


class AgentResponse(BaseModel):
    answer: str
    conversation_id: UUID
    model: ChatModelName
