"""JSON Lines entry point for the persistent local agent worker."""
import asyncio
import json
import logging
import sys

from personal_agent.common.logging import configure_logging
from personal_agent.services.agent_runtime import AgentRuntime


async def serve(input_stream, output_stream):
    runtime = await AgentRuntime.create()

    def emit(event):
        output_stream.write(json.dumps(event, ensure_ascii=False) + "\n")
        output_stream.flush()

    try:
        while line := await asyncio.to_thread(input_stream.readline):
            request_id = None
            try:
                payload = json.loads(line)
                if not isinstance(payload, dict):
                    raise ValueError("Request must be an object")
                request_id = payload.get("id")
                if not isinstance(request_id, str) or not request_id:
                    raise ValueError("Request id is required")
                response = await runtime.handle(payload, request_id)
            except Exception as exc:
                logging.exception("Agent request failed")
                response = {"id": request_id, "type": "error", "error": str(exc)}
            emit(response)
    finally:
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
