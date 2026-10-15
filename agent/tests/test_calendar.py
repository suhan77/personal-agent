import unittest
from unittest.mock import AsyncMock, patch
from pydantic import ValidationError
from personal_agent.tools.calendar import EventSearch, EventCreate, EventUpdate, find_calendar_events, create_calendar_event, update_calendar_event

START = "2026-10-16T09:00:00+09:00"
END = "2026-10-16T10:00:00+09:00"


class CalendarTests(unittest.IsolatedAsyncioTestCase):
    def test_invalid_ranges(self):
        for start, end in [(END, START), (START, START), ("2026-10-16T09:00:00", END)]:
            with self.assertRaises(ValidationError):
                EventSearch(start=start, end=end)
        with self.assertRaises(ValidationError):
            EventCreate(start=START, end=END, title=" ")

    def test_create_schema_has_event_times_without_search_query(self):
        schema = EventCreate.model_json_schema()
        self.assertNotIn("query", schema["properties"])
        self.assertNotIn("조회", schema["properties"]["end"]["description"])
        self.assertEqual(set(schema["required"]), {"title", "start", "end"})

    def test_updates_require_changes(self):
        for fields in ({}, {"title": None}, {"title": " "}, {"start": END, "end": START}):
            with self.assertRaises(ValidationError):
                EventUpdate(identifier="id", revision="version", **fields)

    async def test_bridge_preserves_partial_update(self):
        with patch("personal_agent.tools.calendar.call_native_tool", new_callable=AsyncMock) as native:
            native.return_value = {"status": "rejected", "items": [], "truncated": False}
            result = await update_calendar_event.ainvoke({"identifier": "id", "revision": "version", "location": ""})
            self.assertEqual(result["status"], "rejected")
            self.assertEqual(native.call_args.args, ("update_calendar_event", {"identifier": "id", "revision": "version", "location": ""}))

    async def test_search_and_create(self):
        with patch("personal_agent.tools.calendar.call_native_tool", new_callable=AsyncMock) as native:
            native.return_value = {"items": [], "truncated": False}
            await find_calendar_events.ainvoke({"start": START, "end": END})
            self.assertEqual(native.call_args.args[0], "find_calendar_events")
            await create_calendar_event.ainvoke({"start": START, "end": END, "title": "회의"})
            self.assertEqual(native.call_args.args[0], "create_calendar_event")
