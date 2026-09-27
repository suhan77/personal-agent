"""Application runtime for the long-lived local agent worker."""

import asyncio
from contextlib import AsyncExitStack
import logging
from uuid import UUID

from personal_agent.llm.registry_llm import ChatModels
from personal_agent.common.logging import configure_logging
from personal_agent.common.log_messages import LogMessages
from personal_agent.common.timing import log_duration, log_timed
from personal_agent.config.settings import Settings, get_settings
from personal_agent.graph.checkpoint import delete_conversation, open_checkpointer
from personal_agent.schemas.agent import AgentRequest
from personal_agent.services.chat_service import AgentService
from personal_agent.services.review_service import ReviewService


class AgentRuntime:
    def __init__(self, stack: AsyncExitStack, service: AgentService, reviews: ReviewService, saver) -> None:
        self._stack = stack
        self._service = service
        self._reviews = reviews
        self._saver = saver

    @classmethod
    async def create(cls) -> "AgentRuntime":
        """장기 실행에 필요한 모델과 저장소를 준비해 에이전트 런타임을 생성한다.

        앱 시작 시 다음 초기화 작업을 수행한다.

        1. 환경 설정을 읽고 로그 레벨을 적용한다.
        2. Python 모델과 생성 파이프라인을 미리 메모리에 적재한다.
        3. SQLite 체크포인터를 열어 대화 이력을 복원하거나 저장할 수 있게 한다.
        4. 하나의 그래프를 공유하는 `AgentService`와 `ReviewService`를 구성한다.

        반환된 런타임은 Python 워커가 살아 있는 동안 재사용해야 하며,
        사용이 끝나면 `close()`를 호출해 체크포인터 연결을 닫아야 한다.
        """
        settings = get_settings()
        configure_logging(settings.log_level)
        models = await cls._load_models(settings)
        stack = AsyncExitStack()
        await stack.__aenter__()
        saver, service, reviews = await cls._initialize_graph(stack, models, settings)
        return cls(stack, service, reviews, saver)

    @staticmethod
    @log_timed(LogMessages.MODEL_INITIALIZATION)
    async def _load_models(settings: Settings) -> ChatModels:
        return await asyncio.to_thread(ChatModels, settings)

    @staticmethod
    @log_timed(LogMessages.GRAPH_INITIALIZATION)
    async def _initialize_graph(
        stack: AsyncExitStack, models: ChatModels, settings: Settings
    ):
        saver = await stack.enter_async_context(
            open_checkpointer(settings.agent_data_dir / "checkpoints.sqlite")
        )
        service = AgentService(models, saver)
        return saver, service, ReviewService(service.graph)

    @log_duration(LogMessages.REQUEST_PROCESSING)
    async def handle(self, payload: dict, request_id: str) -> dict:
        # 대화와 LangGraph 체크포인트를 함께 삭제한다.
        if payload.get("type") == "delete_conversation":
            conversation_id = payload.get("conversation_id")
            await delete_conversation(self._saver, conversation_id)
            return {"id": request_id, "type": "conversation_deleted"}

        # 모델을 호출하고 대화 이력을 반영해 답변을 생성한다.
        elif payload.get("type") == "generate_reply":
            request = AgentRequest.model_validate(payload)
            logging.info(LogMessages.REQUEST_STARTED, request_id, request.model.value, len(request.message))
            result = await self._service.run(request)
            response = {"id": request_id, "type": "assistant_reply", **result.model_dump(mode="json")} if not isinstance(result, dict) else {"id": request_id, **result}
            logging.info(LogMessages.REQUEST_COMPLETED, request_id, response["type"])
            return response

        elif payload.get("type") == "review_file_change":
            conversation_id = UUID(payload["conversation_id"])
            result = await self._reviews.resume_file_change(conversation_id, payload["decision"])
            return {"id": request_id, "type": "assistant_reply", **result.model_dump(mode="json")} if not isinstance(result, dict) else {"id": request_id, **result}

        elif payload.get("type") == "review_reminder":
            conversation_id = UUID(payload["conversation_id"])
            result = await self._reviews.resume_reminder_creation(conversation_id, payload["result"])
            return {"id": request_id, "type": "assistant_reply", **result.model_dump(mode="json")} if not isinstance(result, dict) else {"id": request_id, **result}

        elif payload.get("type") == "review_reminder_update":
            conversation_id = UUID(payload["conversation_id"])
            result = await self._reviews.resume_reminder_change(conversation_id, payload["result"])
            return {"id": request_id, "type": "assistant_reply", **result.model_dump(mode="json")} if not isinstance(result, dict) else {"id": request_id, **result}

        # 등록되지 않은 JSON 명령은 처리하지 않는다.
        else:
            raise ValueError("Unsupported request type")

    async def close(self) -> None:
        await self._stack.aclose()
