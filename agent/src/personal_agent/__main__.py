"""JSON Lines entry point for the persistent local agent worker."""
import asyncio
import json
import logging
import sys

from personal_agent.common.logging import configure_logging
from personal_agent.runtime import AgentRuntime
from personal_agent.services.native_tool_bridge import NativeToolBridge, native_tool_context


async def serve(input_stream, output_stream):
    runtime = await AgentRuntime.create()

    def emit(event):
        output_stream.write(json.dumps(event, ensure_ascii=False) + "\n")
        output_stream.flush()

    bridge = NativeToolBridge(emit)
    requests = asyncio.Queue()

    async def read_input():
        while line := await asyncio.to_thread(input_stream.readline):
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                await requests.put(line)
                continue
            if isinstance(payload, dict) and payload.get("type") == "native_tool_result":
                bridge.resolve(payload)
            else:
                await requests.put(line)
        await requests.put(None)

    async def process_requests():
        while (line := await requests.get()) is not None:
            request_id = None
            try:
                payload = json.loads(line)
                if not isinstance(payload, dict):
                    raise ValueError("Request must be an object")
                request_id = payload.get("id")
                if not isinstance(request_id, str) or not request_id:
                    raise ValueError("Request id is required")
                with native_tool_context(bridge, request_id):
                    response = await runtime.handle(payload, request_id)
            except Exception as exc:
                logging.exception("Agent request failed")
                response = {"id": request_id, "type": "error", "error": str(exc)}
            emit(response)

    try:
        await asyncio.gather(read_input(), process_requests())
    finally:
        bridge.close()
        await runtime.close()


def main():
    protocol_output = sys.stdout
    sys.stdout = sys.stderr
    configure_logging()
    try:
        asyncio.run(serve(sys.stdin, protocol_output))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
