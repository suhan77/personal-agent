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
from personal_agent.schemas.reminder_update import ReminderUpdateRequest
from personal_agent.services.chat_service import AgentService
from personal_agent.services.review_service import ReviewService
from personal_agent.services.native_tool_bridge import NativeToolBridge, native_tool_context


class UpdatingModel(FakeListChatModel):
    _calls: int = PrivateAttr(default=0)

    def __init__(self):
        super().__init__(responses=[])

    async def ainvoke(self, messages, *args, **kwargs):
        self._calls += 1
        if self._calls == 1:
            return AIMessage(content="", tool_calls=[{
                "name": "find_reminders", "args": {"query": "발표"}, "id": "find-1"
            }])
        if self._calls == 2:
            return AIMessage(content="", tool_calls=[{
                "name": "propose_update_reminder", "args": {
                    "identifier": "reminder-id", "set": {"title": "새 제목"}, "clear": ["notes"]
                }, "id": "update-1"
            }])
        tool_result = next(message for message in reversed(messages) if isinstance(message, ToolMessage))
        return AIMessage(content=str(tool_result.content))


class UpdatingModels:
    def __init__(self):
        self.model = UpdatingModel()

    def get_with_tools(self, name, tools):
        return self.model

    def get_summary_model(self):
        from personal_agent.llm.granite.llm_config import GraniteLLMConfig
        return self.model, GraniteLLMConfig().parameters


class ReminderUpdateTests(unittest.IsolatedAsyncioTestCase):
    def test_patch_requires_explicit_changes(self):
        for payload in [
            {"identifier": "x"},
            {"identifier": "x", "set": {"title": None}},
            {"identifier": "x", "set": {"notes": "a"}, "clear": ["notes"]},
            {"identifier": "x", "clear": ["title"]},
            {"identifier": "x", "set": {"url": "file:///tmp/a"}},
        ]:
            with self.subTest(payload=payload), self.assertRaises(ValidationError):
                ReminderUpdateRequest.model_validate(payload)
        valid = ReminderUpdateRequest.model_validate({
            "identifier": "x", "set": {"title": "새 제목"}, "clear": ["notes"]
        })
        self.assertEqual(valid.set.model_dump(exclude_unset=True), {"title": "새 제목"})

    async def test_requires_search_evidence(self):
        state = {"messages": [AIMessage(content="", tool_calls=[{
            "name": "propose_update_reminder", "args": {"identifier": "invented", "set": {"title": "x"}}, "id": "call"
        }])]}
        with self.assertRaisesRegex(ValueError, "find_reminders"):
            await prepare_reminder_change(state)

    async def test_preview_rejection_and_stale_result_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            async with open_checkpointer(Path(directory) / "checkpoints.sqlite") as saver:
                service = AgentService(UpdatingModels(), saver)
                bridge = None
                events = []

                def emit(event):
                    events.append(event)
                    result = ({"items": [{"identifier": "reminder-id", "title": "발표 준비"}], "truncated": False}
                              if event["tool"] == "find_reminders" else {
                                  "identifier": "reminder-id", "title": "발표 준비", "due_date": "2026-09-29",
                                  "due_time": None, "list_name": "기본", "notes": "기존 메모", "url": None,
                                  "repeat": None, "priority": None, "is_completed": False, "revision": "revision-1"
                              })
                    asyncio.get_running_loop().call_soon(bridge.resolve, {
                        "id": event["id"], "call_id": event["call_id"], "result": result
                    })

                bridge = NativeToolBridge(emit)
                conversation_id = uuid4()
                with native_tool_context(bridge, "parent"):
                    proposal = await service.run(AgentRequest(message="발표 미리 알림 제목 수정해줘",
                                                              conversation_id=conversation_id))
                self.assertEqual(proposal["type"], "reminder_update_proposal")
                self.assertEqual([event["tool"] for event in events], ["find_reminders", "get_reminder"])
                details = proposal["reminder_update"]
                reviews = ReviewService(service.graph)
                self.assertEqual(details["before"]["title"], "발표 준비")
                self.assertEqual(details["after"]["title"], "새 제목")
                self.assertIsNone(details["after"]["notes"])
                with self.assertRaisesRegex(ValueError, "does not match"):
                    await reviews.resume_reminder_change(conversation_id, {"proposal_id": "wrong", "status": "rejected"})
                result = {"proposal_id": details["proposal_id"], "status": "rejected", "identifier": None, "error": None}
                response = await reviews.resume_reminder_change(conversation_id, result)
                self.assertIn("거부", response.answer)
                replay = await reviews.resume_reminder_change(conversation_id, result)
                self.assertEqual(replay.answer, response.answer)
