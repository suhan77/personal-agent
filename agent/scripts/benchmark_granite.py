"""Benchmark local inference only; no tool is executed and no app history is used."""
import argparse
import asyncio
import json
from pathlib import Path
from time import perf_counter
from datetime import datetime

from langchain_core.messages import HumanMessage, SystemMessage
from personal_agent.chain.prompts import build_prompt
from personal_agent.config.settings import Settings
from personal_agent.llm.define_llm import ChatModelName
from personal_agent.llm.registry_llm import ChatModels
from personal_agent.tools.calendar import find_calendar_events, create_calendar_event, update_calendar_event


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=["granite"], required=True)
    parser.add_argument("--repeat", type=int, default=2)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.repeat < 1:
        parser.error("--repeat must be positive")
    models = ChatModels(Settings())
    name = ChatModelName(args.model)
    started = perf_counter()
    model = models.get(name)
    load_seconds = perf_counter() - started
    cases = [
        ("chat", "안녕. 한 문장으로 인사해줘.", []),
        ("calendar", '오늘 오후 6시부터 오후 7시까지 "러닝크루" 일정 추가해줘.',
         [find_calendar_events, create_calendar_event, update_calendar_event]),
    ]
    results = []
    for case, prompt, tools in cases:
        messages = [SystemMessage(content=build_prompt("calendar" if tools else None,
                        datetime.fromisoformat("2026-10-15T14:00:00+09:00"))), HumanMessage(content=prompt)]
        bound = model.bind_tools(tools)
        for iteration in range(args.repeat):
            kwargs = {"temperature": 0.0, "max_tokens": 256}
            started = perf_counter()
            response = await bound.ainvoke(messages, **kwargs)
            elapsed = perf_counter() - started
            usage = response.usage_metadata or {}
            metadata = response.response_metadata
            metrics = {"input_tokens": usage.get("input_tokens"), "output_tokens": usage.get("output_tokens"),
                       "prompt_tps": metadata.get("prompt_tps"), "generation_tps": metadata.get("generation_tps")}
            row = {"case": case, "iteration": iteration + 1, "seconds": elapsed, **metrics,
                   "content": response.content, "tool_calls": response.tool_calls}
            results.append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)
    report = {"model": args.model, "load_seconds": load_seconds, "precision": "bf16",
              "thinking": False, "sampling": "greedy", "max_tokens": 256,
              "results": results}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    asyncio.run(main())
