import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import Generation, LLMResult
from langchain_community.utilities.duckduckgo_search import DuckDuckGoSearchAPIWrapper
from pydantic import PrivateAttr
from personal_agent.__main__ import serve
from personal_agent.services.chat_service import AgentService
from personal_agent.services.review_service import ReviewService
from personal_agent.config.settings import Settings
from personal_agent.graph.checkpoint import open_checkpointer
from personal_agent.llm.granite.chat_model import GraniteChatModel
from personal_agent.llm.granite.tool_call_parser import parse_tool_calls
from personal_agent.llm.granite.llm_config import GraniteLLMConfig
from personal_agent.schemas.agent import AgentRequest
from personal_agent.tools.filesystem import create_file


class FakeModels:
    def __init__(self, *args):
        self.model = FakeListChatModel(responses=["테스트 응답"])

    def get(self, name):
        return self.model

    def get_with_max_new_tokens(self, name, max_new_tokens):
        return self.model

    def get_summary_model(self):
        return self.model, GraniteLLMConfig().parameters

    def get_with_tools(self, name, tools):
        return self.model


class ToolCallingFakeModel(FakeListChatModel):
    _calls: int = PrivateAttr(default=0)

    def __init__(self) -> None:
        super().__init__(responses=[])

    async def ainvoke(self, messages, *args, **kwargs):
        self._calls += 1
        if self._calls == 1:
            return AIMessage(
                content="",
                tool_calls=[
                    {"name": "list_directory", "args": {}, "id": "call_directory"}
                ],
            )

        tool_result = next(message for message in reversed(messages) if isinstance(message, ToolMessage))
        if not any(entry["name"] == "test.txt" for entry in tool_result.content):
            raise AssertionError("Tool result was not passed to the model")
        return AIMessage(content="test.txt 파일을 찾았습니다.")


class ToolCallingFakeModels(FakeModels):
    def __init__(self, *args) -> None:
        self.model = ToolCallingFakeModel()


class FileCreatingFakeModel(FakeListChatModel):
    _calls: int = PrivateAttr(default=0)

    def __init__(self) -> None:
        super().__init__(responses=[])

    async def ainvoke(self, messages, *args, **kwargs):
        self._calls += 1
        if self._calls == 1:
            return AIMessage(
                content="",
                tool_calls=[{
                    "name": "create_file",
                    "args": {"path": "note.txt", "content": "테스트 내용"},
                    "id": "call_create_file",
                }],
            )
        tool_result = next(message for message in reversed(messages) if isinstance(message, ToolMessage))
        if "적용했습니다" not in tool_result.content:
            raise AssertionError("Approval result was not returned to the model")
        return AIMessage(content="note.txt 파일을 만들었습니다.")


class FileCreatingFakeModels(FakeModels):
    def __init__(self, *args) -> None:
        self.model = FileCreatingFakeModel()


class FileUpdatingFakeModel(FakeListChatModel):
    _calls: int = PrivateAttr(default=0)

    def __init__(self) -> None:
        super().__init__(responses=[])

    async def ainvoke(self, messages, *args, **kwargs):
        self._calls += 1
        if self._calls == 1:
            return AIMessage(content="", tool_calls=[{
                "name": "update_file", "args": {"path": "note.txt", "old_text": "old", "new_text": "new"}, "id": "edit_1"
            }])
        return AIMessage(content="변경 검토가 끝났습니다.")


class FileUpdatingFakeModels(FakeModels):
    def __init__(self, *args) -> None:
        self.model = FileUpdatingFakeModel()


class WebSearchingFakeModel(FakeListChatModel):
    _calls: int = PrivateAttr(default=0)

    def __init__(self) -> None:
        super().__init__(responses=[])

    async def ainvoke(self, messages, *args, **kwargs):
        self._calls += 1
        if self._calls == 1:
            return AIMessage(content="", tool_calls=[{
                "name": "web_search", "args": {"query": "LangGraph 공식 문서"}, "id": "search_1"
            }])
        tool_result = next(message for message in reversed(messages) if isinstance(message, ToolMessage))
        if "https://langchain-ai.github.io/langgraph/" not in tool_result.content:
            raise AssertionError("Search result URL was not passed to the model")
        return AIMessage(content="공식 문서: https://langchain-ai.github.io/langgraph/")


