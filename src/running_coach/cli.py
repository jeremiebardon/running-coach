"""Terminal chat with the coach: `uv run coach-chat [--fixtures]`."""

import argparse
import asyncio
import os
import sys
from uuid import uuid4

DIM, RESET = "\x1b[2m", "\x1b[0m"


async def chat(graph, data_source: str) -> None:
    from running_coach.agent.runner import DoneEvent, ErrorEvent, TokenEvent, ToolCallEvent, stream_turn

    session_id = str(uuid4())
    print(f"🏃 Running coach ({data_source} data) — session {session_id[:8]}. Ctrl+C to quit.\n")
    while True:
        question = (await asyncio.to_thread(input, "you › ")).strip()
        if not question:
            continue
        print("\ncoach › ", end="", flush=True)
        async for event in stream_turn(graph, question, session_id=session_id, metadata={"surface": "cli"}):
            match event:
                case TokenEvent(text=text):
                    print(text, end="", flush=True)
                case ToolCallEvent(name=name):
                    print(f"{DIM}[{name}…]{RESET} ", end="", flush=True)
                case DoneEvent(result=r):
                    tools = ", ".join(t.name for t in r.tool_calls) or "none"
                    print(f"\n{DIM}[tools: {tools} · steps: {r.steps}]{RESET}\n")
                case ErrorEvent(error=err):
                    print(f"\n⚠️  {err}\n")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to cp1252
    parser = argparse.ArgumentParser(description="Chat with the running coach in your terminal.")
    parser.add_argument("--fixtures", action="store_true", help="use the demo athlete instead of intervals.icu")
    if parser.parse_args().fixtures:
        os.environ["DATA_SOURCE"] = "fixtures"

    from langgraph.checkpoint.memory import InMemorySaver

    from running_coach.agent.graph import build_graph
    from running_coach.data.factory import athlete_clock, build_data_source
    from running_coach.llm import build_model
    from running_coach.settings import get_settings
    from running_coach.telemetry import init_telemetry, shutdown_telemetry

    settings = get_settings()
    init_telemetry()
    clock = athlete_clock(settings)
    graph = build_graph(build_model(settings.coach_model), build_data_source(settings, clock), clock, InMemorySaver())
    try:
        asyncio.run(chat(graph, settings.data_source))
    except (KeyboardInterrupt, EOFError):
        print()
    finally:
        shutdown_telemetry()
