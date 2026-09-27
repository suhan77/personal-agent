import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import Generation, LLMResult
from pydantic import PrivateAttr
from personal_agent.__main__ import serve
from personal_agent.services.chat_service import AgentService
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
        if not tool_result.content.endswith("note.txt"):
            raise AssertionError("Created file path was not returned to the model")
        return AIMessage(content="note.txt 파일을 만들었습니다.")


class FileCreatingFakeModels(FakeModels):
    def __init__(self, *args) -> None:
        self.model = FileCreatingFakeModel()


class AgentTests(unittest.IsolatedAsyncioTestCase):
    async def test_history_isolation_and_persistence(self):
        first, second = uuid4(), uuid4()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "checkpoints.sqlite"
            async with open_checkpointer(path) as saver:
                service = AgentService(FakeModels(), saver)
                await service.run(AgentRequest(message="첫 메시지", conversation_id=first))
                await service.run(AgentRequest(message="후속 메시지", conversation_id=first))
                await service.run(AgentRequest(message="새 대화", conversation_id=second))
                for conversation, expected in [(first, 5), (second, 3)]:
                    state = await service.graph.aget_state({"configurable": {"thread_id": str(conversation)}})
                    self.assertEqual(len(state.values["messages"]), expected)
            async with open_checkpointer(path) as saver:
                service = AgentService(FakeModels(), saver)
                state = await service.graph.aget_state({"configurable": {"thread_id": str(first)}})
                self.assertEqual(state.values["messages"][1].content, "첫 메시지")

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

            self.assertEqual(response.answer, "note.txt 파일을 만들었습니다.")
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