class WebSearchingFakeModels(FakeModels):
    def __init__(self, *args) -> None:
        self.model = WebSearchingFakeModel()


class ReminderFakeModel(FakeListChatModel):
    _calls: int = PrivateAttr(default=0)

    def __init__(self) -> None:
        super().__init__(responses=[])

    async def ainvoke(self, messages, *args, **kwargs):
        self._calls += 1
        if not any(isinstance(message, ToolMessage) for message in messages):
            return AIMessage(content="", tool_calls=[{
                "name": "propose_reminder",
                "args": {"title": "발표 준비", "due_date": "2026-09-29", "priority": "high"},
                "id": "reminder_1",
            }])
        tool_result = next(message for message in reversed(messages) if isinstance(message, ToolMessage))
        return AIMessage(content=tool_result.content)


class ReminderFakeModels(FakeModels):
    def __init__(self, *args) -> None:
        self.model = ReminderFakeModel()


class ReminderFlakyFakeModel(ReminderFakeModel):
    async def ainvoke(self, messages, *args, **kwargs):
        if any(isinstance(message, ToolMessage) for message in messages) and self._calls == 1:
            self._calls += 1
            raise RuntimeError("temporary model failure")
        return await super().ainvoke(messages, *args, **kwargs)


class ReminderFlakyFakeModels(FakeModels):
    def __init__(self, *args) -> None:
        self.model = ReminderFlakyFakeModel()


class ReminderInformationFakeModel(FakeListChatModel):
    def __init__(self) -> None:
        super().__init__(responses=[])

    async def ainvoke(self, messages, *args, **kwargs):
        assert isinstance(messages[0], SystemMessage)
        assert "새 미리 알림 등록에만 제목과 날짜가 필수" in messages[0].content
        inputs = [message.content for message in messages if isinstance(message, HumanMessage)]
        if len(inputs) == 1:
            return AIMessage(content="필수: 제목, 날짜. 선택: 시간, 메모, URL, 목록, 반복, 우선순위.")
        if len(inputs) == 2:
            return AIMessage(content="날짜를 알려주세요.")
        return AIMessage(content="", tool_calls=[{
            "name": "propose_reminder", "args": {"title": "발표 준비", "due_date": "2026-09-29"},
            "id": "after_missing_inputs",
        }])


class ReminderInformationFakeModels(FakeModels):
    def __init__(self, *args) -> None:
        self.model = ReminderInformationFakeModel()


class AgentTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_reminder_information_is_carried_across_turns(self):
        with tempfile.TemporaryDirectory() as directory:
            async with open_checkpointer(Path(directory) / "checkpoints.sqlite") as saver:
                service = AgentService(ReminderInformationFakeModels(), saver)
                conversation_id = uuid4()
                first = await service.run(AgentRequest(message="리마인더 등록해줘", conversation_id=conversation_id))
                self.assertIn("제목, 날짜", first.answer)
                state = await service.graph.aget_state({"configurable": {"thread_id": str(conversation_id)}})
                self.assertEqual(state.values["active_workflow"], "reminder")
                self.assertFalse(any(isinstance(message, SystemMessage) for message in state.values["messages"]))
                second = await service.run(AgentRequest(message="발표 준비", conversation_id=conversation_id))
                self.assertIn("날짜", second.answer)
                proposal = await service.run(AgentRequest(message="2026-09-29", conversation_id=conversation_id))
                self.assertEqual(proposal["type"], "reminder_proposal")
                self.assertEqual(proposal["reminder"]["title"], "발표 준비")

    async def test_reminder_proposal_waits_for_save_result(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "checkpoints.sqlite"
            async with open_checkpointer(path) as saver:
                service = AgentService(ReminderFakeModels(), saver)
                proposal = await service.run(AgentRequest(message="내일 발표 준비 알림 등록해줘"))
                self.assertEqual(proposal["type"], "reminder_proposal")
                self.assertEqual(proposal["reminder"]["priority"], "high")
                proposal_id = proposal["reminder"]["proposal_id"]
                state = await service.graph.aget_state({"configurable": {"thread_id": proposal["conversation_id"]}})
                self.assertIn("review_reminder", state.next)
                with self.assertRaisesRegex(ValueError, "identifier"):
                    await ReviewService(service.graph).resume_reminder_creation(proposal["conversation_id"], {"status": "saved", "proposal_id": proposal_id})
                with self.assertRaisesRegex(ValueError, "does not match"):
                    await ReviewService(service.graph).resume_reminder_creation(proposal["conversation_id"], {"status": "rejected", "proposal_id": "wrong"})
                result = {"status": "saved", "proposal_id": proposal_id, "identifier": "test-id"}
                final = await ReviewService(service.graph).resume_reminder_creation(proposal["conversation_id"], result)
                self.assertIn("저장에 성공", final.answer)
                self.assertIn("test-id", final.answer)
                state = await service.graph.aget_state({"configurable": {"thread_id": proposal["conversation_id"]}})
                self.assertIsNone(state.values["active_workflow"])
                repeated = await ReviewService(service.graph).resume_reminder_creation(proposal["conversation_id"], result)
                self.assertEqual(repeated.answer, final.answer)

    async def test_reminder_rejection_does_not_claim_saved(self):
        with tempfile.TemporaryDirectory() as directory:
            async with open_checkpointer(Path(directory) / "checkpoints.sqlite") as saver:
                service = AgentService(ReminderFakeModels(), saver)
                proposal = await service.run(AgentRequest(message="알림 등록해줘"))
                final = await ReviewService(service.graph).resume_reminder_creation(proposal["conversation_id"], {"status": "rejected", "proposal_id": proposal["reminder"]["proposal_id"]})
                self.assertIn("저장되지 않았습니다", final.answer)

    async def test_reminder_pending_review_survives_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "checkpoints.sqlite"
            async with open_checkpointer(path) as saver:
                service = AgentService(ReminderFakeModels(), saver)
                proposal = await service.run(AgentRequest(message="알림 등록해줘"))
            async with open_checkpointer(path) as saver:
                service = AgentService(ReminderFakeModels(), saver)
                state = await service.graph.aget_state({"configurable": {"thread_id": proposal["conversation_id"]}})
                self.assertIn("review_reminder", state.next)
                final = await ReviewService(service.graph).resume_reminder_creation(proposal["conversation_id"], {
                    "status": "confirmed_not_saved", "proposal_id": proposal["reminder"]["proposal_id"]
                })
                self.assertIn("등록되지 않았음", final.answer)

    async def test_reminder_save_failure_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            async with open_checkpointer(Path(directory) / "checkpoints.sqlite") as saver:
                service = AgentService(ReminderFakeModels(), saver)
                proposal = await service.run(AgentRequest(message="알림 등록해줘"))
                final = await ReviewService(service.graph).resume_reminder_creation(proposal["conversation_id"], {
                    "status": "failed", "proposal_id": proposal["reminder"]["proposal_id"],
                    "error": "미리 알림 접근 권한이 없습니다",
                })
                self.assertIn("실패", final.answer)
                self.assertIn("권한", final.answer)

    async def test_saved_reminder_result_can_resume_after_model_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            async with open_checkpointer(Path(directory) / "checkpoints.sqlite") as saver:
                service = AgentService(ReminderFlakyFakeModels(), saver)
                proposal = await service.run(AgentRequest(message="알림 등록해줘"))
                result = {"status": "saved", "proposal_id": proposal["reminder"]["proposal_id"], "identifier": "saved-id"}
                with self.assertRaisesRegex(RuntimeError, "temporary model failure"):
                    await ReviewService(service.graph).resume_reminder_creation(proposal["conversation_id"], result)
                final = await ReviewService(service.graph).resume_reminder_creation(proposal["conversation_id"], result)
                self.assertIn("saved-id", final.answer)

    async def test_web_search_returns_sources_to_model(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(DuckDuckGoSearchAPIWrapper, "results", return_value=[{
                "title": "LangGraph", "link": "https://langchain-ai.github.io/langgraph/", "snippet": "공식 문서"
            }]) as search:
                async with open_checkpointer(Path(directory) / "checkpoints.sqlite") as saver:
                    models = WebSearchingFakeModels()
                    service = AgentService(models, saver)
                    response = await service.run(AgentRequest(message="LangGraph 찾아줘"))
            self.assertIn("https://langchain-ai.github.io/langgraph/", response.answer)
            self.assertEqual(search.call_count, 1)
            self.assertEqual(models.model._calls, 2)

    async def test_update_requires_approval_and_reject_does_not_write(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "note.txt"
            target.write_text("old", encoding="utf-8")
            async with open_checkpointer(root / "checkpoints.sqlite") as saver:
                service = AgentService(FileUpdatingFakeModels(), saver)
                proposal = await service.run(AgentRequest(message="바꿔줘", working_directory=str(root)))
                self.assertEqual(proposal["type"], "file_edit_proposal")
                self.assertIn("+new", proposal["diff"])
                self.assertEqual(target.read_text(), "old")
                await ReviewService(service.graph).resume_file_change(proposal["conversation_id"], "reject")
                self.assertEqual(target.read_text(), "old")

    async def test_update_rejects_stale_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "note.txt"
            target.write_text("old", encoding="utf-8")
            async with open_checkpointer(root / "checkpoints.sqlite") as saver:
                service = AgentService(FileUpdatingFakeModels(), saver)
                proposal = await service.run(AgentRequest(message="바꿔줘", working_directory=str(root)))
                target.write_text("external edit", encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "changed after review"):
                    await ReviewService(service.graph).resume_file_change(proposal["conversation_id"], "approve")
                self.assertEqual(target.read_text(), "external edit")

    async def test_update_applies_only_after_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "note.txt"
            target.write_text("old", encoding="utf-8")
            async with open_checkpointer(root / "checkpoints.sqlite") as saver:
                service = AgentService(FileUpdatingFakeModels(), saver)
                proposal = await service.run(AgentRequest(message="바꿔줘", working_directory=str(root)))
                self.assertEqual(target.read_text(), "old")
                result = await ReviewService(service.graph).resume_file_change(proposal["conversation_id"], "approve")
                self.assertEqual(result.answer, "변경 검토가 끝났습니다.")
                self.assertEqual(target.read_text(), "new")

    async def test_history_isolation_and_persistence(self):
        first, second = uuid4(), uuid4()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "checkpoints.sqlite"
            async with open_checkpointer(path) as saver:
                service = AgentService(FakeModels(), saver)
                await service.run(AgentRequest(message="첫 메시지", conversation_id=first))
                await service.run(AgentRequest(message="후속 메시지", conversation_id=first))
                await service.run(AgentRequest(message="새 대화", conversation_id=second))
                for conversation, expected in [(first, 4), (second, 2)]:
                    state = await service.graph.aget_state({"configurable": {"thread_id": str(conversation)}})
                    self.assertEqual(len(state.values["messages"]), expected)
            async with open_checkpointer(path) as saver:
                service = AgentService(FakeModels(), saver)
                state = await service.graph.aget_state({"configurable": {"thread_id": str(first)}})
                self.assertEqual(state.values["messages"][0].content, "첫 메시지")

    async def test_tool_call_lists_the_selected_working_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            working_directory = Path(directory)
            (working_directory / "test.txt").touch()
            async with open_checkpointer(working_directory / "checkpoints.sqlite") as saver:
                models = ToolCallingFakeModels()
                service = AgentService(models, saver)
                response = await service.run(
                    AgentRequest(
                        message="파일을 찾아줘",
                        working_directory=str(working_directory),
                    )
                )

            self.assertEqual(response.answer, "test.txt 파일을 찾았습니다.")
            self.assertEqual(models.model._calls, 2)

    async def test_tool_call_creates_file_in_selected_working_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            working_directory = Path(directory)
            async with open_checkpointer(working_directory / "checkpoints.sqlite") as saver:
                models = FileCreatingFakeModels()
                service = AgentService(models, saver)
                response = await service.run(AgentRequest(
                    message="note.txt 파일을 만들어줘",
                    working_directory=str(working_directory),
                ))
                self.assertEqual(response["type"], "file_edit_proposal")
                self.assertFalse((working_directory / "note.txt").exists())
                final = await ReviewService(service.graph).resume_file_change(response["conversation_id"], "approve")

            self.assertEqual(final.answer, "note.txt 파일을 만들었습니다.")
            self.assertEqual((working_directory / "note.txt").read_text(), "테스트 내용")
            self.assertEqual(models.model._calls, 2)

    async def test_protocol_recovers_and_reuses_model(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = Settings(agent_data_dir=Path(directory), _env_file=None)
            requests = ["not json", "[]", json.dumps({"id": "bad", "type": "generate_reply", "message": " "})]
            for i in range(2):
                requests.append(json.dumps({"id": str(i), "type": "generate_reply", "message": "안녕"}))
            output = io.StringIO()
            with patch("personal_agent.config.settings.get_settings", return_value=settings), patch(
                "personal_agent.services.agent_runtime.ChatModels", side_effect=FakeModels
            ) as models:
                await serve(io.StringIO("\n".join(requests) + "\n"), output)
                self.assertEqual(models.call_count, 1)
            replies = [json.loads(line) for line in output.getvalue().splitlines()]
            self.assertEqual([r["type"] for r in replies], ["error"] * 3 + ["assistant_reply"] * 2)
            self.assertEqual(replies[-1]["answer"], "테스트 응답")
            self.assertEqual(replies[-1]["id"], "1")


class ToolCallParserTests(unittest.TestCase):
    def test_parses_granite_tool_call(self):
        content, tool_calls = parse_tool_calls(
            "확인하겠습니다.\n"
            "<tool_call>\n"
            "<function=list_directory>\n"
            "</function>\n"
            "</tool_call>"
        )

        self.assertEqual(content, "확인하겠습니다.")
        self.assertEqual(len(tool_calls), 1)
        self.assertEqual(tool_calls[0]["name"], "list_directory")
        self.assertEqual(tool_calls[0]["args"], {})

    def test_parses_tool_call_arguments(self):
        _, tool_calls = parse_tool_calls(
            "<tool_call>\n"
            "<function=read_file>\n"
            "<parameter=path>\nREADME.md\n</parameter>\n"
            "<parameter=limit>\n10\n</parameter>\n"
            "</function>\n"
            "</tool_call>"
        )

        self.assertEqual(
            tool_calls[0]["args"],
            {"path": "README.md", "limit": 10},
        )

    def test_model_result_contains_tool_calls(self):
        result = GraniteChatModel._to_chat_result(
            LLMResult(
                generations=[[
                    Generation(
                        text="<tool_call>\n<function=list_directory>\n</function>\n</tool_call>"
                    )
                ]]
            )
        )

        message = result.generations[0].message
        self.assertEqual(message.content, "")
        self.assertEqual(message.tool_calls[0]["name"], "list_directory")
        self.assertEqual(message.tool_calls[0]["args"], {})

    def test_converts_tool_messages_for_granite(self):
        tool_call = AIMessage(
            content="",
            tool_calls=[{"name": "list_directory", "args": {}, "id": "call_1"}],
        )
        tool_result = ToolMessage(
            content='[{"name": "test", "type": "file"}]',
            tool_call_id="call_1",
        )

        self.assertEqual(
            GraniteChatModel._to_chatml_format(tool_call)["tool_calls"],
            [{"function": {"name": "list_directory", "arguments": {}}}],
        )
        self.assertEqual(
            GraniteChatModel._to_chatml_format(tool_result),
            {"role": "tool", "content": '[{"name": "test", "type": "file"}]'},
        )


class FileCreationTests(unittest.TestCase):
    def test_rejects_overwrite_and_paths_outside_working_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "workspace"
            root.mkdir()
            arguments = {"working_directory": str(root), "content": "new"}

            created = create_file.invoke({**arguments, "path": "note.txt"})
            self.assertEqual(created, str((root / "note.txt").resolve()))
            with self.assertRaises(FileExistsError):
                create_file.invoke({**arguments, "path": "note.txt"})
            self.assertEqual((root / "note.txt").read_text(), "new")

            with self.assertRaises(ValueError):
                create_file.invoke({**arguments, "path": "../outside.txt"})
            with self.assertRaises(ValueError):
                create_file.invoke({**arguments, "path": str(Path(directory) / "outside.txt")})
            self.assertFalse((Path(directory) / "outside.txt").exists())


if __name__ == "__main__":
    unittest.main()
