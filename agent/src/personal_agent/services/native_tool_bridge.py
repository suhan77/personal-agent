"""Python 도구가 실행 중인 Swift 앱에 읽기 전용 기능을 요청하는 JSONL 브리지."""

import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
import logging
from uuid import uuid4


_current_bridge: ContextVar["NativeToolBridge | None"] = ContextVar("native_tool_bridge", default=None)
_current_request_id: ContextVar[str | None] = ContextVar("native_request_id", default=None)
logger = logging.getLogger(__name__)


class NativeToolBridge:
    def __init__(self, emit) -> None:
        self._emit = emit
        self._pending: dict[str, tuple[str, asyncio.Future]] = {}

    async def request(self, tool: str, arguments: dict, timeout: float = 30) -> object:
        parent_id = _current_request_id.get()
        if not parent_id:
            raise RuntimeError("Native tool request requires an active agent request")
        call_id = str(uuid4())
        future = asyncio.get_running_loop().create_future()
        self._pending[call_id] = (parent_id, future)
        try:
            logger.info("macOS 도구 요청 | name=%s | call_id=%s", tool, call_id)
            self._emit({"id": parent_id, "type": "native_tool_request", "tool": tool,
                        "call_id": call_id, "arguments": arguments})
            result = await asyncio.wait_for(future, timeout=timeout)
            logger.info("macOS 도구 완료 | name=%s | call_id=%s", tool, call_id)
            return result
        except TimeoutError as exc:
            logger.error("macOS 도구 응답 시간 초과 | name=%s | call_id=%s", tool, call_id)
            raise TimeoutError(f"{tool} 도구의 macOS 응답이 {timeout:g}초 안에 오지 않았습니다") from exc
        except Exception as exc:
            logger.error("macOS 도구 실패 | name=%s | call_id=%s | error=%s", tool, call_id, exc)
            raise
        finally:
            self._pending.pop(call_id, None)

    def resolve(self, payload: dict) -> None:
        call_id = payload.get("call_id")
        pending = self._pending.get(call_id)
        if pending is None or pending[0] != payload.get("id"):
            return
        future = pending[1]
        if future.done():
            return
        if isinstance(payload.get("error"), str) and payload["error"]:
            future.set_exception(RuntimeError(payload["error"]))
        elif "result" in payload:
            future.set_result(payload["result"])
        else:
            future.set_exception(ValueError("Native tool response has no result"))

    def close(self) -> None:
        for _, future in self._pending.values():
            if not future.done():
                future.set_exception(ConnectionError("Swift app disconnected"))
        self._pending.clear()


@contextmanager
def native_tool_context(bridge: NativeToolBridge, request_id: str):
    bridge_token = _current_bridge.set(bridge)
    request_token = _current_request_id.set(request_id)
    try:
        yield
    finally:
        _current_request_id.reset(request_token)
        _current_bridge.reset(bridge_token)


async def call_native_tool(tool: str, arguments: dict, timeout: float = 30) -> object:
    bridge = _current_bridge.get()
    if bridge is None:
        raise RuntimeError("Native tool bridge is unavailable")
    return await bridge.request(tool, arguments, timeout=timeout)
