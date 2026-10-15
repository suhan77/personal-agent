import unittest
from unittest.mock import AsyncMock
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from personal_agent.graph.nodes.generation import GenerationNode
from personal_agent.graph.nodes.workflow import select_workflow
from personal_agent.chain.prompts import build_prompt
from personal_agent.tools.calendar import find_calendar_events, create_calendar_event, update_calendar_event
from personal_agent.tools.macos_shortcuts import get_macos_shortcuts


class Models:
    def __init__(self, responses):
        self.model = AsyncMock()
        self.model.ainvoke.side_effect = responses
        self.tools = []

    def get_with_tools(self, name, tools):
        self.tools = tools
        return self.model


class CalendarWorkflowTests(unittest.IsolatedAsyncioTestCase):
    def test_calendar_request_and_followup(self):
        self.assertEqual(select_workflow({"messages": [HumanMessage(content='오늘 오후 6시에 "러닝크루" 일정 추가해줘')]}), {"active_workflow": "calendar"})
        self.assertEqual(select_workflow({"messages": [HumanMessage(content="7시까지")], "active_workflow": "calendar"}), {})
        self.assertEqual(select_workflow({"messages": [HumanMessage(content="취소")], "active_workflow": "calendar"}), {"active_workflow": None})
        self.assertEqual(select_workflow({"messages": [HumanMessage(content="파이썬 설명해줘")], "active_workflow": "calendar"}), {"active_workflow": None})
        self.assertIn("완결된 시간 범위", build_prompt("calendar"))

    async def generate(self, responses, history=None):
        models = Models(responses)
        node = GenerationNode(models, [find_calendar_events, create_calendar_event, update_calendar_event, get_macos_shortcuts])
        result = await node.run({"model": "granite", "active_workflow": "calendar", "messages": history or [HumanMessage(content='오늘 오후 6시에 러닝크루 일정 추가해줘')]})
        self.assertEqual([t.name for t in models.tools], ["find_calendar_events", "create_calendar_event", "update_calendar_event"])
        return result["messages"][0], models

    async def test_logged_response_retries_with_question(self):
        result, models = await self.generate([AIMessage(content="1시간으로 간주합니다. 이제 일정을 생성합니다."), AIMessage(content="몇 시까지 진행할까요?")])
        self.assertEqual(result.content, "몇 시까지 진행할까요?")
        self.assertEqual(models.model.ainvoke.call_count, 2)

    async def test_real_call_is_preserved(self):
        call = AIMessage(content="", tool_calls=[{"name": "create_calendar_event", "args": {"title": "러닝크루", "start": "2026-10-15T18:00:00+09:00", "end": "2026-10-15T19:00:00+09:00"}, "id": "call1"}])
        result, models = await self.generate([call])
        self.assertEqual(result.tool_calls, call.tool_calls)
        self.assertEqual(models.model.ainvoke.call_count, 1)

    async def test_repeated_false_claim_falls_back(self):
        result, models = await self.generate([AIMessage(content="추가하겠습니다"), AIMessage(content="생성했습니다")])
        self.assertIn("변경하지 못했습니다", result.content)
        self.assertEqual(models.model.ainvoke.call_count, 2)

    async def test_success_after_tool_result_is_not_retried(self):
        history = [HumanMessage(content="7시까지"), AIMessage(content="", tool_calls=[{"name": "create_calendar_event", "args": {}, "id": "call1"}]), ToolMessage(content='{"status":"saved"}', tool_call_id="call1")]
        result, models = await self.generate([AIMessage(content="일정을 생성했습니다")], history)
        self.assertEqual(models.model.ainvoke.call_count, 1)
