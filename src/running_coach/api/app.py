"""HTTP API: same agent as the CLI, different transport.

`create_app` takes its dependencies so tests can pass a graph built on a fake
model; `main` wires the real ones from settings.
"""

import argparse
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from langgraph.graph.state import CompiledStateGraph
from prometheus_client import make_asgi_app

from running_coach.api.routes import router
from running_coach.metrics import init_metrics
from running_coach.telemetry import shutdown_telemetry

origins = [
    "http://localhost.tiangolo.com",
    "https://localhost.tiangolo.com",
    "http://localhost",
    "http://localhost:8080",
]


def create_app(graph: CompiledStateGraph, data_source: str) -> FastAPI:
    if graph.checkpointer is None:
        raise ValueError("The API needs a graph compiled with a checkpointer (it holds the sessions).")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        shutdown_telemetry()  # flush spans on SIGTERM (`docker compose down`) / Ctrl+C

    init_metrics()
    # FastAPI 0.156 has built-in OpenTelemetry. Traces go to Phoenix, which only wants LLM data:
    # HTTP/operation spans (POST /chat, fastapi.endpoint, …) would be noise and would become the
    # root of every trace, burying `coach.turn`. HTTP *metrics* are useful, so they stay on and
    # flow to Prometheus through the global MeterProvider installed by init_metrics().
    app = FastAPI(
        title="Running coach",
        version="0.1.0",
        lifespan=lifespan,
        telemetry={"tracing": True, "operation_spans": True, "metrics": True, "logs": True},
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.graph = graph
    app.state.data_source = data_source
    app.include_router(router)
    app.mount("/metrics", make_asgi_app())  # Prometheus scrape target

    @app.exception_handler(RequestValidationError)
    async def bad_request(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse({"error": "Body must be { message: string, sessionId?: string }"}, status_code=400)

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the running coach over HTTP.")
    parser.add_argument("--fixtures", action="store_true", help="use the demo athlete instead of intervals.icu")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int)
    args = parser.parse_args()
    if args.fixtures:
        os.environ["DATA_SOURCE"] = "fixtures"

    import uvicorn
    from langgraph.checkpoint.memory import InMemorySaver

    from running_coach.agent.graph import build_graph
    from running_coach.data.factory import athlete_clock, build_data_source
    from running_coach.llm import build_model
    from running_coach.settings import get_settings
    from running_coach.telemetry import init_telemetry

    settings = get_settings()
    init_telemetry()
    clock = athlete_clock(settings)
    # In-memory sessions: fine for one container. For several replicas or restarts,
    # swap in a persistent checkpointer (langgraph-checkpoint-postgres / -sqlite).
    graph = build_graph(build_model(settings.coach_model), build_data_source(settings, clock), clock, InMemorySaver())
    uvicorn.run(create_app(graph, settings.data_source), host=args.host, port=args.port or settings.port)
