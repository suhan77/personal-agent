"""기존 미리 알림 삭제 대상의 식별자만 받는다."""

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ReminderDeleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identifier: str = Field(min_length=1, description="find_reminders 결과의 정확한 identifier")

    @field_validator("identifier")
    @classmethod
    def nonblank_identifier(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("미리 알림 식별자가 비어 있습니다")
        return value.strip()
