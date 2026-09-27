import asyncio
import json
from pathlib import Path
from queue import Queue
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import PrivateAttr, ValidationError

from personal_agent.__main__ import serve
from personal_agent.graph.checkpoint import open_checkpointer
from personal_agent.schemas.agent import AgentRequest
from personal_agent.services.chat_service import AgentService
from personal_agent.services.native_tool_bridge import NativeToolBridge, call_native_tool, native_tool_context
from personal_agent.tools.reminder_search import ReminderSearchInput, find_reminders


class ReminderSearchModel(FakeListChatModel):
    _calls: int = PrivateAttr(default=0)

    def __init__(self):
        super().__init__(responses=[])

    async def ainvoke(self, messages, *args, **kwargs):
        self._calls += 1
        if self._calls == 1:
            return AIMessage(content="", tool_calls=[{
                "name": "find_reminders", "args": {"query": "발표"}, "id": "search_reminders_1"
            }])
        result = next(item for item in reversed(messages) if isinstance(item, ToolMessage))
        if "접근 권한" in str(result.content):
            return AIMessage(content="미리 알림 접근 권한이 없어 검색하지 못했습니다.")
        if "reminder-id" not in str(result.content):
            raise AssertionError("Swift search result did not reach the model")
        return AIMessage(content="발표 준비 미리 알림을 찾았습니다.")


class ReminderSearchModels:
    def __init__(self):
        self.model = ReminderSearchModel()

    def get_with_tools(self, name, tools):
        return self.model

    def get_summary_model(self):
        from personal_agent.llm.granite.llm_config import GraniteLLMConfig
        return self.model, GraniteLLMConfig().parameters


class QueueInput:
    def __init__(self):
        self.lines = Queue()

    def readline(self):
        return self.lines.get()


class ReplyingOutput:
    def __init__(self, input_stream):
        self.input = input_stream
        self.events = []

    def write(self, line):
        event = json.loads(line)
        self.events.append(event)
        if event["type"] == "native_tool_request":
            self.input.lines.put(json.dumps({
                "id": event["id"], "type": "native_tool_result", "call_id": event["call_id"],
                "result": {"items": [{"identifier": "reminder-id", "title": "발표 준비"}], "truncated": False},
            }) + "\n")
        elif event["type"] == "assistant_reply":
            self.input.lines.put("")

    def flush(self):
        pass


class ReminderSearchTests(unittest.IsolatedAsyncioTestCase):
    async def test_permission_error_is_returned_to_model(self):
        with tempfile.TemporaryDirectory() as directory:
            async with open_checkpointer(Path(directory) / "checkpoint.sqlite") as saver:
                service = AgentService(ReminderSearchModels(), saver)
                bridge = None

                def emit(event):
                    asyncio.get_running_loop().call_soon(bridge.resolve, {
                        "id": event["id"], "call_id": event["call_id"],
                        "error": "미리 알림 접근 권한이 없습니다",
                    })

                bridge = NativeToolBridge(emit)
                with native_tool_context(bridge, "parent-request"):
                    response = await service.run(AgentRequest(message="발표 알림 찾아줘"))
                self.assertIn("권한이 없어", response.answer)

    async def test_tool_schema_exposes_bounded_read_only_search(self):
        schema = convert_to_openai_tool(find_reminders)["function"]
        self.assertIn("수정·삭제 대상을 찾을 때", schema["description"])
        self.assertIn("query", schema["parameters"]["required"])
        self.assertNotIn("due_date", schema["parameters"]["required"])

    async def test_search_tool_returns_native_results_to_model(self):
        with tempfile.TemporaryDirectory() as directory:
            async with open_checkpointer(Path(directory) / "checkpoint.sqlite") as saver:
                service = AgentService(ReminderSearchModels(), saver)
                events = []
                bridge = None

                def emit(event):
                    events.append(event)
                    asyncio.get_running_loop().call_soon(bridge.resolve, {
                        "id": event["id"], "call_id": event["call_id"],
                        "result": {"items": [{"identifier": "reminder-id", "title": "발표 준비"}], "truncated": False},
                    })

                bridge = NativeToolBridge(emit)
                with native_tool_context(bridge, "parent-request"):
                    response = await service.run(AgentRequest(message="발표 준비 알림 찾아줘"))
                self.assertIn("찾았습니다", response.answer)
                self.assertEqual(events[0]["tool"], "find_reminders")
                self.assertEqual(events[0]["arguments"]["query"], "발표")

    async def test_json_lines_accepts_tool_response_while_request_is_running(self):
        class FakeRuntime:
            async def handle(self, payload, request_id):
                result = await call_native_tool("find_reminders", {"query": "발표"})
                return {"id": request_id, "type": "assistant_reply", "answer": result["items"][0]["title"]}

            async def close(self):
                pass

        input_stream = QueueInput()
        output_stream = ReplyingOutput(input_stream)
        input_stream.lines.put('{"id":"request-1","type":"generate_reply"}\n')
        with patch("personal_agent.__main__.AgentRuntime.create", new=AsyncMock(return_value=FakeRuntime())):
            await asyncio.wait_for(serve(input_stream, output_stream), timeout=5)
        self.assertEqual([event["type"] for event in output_stream.events],
                         ["native_tool_request", "assistant_reply"])
        self.assertEqual(output_stream.events[-1]["answer"], "발표 준비")

    async def test_rejects_blank_search_and_mismatched_tool_result(self):
        with self.assertRaises(ValidationError):
            ReminderSearchInput.model_validate({"query": "   "})
        bridge = None
        events = []

        def emit(event):
            events.append(event)
            bridge.resolve({"id": "wrong-parent", "call_id": event["call_id"], "result": {"items": [], "truncated": False}})
            asyncio.get_running_loop().call_soon(bridge.resolve, {
                "id": event["id"], "call_id": event["call_id"],
                "result": {"items": [], "truncated": False}
            })

        bridge = NativeToolBridge(emit)
        with native_tool_context(bridge, "parent"):
            self.assertEqual(await find_reminders.ainvoke({"query": "발표"}), {"items": [], "truncated": False})
        self.assertEqual(len(events), 1)

    async def test_native_search_permission_error_is_not_treated_as_empty_results(self):
        bridge = None

        def emit(event):
            asyncio.get_running_loop().call_soon(bridge.resolve, {
                "id": event["id"], "call_id": event["call_id"],
                "error": "미리 알림 접근 권한이 없습니다",
            })

        bridge = NativeToolBridge(emit)
        with native_tool_context(bridge, "parent"):
            with self.assertRaisesRegex(RuntimeError, "접근 권한"):
                await find_reminders.ainvoke({"query": "발표"})
