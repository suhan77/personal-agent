import unittest
from datetime import datetime, timedelta, timezone

from pydantic import ValidationError
from langchain_core.utils.function_calling import convert_to_openai_tool

from personal_agent.schemas.reminder import ReminderProposal
from personal_agent.chain.prompts import build_prompt, build_system_prompt
from personal_agent.graph.nodes.workflow import select_workflow
from langchain_core.messages import HumanMessage
from personal_agent.tools.reminder import propose_reminder
from personal_agent.tools.filesystem import update_file
from personal_agent.tools.web_search import create_web_search_tool


class ReminderProposalTests(unittest.TestCase):
    def test_common_prompt_and_local_time_are_independent_of_tool_names(self):
        now = datetime(2026, 9, 28, 14, 30, tzinfo=timezone(timedelta(hours=9)))
        prompt = build_system_prompt(now)
        self.assertIn("필요한 정보가 없거나 모호하면 확인합니다", prompt)
        self.assertIn("2026-09-28T14:30+09:00", prompt)
        self.assertIn("승인·저장 결과를 받기 전", prompt)
        self.assertNotIn("미리 알림 등록에는", prompt)
        for tool_name in ("propose_reminder", "web_search", "update_file"):
            self.assertNotIn(tool_name, prompt)

        reminder_prompt = build_prompt("reminder", now)
        self.assertIn("등록에만 제목과 날짜가 필수", reminder_prompt)
        self.assertIn("빠진 필수 항목만 묻는다", reminder_prompt)
        self.assertIn("propose_reminder", reminder_prompt)
        self.assertEqual(build_prompt(None, now), prompt)
        with self.assertRaisesRegex(ValueError, "Unknown workflow"):
            build_prompt("unknown", now)

    def test_reminder_workflow_selection_and_follow_up(self):
        first = select_workflow({"messages": [HumanMessage(content="미리 알림 등록해줘")]})
        self.assertEqual(first, {"active_workflow": "reminder"})
        follow_up = select_workflow({"messages": [HumanMessage(content="내일 오후 3시")], "active_workflow": "reminder"})
        self.assertEqual(follow_up, {})
        cancelled = select_workflow({"messages": [HumanMessage(content="취소해줘")], "active_workflow": "reminder"})
        self.assertEqual(cancelled, {"active_workflow": None})
        unrelated = select_workflow({"messages": [HumanMessage(content="리마인더는 뭐야?")]})
        self.assertEqual(unrelated, {})
        explanation = select_workflow({"messages": [HumanMessage(content="미리 알림 설정 방법 알려줘")]})
        self.assertEqual(explanation, {})

    def test_tool_descriptions_carry_usage_rules(self):
        reminder_tool = convert_to_openai_tool(propose_reminder)["function"]
        self.assertIn("제목과 날짜가 확정된", reminder_tool["description"])
        self.assertIn("저장하지 않는다", reminder_tool["description"])
        reminder_fields = reminder_tool["parameters"]["properties"]
        self.assertIn("title", reminder_tool["parameters"]["required"])
        self.assertIn("due_date", reminder_tool["parameters"]["required"])
        self.assertIn("선택", reminder_fields["due_time"]["description"])
        self.assertIn("선택", reminder_fields["repeat"]["description"])
        self.assertIn("read_file", update_file.description)
        self.assertIn("URL", create_web_search_tool().description)

    def test_requires_title_and_date(self):
        with self.assertRaises(ValidationError):
            ReminderProposal.model_validate({"title": "발표 준비"})
        with self.assertRaises(ValidationError):
            ReminderProposal.model_validate({"title": " ", "due_date": "2026-09-29"})

    def test_date_without_time_is_all_day(self):
        result = propose_reminder.invoke({"title": "발표 준비", "due_date": "2026-09-29"})
        self.assertEqual(result["due_date"], "2026-09-29")
        self.assertIsNone(result["due_time"])
        self.assertIsNone(result["list_name"])

    def test_optional_fields_are_preserved(self):
        result = propose_reminder.invoke({
            "title": "발표 준비",
            "due_date": "2026-09-29",
            "due_time": "15:00",
            "notes": "자료 확인",
            "url": "https://example.com",
            "list_name": "스터디",
            "repeat": "weekly",
            "priority": "high",
        })
        self.assertEqual(result["due_time"], "15:00:00")
        self.assertEqual(result["repeat"], "weekly")
        self.assertEqual(result["priority"], "high")

    def test_rejects_unsupported_and_unknown_options(self):
        with self.assertRaisesRegex(ValueError, "자동 등록할 수 없는 옵션"):
            propose_reminder.invoke({
                "title": "발표 준비",
                "due_date": "2026-09-29",
                "unsupported_options": ["긴급"],
            })
        with self.assertRaises(ValidationError):
            ReminderProposal.model_validate({
                "title": "발표 준비", "due_date": "2026-09-29", "urgent": True,
            })

    def test_rejects_invalid_url(self):
        with self.assertRaises(ValidationError):
            ReminderProposal.model_validate({
                "title": "발표 준비", "due_date": "2026-09-29", "url": "file:///tmp/note",
            })
