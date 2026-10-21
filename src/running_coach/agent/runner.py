"""Run one conversational turn through the graph — streamed or all at once.

Every surface (CLI, HTTP JSON, HTTP SSE, evals) goes through `stream_turn`, so
tracing, tool-call bookkeeping and error handling live in one place.
"""

import asyncio
import json
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from langgraph.graph.state import CompiledStateGraph
from openinference.instrumentation import using_session
from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes
from opentelemetry import trace
from opentelemetry.trace import StatusCode

from running_coach import metrics
from running_coach.agent.graph import RECURSION_LIMIT
from running_coach.agent.prompts import COACH_PROMPT_VERSION

tracer = trace.get_tracer("running-coach")


@dataclass
class ToolCallRecord:
    name: str
    input: dict[str, Any]
    output: Any


@dataclass
class TurnResult:
    answer: str
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    steps: int = 0
    usage: dict[str, int] = field(default_factory=lambda: {"input_tokens": 0, "output_tokens": 0})


# --- stream events (the SSE endpoint sends each one as `event: <kind>`) ---


@dataclass
class TokenEvent:
    text: str
    kind = "token"


@dataclass
class ToolCallEvent:
    name: str
    input: dict[str, Any]
    kind = "tool_call"


@dataclass
class ToolResultEvent:
    name: str
    output: Any
    kind = "tool_result"


@dataclass
class DoneEvent:
    result: TurnResult
    kind = "done"


@dataclass
class ErrorEvent:
    error: BaseException
    kind = "error"


type TurnEvent = TokenEvent | ToolCallEvent | ToolResultEvent | DoneEvent | ErrorEvent


async def stream_turn(
    graph: CompiledStateGraph,
    message: str,
    *,
    session_id: str,
    metadata: dict[str, Any] | None = None,
) -> AsyncIterator[TurnEvent]:
    """Yield tokens and tool activity as they happen, then a DoneEvent (or an ErrorEvent).

    The graph runs in its own task and hands events over through a queue: the task
    owns the tracing context for the whole turn, and if the consumer stops early
    (HTTP client disconnected) the `finally` cancels the run.
    """
    queue: asyncio.Queue[TurnEvent | None] = asyncio.Queue()
    task = asyncio.create_task(_run(graph, message, session_id, metadata or {}, queue.put))
    try:
        while (event := await queue.get()) is not None:
            yield event
    finally:
        task.cancel()


async def run_turn(
    graph: CompiledStateGraph,
    message: str,
    *,
    session_id: str,
    metadata: dict[str, Any] | None = None,
) -> TurnResult:
    """Non-streaming turn: the final result, or the exception that ended the turn."""
    async for event in stream_turn(graph, message, session_id=session_id, metadata=metadata):
        if isinstance(event, DoneEvent):
            return event.result
        if isinstance(event, ErrorEvent):
            raise event.error
    raise RuntimeError("turn ended without a result")


async def _run(graph, message, session_id, metadata, emit) -> None:
    config = {
        "configurable": {"thread_id": session_id},
        "recursion_limit": RECURSION_LIMIT,
        "metadata": {"prompt_version": COACH_PROMPT_VERSION, **metadata},
    }
    before = await graph.aget_state(config) if graph.checkpointer else None
    started = time.perf_counter()
    surface = {"surface": str(metadata.get("surface", "unknown"))}
    try:
        # One root AGENT span per turn, tagged with the session id: Phoenix groups
        # traces by session.id, and every LangChain span (LLM calls, tools) nests under it.
        with (
            using_session(session_id),
            tracer.start_as_current_span(
                "coach.turn",
                attributes={
                    SpanAttributes.OPENINFERENCE_SPAN_KIND: OpenInferenceSpanKindValues.AGENT.value,
                    SpanAttributes.INPUT_VALUE: message,
                    SpanAttributes.METADATA: json.dumps({"promptVersion": COACH_PROMPT_VERSION, **metadata}),
                },
            ) as span,
        ):
            result = await _stream_graph(graph, message, config, emit)
            span.set_attribute(SpanAttributes.OUTPUT_VALUE, result.answer)
            # outcome next to the inputs, so a turn can be judged from the span list alone
            span.set_attribute(
                SpanAttributes.METADATA,
                json.dumps(
                    {
                        "promptVersion": COACH_PROMPT_VERSION,
                        **metadata,
                        "tools": [t.name for t in result.tool_calls],
                        "steps": result.steps,
                        "usage": result.usage,
                    }
                ),
            )
            span.set_status(StatusCode.OK)
        _record_metrics(result, surface, started)
        await emit(DoneEvent(result))
    except Exception as err:  # the span already recorded it
        metrics.turn_duration.record(time.perf_counter() - started, {**surface, "outcome": "error"})
        await _rollback(graph, config, before)
        await emit(ErrorEvent(err))
    finally:
        await emit(None)


def _record_metrics(result: TurnResult, surface: dict[str, str], started: float) -> None:
    metrics.turn_duration.record(time.perf_counter() - started, {**surface, "outcome": "ok"})
    metrics.turn_steps.record(result.steps, surface)
    for kind in ("input", "output"):
        metrics.tokens.add(result.usage[f"{kind}_tokens"], {"type": kind})
    for call in result.tool_calls:
        metrics.tool_calls.add(1, {"tool": call.name})


async def _stream_graph(graph, message, config, emit) -> TurnResult:
    result = TurnResult(answer="")
    pending: dict[str, ToolCallRecord] = {}
    async for mode, chunk in graph.astream(
        {"messages": [HumanMessage(message)]}, config, stream_mode=["messages", "updates"]
    ):
        if mode == "messages":
            msg, meta = chunk
            if isinstance(msg, AIMessageChunk) and meta.get("langgraph_node") == "agent" and msg.text:
                await emit(TokenEvent(msg.text))
            continue

        for update in chunk.values():  # mode == "updates": {node_name: state update}
            for msg in (update or {}).get("messages", []):
                if isinstance(msg, AIMessage):
                    result.steps += 1
                    result.answer = msg.text
                    for k in ("input_tokens", "output_tokens"):
                        result.usage[k] += (msg.usage_metadata or {}).get(k, 0)
                    for call in msg.tool_calls:
                        pending[call["id"]] = record = ToolCallRecord(call["name"], call["args"], None)
                        result.tool_calls.append(record)
                        await emit(ToolCallEvent(call["name"], call["args"]))
                elif isinstance(msg, ToolMessage):
                    record = pending.pop(msg.tool_call_id, None)
                    output = _parse_tool_output(msg.content)
                    if record:
                        record.output = output
                    await emit(ToolResultEvent(msg.name or (record.name if record else "?"), output))
    return result


def _parse_tool_output(content: Any) -> Any:
    try:
        return json.loads(content) if isinstance(content, str) else content
    except json.JSONDecodeError:
        return content


async def _rollback(graph, config, before) -> None:
    """Forget a failed turn, so the client can simply retry.

    LangGraph checkpoints the user message (and any finished steps) as the turn
    runs; we move the thread back to its checkpoint from before the turn.
    """
    if before is None:
        return
    if not before.values.get("messages"):  # brand-new conversation
        await graph.checkpointer.adelete_thread(config["configurable"]["thread_id"])
    else:  # fork from the last good checkpoint; it becomes the thread's latest state
        await graph.aupdate_state(before.config, None, as_node="agent")
