import json

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver

from running_coach.agent.graph import build_graph
from running_coach.api.app import create_app
from tests.fakes import FakeChatModel, reply, tool_call


@pytest.fixture
def make_client(fixture_data, clock):
    def make(*responses) -> tuple[TestClient, FakeChatModel]:
        model = FakeChatModel(responses=list(responses), calls=[])
        graph = build_graph(model, fixture_data, clock, InMemorySaver())
        return TestClient(create_app(graph, "fixtures")), model

    return make


def parse_sse(body: str) -> list[tuple[str, dict]]:
    events = []
    for block in body.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines() if not line.startswith(":"))
        if "event" in fields:
            events.append((fields["event"], json.loads(fields["data"])))
    return events


def test_health(make_client):
    client, _ = make_client()
    assert client.get("/health").json() == {"status": "ok", "dataSource": "fixtures"}


def test_rejects_an_invalid_body(make_client):
    client, _ = make_client()
    assert client.post("/chat", json={"nope": True}).status_code == 400
    assert client.post("/chat", json={"message": "   "}).status_code == 400


def test_keeps_conversation_history_per_session(make_client):
    client, model = make_client(reply("First answer"), reply("Second answer"))

    first = client.post("/chat", json={"message": "Hi coach"}).json()
    assert first["answer"] == "First answer"
    assert first["usage"] == {"inputTokens": 10, "outputTokens": 5}

    second = client.post("/chat", json={"message": "And now?", "sessionId": first["sessionId"]}).json()
    assert second["answer"] == "Second answer"

    # the 2nd model call received the whole conversation (user, assistant, user)
    assert [m.content for m in model.calls[1][1:]] == ["Hi coach", "First answer", "And now?"]


def test_returns_502_when_the_agent_fails(make_client):
    client, _ = make_client(RuntimeError("boom"))
    res = client.post("/chat", json={"message": "Hi"})
    assert res.status_code == 502
    assert "sessionId" in res.json()


def test_delete_session_forgets_the_conversation(make_client):
    client, model = make_client(reply("One"), reply("Two"))
    sid = client.post("/chat", json={"message": "Hi"}).json()["sessionId"]
    assert client.delete(f"/sessions/{sid}").status_code == 204
    client.post("/chat", json={"message": "Fresh start", "sessionId": sid})
    assert [m.content for m in model.calls[1][1:]] == ["Fresh start"]


def test_streams_a_turn_as_server_sent_events(make_client):
    client, _ = make_client(
        tool_call("get_activity_details", {"date": "2026-10-17"}), reply("Nice easy run with strides.")
    )
    with client.stream("POST", "/chat/stream", json={"message": "How was my run today?"}) as res:
        assert res.headers["content-type"].startswith("text/event-stream")
        events = parse_sse(res.read().decode())

    kinds = [kind for kind, _ in events]
    assert kinds[:3] == ["session", "tool_call", "tool_result"]
    assert kinds[-1] == "done"
    assert set(kinds[3:-1]) == {"token"}

    tokens = "".join(data["text"] for kind, data in events if kind == "token")
    done = events[-1][1]
    assert done["answer"] == tokens == "Nice easy run with strides."
    assert done["tools"] == ["get_activity_details"]
    assert done["sessionId"] == events[0][1]["sessionId"]
    assert events[2][1]["output"]["activity"]["work_intervals"]["count"] == 6


def test_streamed_turns_share_history_with_json_turns(make_client):
    client, model = make_client(reply("Streamed hello"), reply("JSON follow-up"))
    with client.stream("POST", "/chat/stream", json={"message": "Hi"}) as res:
        sid = parse_sse(res.read().decode())[0][1]["sessionId"]
    client.post("/chat", json={"message": "Again", "sessionId": sid})
    assert [m.content for m in model.calls[1][1:]] == ["Hi", "Streamed hello", "Again"]


def test_stream_reports_failures_as_an_error_event(make_client):
    client, _ = make_client(RuntimeError("boom"))
    with client.stream("POST", "/chat/stream", json={"message": "Hi"}) as res:
        events = parse_sse(res.read().decode())
    assert [kind for kind, _ in events] == ["session", "error"]
    assert "boom" not in events[1][1]["message"]  # internals stay in the logs


def samples(client, name: str, **labels: str) -> list[float]:
    """Values of the Prometheus samples called `name` whose labels include `labels`."""
    out = []
    for line in client.get("/metrics/").text.splitlines():
        is_sample = line.startswith(name + "{") or line.startswith(name + " ")
        if is_sample and all(f'{k}="{v}"' in line for k, v in labels.items()):
            out.append(float(line.rsplit(" ", 1)[1]))
    return out


def test_exposes_prometheus_metrics_for_turns_tokens_and_tools(make_client):
    client, _ = make_client(tool_call("get_activity_details", {"date": "2026-10-17"}), reply("Nice run."))
    before = sum(samples(client, "coach_tool_calls_total", tool="get_activity_details"))
    client.post("/chat", json={"message": "How was my run today?"})

    assert sum(samples(client, "coach_tool_calls_total", tool="get_activity_details")) == before + 1
    assert samples(client, "coach_turn_duration_seconds_count", outcome="ok", surface="http")
    assert samples(client, "coach_tokens_total", type="output")
    assert samples(client, "coach_turn_steps_count", surface="http")


def test_counts_failed_turns_with_an_error_outcome(make_client):
    client, _ = make_client(RuntimeError("boom"))
    before = sum(samples(client, "coach_turn_duration_seconds_count", outcome="error"))
    client.post("/chat", json={"message": "Hi"})
    assert sum(samples(client, "coach_turn_duration_seconds_count", outcome="error")) == before + 1


def test_exposes_fastapi_http_metrics(make_client):
    client, _ = make_client()
    client.get("/health")
    assert samples(client, "http_server_request_duration_seconds_count", http_route="/health")
