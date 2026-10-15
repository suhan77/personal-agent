import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from personal_agent.config.settings import Settings
from personal_agent.graph.checkpoint import open_checkpointer
from personal_agent.llm.define_llm import ChatModelName
from personal_agent.llm.registry_llm import ChatModels
from personal_agent.schemas.agent import AgentRequest
from personal_agent.services.chat_service import AgentService
from personal_agent.services.native_tool_bridge import NativeToolBridge, native_tool_context
from personal_agent.tools.calendar import find_calendar_events


def completion(message, reason="stop"):
    return httpx.Response(200, json={
        "id": "chatcmpl-test", "object": "chat.completion", "created": 1, "model": "gpt-6-luna",
        "choices": [{"index": 0, "message": {"role": "assistant", **message}, "finish_reason": reason}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
    })


class OpenAIModelTests(unittest.IsolatedAsyncioTestCase):
    def settings(self, key=None):
        return Settings(openai_api_key=key, _env_file=None)

    def test_lazy_initialization_and_missing_key(self):
        with patch("personal_agent.llm.granite.chat_model.GraniteChatModel.from_settings") as local:
            models = ChatModels(self.settings())
            self.assertEqual(models._models, {})
            with self.assertRaisesRegex(ValueError, "OPENAI_API_KEY"):
                models.get(ChatModelName.GPT6_LUNA)
            local.assert_not_called()

    def test_cloud_model_configuration_and_cache(self):
        models = ChatModels(self.settings("test-key"))
        model = models.get(ChatModelName.GPT6_LUNA)
        self.assertIs(model, models.get(ChatModelName.GPT6_LUNA))
        self.assertEqual(model.reasoning_effort, "none")
        self.assertFalse(model.use_responses_api)
        self.assertNotIn(ChatModelName.GRANITE, models._models)
        bound = models.get_with_tools(ChatModelName.GPT6_LUNA, [find_calendar_events])
        self.assertFalse(bound.kwargs["parallel_tool_calls"])
        self.assertFalse(bound.kwargs["tools"][0]["function"]["strict"])
        summary, _ = models.get_summary_model(ChatModelName.GPT6_LUNA)
        self.assertEqual(summary.kwargs["max_completion_tokens"], 256)
        self.assertNotIn("test-key", repr(models._settings))

    async def test_api_tool_roundtrip_through_graph(self):
        requests = []
        def respond(request):
            body = json.loads(request.content)
            requests.append(body)
            self.assertEqual(body["model"], "gpt-6-luna")
            self.assertEqual(body["reasoning_effort"], "none")
            if len(requests) == 1:
                return completion({"content": None, "tool_calls": [{"id": "call-calendar", "type": "function", "function": {
                    "name": "find_calendar_events", "arguments": json.dumps({"start": "2026-10-15T00:00:00+09:00", "end": "2026-10-16T00:00:00+09:00"})}}]}, "tool_calls")
            self.assertEqual(body["messages"][-1]["role"], "tool")
            self.assertIn("러닝크루", body["messages"][-1]["content"])
            return completion({"content": "오후 6시에 러닝크루 일정이 있습니다."})

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            models = ChatModels(self.settings("test-key"))
            models._models[ChatModelName.GPT6_LUNA] = ChatOpenAI(model="gpt-6-luna", api_key="test-key", reasoning_effort="none", use_responses_api=False, http_async_client=client)
            from personal_agent.llm.define_llm import ModelParameters
            models._parameters[ChatModelName.GPT6_LUNA] = ModelParameters(context_window=16384, max_new_tokens=2048, summary_max_new_tokens=256)
            bridge = None
            def emit(payload):
                self.assertEqual(payload["tool"], "find_calendar_events")
                bridge.resolve({"id": "request", "call_id": payload["call_id"], "result": {"items": [{"title": "러닝크루"}], "truncated": False}})
            bridge = NativeToolBridge(emit)
            with tempfile.TemporaryDirectory() as directory:
                async with open_checkpointer(Path(directory) / "test.sqlite") as saver:
                    service = AgentService(models, saver)
                    with native_tool_context(bridge, "request"):
                        result = await service.run(AgentRequest(message="오늘 일정 보여줘", model="gpt-6-luna"))
                    self.assertIn("러닝크루", result.answer)
                    self.assertEqual(result.model, ChatModelName.GPT6_LUNA)
                    state = await service.graph.aget_state({"configurable": {"thread_id": str(result.conversation_id)}})
                    self.assertEqual(state.values["model"], "gpt-6-luna")
            self.assertEqual(len(requests), 2)
            self.assertNotIn(ChatModelName.GRANITE, models._models)

    async def test_api_error_does_not_fall_back_to_local(self):
        def respond(request):
            return httpx.Response(401, json={"error": {"message": "Invalid API key", "type": "authentication_error", "code": "invalid_api_key"}})
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            model = ChatOpenAI(model="gpt-6-luna", api_key="test-key", reasoning_effort="none", http_async_client=client, max_retries=0)
            from openai import AuthenticationError
            with self.assertRaises(AuthenticationError):
                await model.ainvoke([HumanMessage(content="안녕")])
