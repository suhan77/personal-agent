import asyncio
from pathlib import Path
import tempfile
import unittest
from uuid import uuid4

from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage, ToolMessage
from pydantic import PrivateAttr, ValidationError

from personal_agent.graph.checkpoint import open_checkpointer
from personal_agent.graph.nodes.reminder_change_review import prepare_reminder_change
from personal_agent.schemas.agent import AgentRequest
from personal_agent.schemas.reminder_delete import ReminderDeleteRequest
from personal_agent.services.chat_service import AgentService
from personal_agent.services.review_service import ReviewService
from personal_agent.services.native_tool_bridge import NativeToolBridge, native_tool_context
from personal_agent.tools.reminder_delete import propose_delete_reminder


class DeletingModel(FakeListChatModel):
    _calls: int = PrivateAttr(default=0)

    def __init__(self):
        super().__init__(responses=[])

    async def ainvoke(self, messages, *args, **kwargs):
        self._calls += 1
        if self._calls == 1:
            return AIMessage(content="", tool_calls=[{
                "name": "find_reminders", "args": {"query": "발표"}, "id": "find-delete-1"
            }])
        if self._calls == 2:
            return AIMessage(content="", tool_calls=[{
                "name": "propose_delete_reminder", "args": {"identifier": "reminder-id"}, "id": "delete-1"
            }])
        result = next(message for message in reversed(messages) if isinstance(message, ToolMessage))
        return AIMessage(content=str(result.content))


class DeletingModels:
    def __init__(self):
        self.model = DeletingModel()

    def get_with_tools(self, name, tools):
        return self.model

    def get_summary_model(self):
        from personal_agent.llm.granite.llm_config import GraniteLLMConfig
        return self.model, GraniteLLMConfig().parameters


class ReminderDeleteTests(unittest.IsolatedAsyncioTestCase):
    def test_delete_tool_only_accepts_known_identifier(self):
        self.assertEqual(propose_delete_reminder.invoke({"identifier": " id "}), {"identifier": "id"})
        with self.assertRaises(ValidationError):
            ReminderDeleteRequest.model_validate({"identifier": "  "})
        with self.assertRaises(ValidationError):
            ReminderDeleteRequest.model_validate({"identifier": "id", "title": "ignored"})

    async def test_search_is_required_before_delete_proposal(self):
        state = {"messages": [AIMessage(content="", tool_calls=[{
            "name": "propose_delete_reminder", "args": {"identifier": "invented"}, "id": "delete"
        }])]}
        with self.assertRaisesRegex(ValueError, "find_reminders"):
            await prepare_reminder_change(state)

    async def test_preview_approval_and_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            async with open_checkpointer(Path(directory) / "checkpoints.sqlite") as saver:
                models = DeletingModels()
                service = AgentService(models, saver)
                bridge = None
                events = []

                def emit(event):
                    events.append(event)
                    result = ({"items": [{"identifier": "reminder-id", "title": "발표 준비"}], "truncated": False}
                              if event["tool"] == "find_reminders" else {
                                  "identifier": "reminder-id", "title": "발표 준비", "due_date": "2026-09-29",
                                  "due_time": None, "list_name": "기본", "notes": "중요", "url": None,
                                  "repeat": None, "priority": None, "is_completed": False, "revision": "rev-delete"
                              })
                    asyncio.get_running_loop().call_soon(bridge.resolve, {
                        "id": event["id"], "call_id": event["call_id"], "result": result
                    })

                bridge = NativeToolBridge(emit)
                conversation_id = uuid4()
                with native_tool_context(bridge, "delete-request"):
                    proposal = await service.run(AgentRequest(message="발표 미리 알림 삭제해줘", conversation_id=conversation_id))
                self.assertEqual([event["tool"] for event in events], ["find_reminders", "get_reminder"])
                self.assertEqual(proposal["type"], "reminder_update_proposal")
                details = proposal["reminder_update"]
                service = AgentService(models, saver)  # 앱 재시작 후 체크포인트에서 승인 대기를 복원
                reviews = ReviewService(service.graph)
                self.assertEqual(details["operation"], "delete")
                self.assertEqual(details["before"]["title"], "발표 준비")
                self.assertEqual(details["revision"], "rev-delete")
                self.assertEqual(details["set"], {})
                with self.assertRaisesRegex(ValueError, "Invalid reminder change status"):
                    await reviews.resume_reminder_change(conversation_id, {
                        "proposal_id": details["proposal_id"], "status": "saved", "identifier": "reminder-id"
                    })
                with self.assertRaisesRegex(ValueError, "identifier"):
                    await reviews.resume_reminder_change(conversation_id, {
                        "proposal_id": details["proposal_id"], "status": "deleted", "identifier": "wrong"
                    })
                result = {"proposal_id": details["proposal_id"], "status": "deleted",
                          "identifier": "reminder-id", "error": None}
                response = await reviews.resume_reminder_change(conversation_id, result)
                self.assertIn("삭제에 성공", response.answer)
                replay = await reviews.resume_reminder_change(conversation_id, result)
                self.assertEqual(replay.answer, response.answer)
