import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from uuid import UUID

from langchain_core.messages import AIMessage, HumanMessage

from personal_agent.config.settings import Settings
from personal_agent.graph.checkpoint import open_checkpointer
from personal_agent.llm.define_llm import ChatModelName, ModelParameters
from personal_agent.llm.granite.mlx_chat_model import GraniteMLXChatModel
from personal_agent.llm.registry_llm import ChatModels
from personal_agent.schemas.agent import AgentRequest
from personal_agent.services.chat_service import AgentService
from personal_agent.services.review_service import ReviewService
from personal_agent.tools.calendar import create_calendar_event


class MLXModelTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.addCleanup(self.executor.shutdown)
        self.tokenizer = Mock()
        self.tokenizer.apply_chat_template.return_value = "formatted prompt"
        self.tokenizer.encode.return_value = [1, 2, 3]
        self.model = GraniteMLXChatModel(model_id="test")
        self.model._runner = SimpleNamespace(executor=self.executor, model=object(), tokenizer=self.tokenizer)

    def modules(self, stream):
        return patch.multiple("personal_agent.llm.granite.mlx_chat_model",
                              stream_generate=stream, make_sampler=lambda **kwargs: kwargs)

    def response(self, text, finish="stop"):
        return SimpleNamespace(text=text, prompt_tps=100.0, generation_tps=40.0, peak_memory=6.0,
                               prompt_tokens=3, generation_tokens=20, finish_reason=finish)

    async def test_tool_binding_and_async_generation(self):
        text = '<tool_call><function=create_calendar_event><parameter=title>러닝크루</parameter></function></tool_call>'
        stream = Mock(return_value=iter([self.response(text)]))
        with self.modules(stream):
            bound = self.model.bind_tools([create_calendar_event])
            result = await bound.ainvoke([HumanMessage(content="일정 추가")])
        self.assertEqual(result.tool_calls[0]["name"], "create_calendar_event")
        self.assertEqual(result.tool_calls[0]["args"], {"title": "러닝크루"})
        self.assertEqual(self.model._bound_tools, [])
        self.assertIs(bound._runner, self.model._runner)
        self.tokenizer.encode.assert_any_call("formatted prompt", add_special_tokens=False)
        self.assertFalse(self.tokenizer.apply_chat_template.call_args.kwargs["enable_thinking"])
        self.assertEqual(result.usage_metadata["output_tokens"], 20)

    async def test_summary_limit_and_stop(self):
        stream = Mock(return_value=iter([self.response("hello END ignored")]))
        with self.modules(stream):
            result = await self.model.with_max_new_tokens(64).ainvoke([HumanMessage(content="요약")], stop=["END"])
        self.assertEqual(result.content, "hello")
        self.assertEqual(stream.call_args.kwargs["max_tokens"], 64)

    async def test_truncated_tool_call_is_error(self):
        with self.modules(lambda *a, **k: iter([self.response("<tool_call><function=unfinished>", "length")])):
            with self.assertRaisesRegex(ValueError, "출력 제한"):
                await self.model.ainvoke([HumanMessage(content="추가")])

    async def test_bound_copies_serialize_inference(self):
        threads = []
        active = 0
        def stream(*args, **kwargs):
            nonlocal active
            active += 1
            self.assertEqual(active, 1)
            threads.append(threading.get_ident())
            time.sleep(.01)
            yield self.response("안녕")
            active -= 1
        with self.modules(stream):
            replies = await asyncio.gather(self.model.ainvoke([HumanMessage(content="안녕")]),
                         self.model.bind_tools([]).ainvoke([HumanMessage(content="다시")]))
        self.assertEqual(len(set(threads)), 1)
        self.assertEqual([r.content for r in replies], ["안녕", "안녕"])

    async def test_graph_creation_approval_resume(self):
        outputs = iter([
            '<tool_call><function=create_file><parameter=path>demo.txt</parameter><parameter=content>테스트</parameter></function></tool_call>',
            '파일 생성을 취소했습니다.',
        ])
        def stream(*args, **kwargs):
            return iter([self.response(next(outputs))])
        models = ChatModels(Settings(_env_file=None))
        models._models[ChatModelName.GRANITE] = self.model
        models._parameters[ChatModelName.GRANITE] = ModelParameters(context_window=16384, max_new_tokens=2048, summary_max_new_tokens=256)
        with self.modules(stream), tempfile.TemporaryDirectory() as directory:
            async with open_checkpointer(Path(directory) / 'test.sqlite') as saver:
                service = AgentService(models, saver)
                request = AgentRequest(message='demo.txt 파일 만들어줘', working_directory=directory, model='granite-mlx')
                result = await service.run(request)
                self.assertIsInstance(result, dict)
                self.assertFalse((Path(directory) / 'demo.txt').exists())
                response = await ReviewService(service.graph).resume_file_change(UUID(result['conversation_id']), 'reject')
                self.assertEqual(response.model, ChatModelName.GRANITE)
                self.assertIn('취소', response.answer)
                self.assertFalse((Path(directory) / 'demo.txt').exists())

    def test_legacy_model_identifier_uses_mlx(self):
        self.assertEqual(ChatModelName("granite-mlx"), ChatModelName.GRANITE)
        self.assertEqual(AgentRequest(message="안녕", model="granite-mlx").model.value, "granite")
