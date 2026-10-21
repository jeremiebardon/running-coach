import pytest
from langgraph.checkpoint.memory import InMemorySaver

from running_coach.agent.graph import build_graph
from running_coach.agent.runner import DoneEvent, TokenEvent, ToolCallEvent, ToolResultEvent, run_turn, stream_turn
from tests.fakes import FakeChatModel, reply, tool_call


def graph_with(responses, fixture_data, clock):
    model = FakeChatModel(responses=responses, calls=[])
    return model, build_graph(model, fixture_data, clock, InMemorySaver())


async def test_calls_predict_race_time_feeds_the_result_back_then_answers(fixture_data, clock):
    model, graph = graph_with(
        [
            tool_call("predict_race_time", {"distance": "marathon", "target_time": "2:55:00"}),
            reply("Borderline: current fitness predicts about 2:58."),
        ],
        fixture_data,
        clock,
    )
    turn = await run_turn(graph, "Could I run a sub 2:55 marathon?", session_id="test")

    assert [t.name for t in turn.tool_calls] == ["predict_race_time"]
    output = turn.tool_calls[0].output
    assert output["reference"]["label"] == "half"
    assert output["target"]["feasibility"]
    assert "2:58" in turn.answer
    assert turn.steps == 2
    # the system prompt carries today's date from the injected clock
    assert "2026-10-17" in model.calls[0][0].content
    # the tool result was fed back to the model on the 2nd call
    assert model.calls[1][-1].type == "tool"


async def test_streams_tool_activity_then_tokens_then_done(fixture_data, clock):
    _, graph = graph_with(
        [tool_call("get_activity_details", {"date": "2026-10-17"}), reply("Nice easy run with strides.")],
        fixture_data,
        clock,
    )
    events = [e async for e in stream_turn(graph, "How was my run today?", session_id="s")]
    kinds = [e.kind for e in events]

    assert kinds[:2] == ["tool_call", "tool_result"]
    assert kinds[-1] == "done"
    assert isinstance(events[0], ToolCallEvent) and events[0].name == "get_activity_details"
    assert isinstance(events[1], ToolResultEvent) and events[1].output["activity"]["work_intervals"]["count"] == 6
    tokens = "".join(e.text for e in events if isinstance(e, TokenEvent))
    done = events[-1]
    assert isinstance(done, DoneEvent) and done.result.answer == tokens == "Nice easy run with strides."


async def test_a_failed_turn_raises_and_leaves_no_trace_in_the_session(fixture_data, clock):
    model, graph = graph_with([RuntimeError("model down"), reply("Back online.")], fixture_data, clock)

    with pytest.raises(RuntimeError, match="model down"):
        await run_turn(graph, "Hello?", session_id="s")
    turn = await run_turn(graph, "Hello again", session_id="s")

    assert turn.answer == "Back online."
    # the retried call sees only the new question, not the failed one
    assert [m.content for m in model.calls[-1][1:]] == ["Hello again"]


async def test_a_failed_turn_mid_conversation_keeps_the_earlier_history(fixture_data, clock):
    model, graph = graph_with([reply("Hi!"), RuntimeError("model down"), reply("Still here.")], fixture_data, clock)

    await run_turn(graph, "First", session_id="s")
    with pytest.raises(RuntimeError):
        await run_turn(graph, "Broken", session_id="s")
    await run_turn(graph, "Third", session_id="s")

    assert [m.content for m in model.calls[-1][1:]] == ["First", "Hi!", "Third"]
