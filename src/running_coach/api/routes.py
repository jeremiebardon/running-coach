import logging
from collections.abc import AsyncIterable
from dataclasses import asdict
from uuid import uuid4

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from fastapi.sse import EventSourceResponse, ServerSentEvent

from running_coach.agent.runner import DoneEvent, ErrorEvent, TurnEvent, TurnResult, run_turn, stream_turn
from running_coach.api.schemas import ChatRequest, ChatResponse, Health

log = logging.getLogger(__name__)
router = APIRouter()

FAILURE_MESSAGE = "The coach failed to answer. Check server logs / Phoenix trace."


@router.get("/health")
async def health(request: Request) -> Health:
    return Health(status="ok", data_source=request.app.state.data_source)


@router.post("/chat", responses={502: {"description": "The agent failed; the turn was not saved, retry is safe."}})
async def chat(body: ChatRequest, request: Request) -> ChatResponse:
    """One turn, answered in a single JSON response."""
    session_id = body.session_id or str(uuid4())
    try:
        result = await run_turn(request.app.state.graph, body.message, session_id=session_id, metadata=_meta("http"))
    except Exception:
        log.exception("[chat] turn failed")
        return JSONResponse({"sessionId": session_id, "error": FAILURE_MESSAGE}, status_code=502)
    return _response(session_id, result)


@router.post("/chat/stream", response_class=EventSourceResponse)
async def chat_stream(body: ChatRequest, request: Request) -> AsyncIterable[ServerSentEvent]:
    """One turn, streamed as Server-Sent Events.

    Events: `session` {sessionId} → `tool_call` {name, input} / `tool_result` {name, output}
    → `token` {text} … → `done` {same body as POST /chat}, or `error` {message}.
    If the client disconnects, the agent run is cancelled.
    """
    session_id = body.session_id or str(uuid4())
    yield ServerSentEvent(event="session", data={"sessionId": session_id})
    async for event in stream_turn(request.app.state.graph, body.message, session_id=session_id, metadata=_meta("sse")):
        yield ServerSentEvent(event=event.kind, data=_payload(event, session_id))


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(session_id: str, request: Request) -> Response:
    await request.app.state.graph.checkpointer.adelete_thread(session_id)
    return Response(status_code=204)


def _meta(surface: str) -> dict:
    return {"surface": surface}


def _response(session_id: str, result: TurnResult) -> ChatResponse:
    return ChatResponse(
        session_id=session_id,
        answer=result.answer,
        tools=[t.name for t in result.tool_calls],
        steps=result.steps,
        usage=result.usage,
    )


def _payload(event: TurnEvent, session_id: str) -> dict:
    match event:
        case DoneEvent(result=result):
            return _response(session_id, result).model_dump(by_alias=True)
        case ErrorEvent(error=error):
            log.error("[chat/stream] turn failed", exc_info=error)
            return {"message": FAILURE_MESSAGE}
        case _:
            return asdict(event)
