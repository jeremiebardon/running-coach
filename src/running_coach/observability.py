"""Observability: traces go to Phoenix, metrics to Prometheus — two separate pipelines.

## Traces (Phoenix)

- `register()` from phoenix.otel installs a tracer provider that exports
  OpenInference spans to Phoenix over OTLP.
- `LangChainInstrumentor` makes every graph node, LLM call and tool call emit a
  span — no tracing code in the agent itself (the runner only adds the root
  `coach.turn` span carrying the session id).

## Metrics (Prometheus, pull: GET /metrics)

Instruments are created from OpenTelemetry's global meter, which is a no-op until
`init_metrics()` installs a MeterProvider — so the runner can record unconditionally
(CLI, evals and tests pay nothing) and only the API server exposes them.

Exposed (Prometheus names):
  coach_turn_duration_seconds{surface,outcome}   histogram — one per conversational turn
  coach_tokens_total{type=input|output}          counter   — LLM tokens consumed
  coach_tool_calls_total{tool}                   counter   — tool calls the model made
  coach_turn_steps                               histogram — model calls per turn
  http_server_*                                  FastAPI's own request metrics (duration, active requests)
"""

import logging
import warnings

from opentelemetry import metrics
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.view import ExplicitBucketHistogramAggregation, View
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider

from running_coach.settings import get_settings

log = logging.getLogger(__name__)

# --- traces ---

# Spans that carry no information. Only LEAF spans may be listed here: dropping a span
# that has children would orphan them in Phoenix's trace tree.
NOISE_SPANS = frozenset({"tools_condition"})  # LangGraph's routing function between agent/tools
_provider: TracerProvider | None = None


def init_telemetry(project_name: str | None = None) -> None:
    global _provider
    settings = get_settings()
    if not settings.phoenix_collector_endpoint:
        log.warning("[telemetry] PHOENIX_COLLECTOR_ENDPOINT not set — traces disabled.")
        return

    from langchain_core._api import LangChainDeprecationWarning
    from openinference.instrumentation.langchain import LangChainInstrumentor
    from phoenix.otel import BatchSpanProcessor, register

    # openinference-instrumentation-langchain still calls message.text() as a method
    warnings.filterwarnings("ignore", message=r"Calling \.text\(\) as a method", category=LangChainDeprecationWarning)

    endpoint = f"{settings.phoenix_collector_endpoint.rstrip('/')}/v1/traces"
    _provider = register(
        project_name=project_name or settings.phoenix_project,
        endpoint=endpoint,
        batch=True,
        verbose=False,
    )

    class QuietBatchSpanProcessor(BatchSpanProcessor):
        def on_end(self, span) -> None:
            if span.name not in NOISE_SPANS:
                super().on_end(span)

    # same export settings as register(batch=True), plus the filter above
    _provider._set_default_processor(QuietBatchSpanProcessor(endpoint=endpoint))
    LangChainInstrumentor().instrument(tracer_provider=_provider)


def shutdown_telemetry() -> None:
    """Flush batched spans before exit."""
    if _provider is not None:
        _provider.shutdown()


# --- metrics ---

meter = metrics.get_meter("running-coach")

turn_duration = meter.create_histogram(
    "coach.turn.duration", unit="s", description="Duration of one conversational turn (model + tools)"
)
turn_steps = meter.create_histogram("coach.turn.steps", unit="{step}", description="Model calls per turn")
tokens = meter.create_counter("coach.tokens", unit="{token}", description="LLM tokens consumed")
tool_calls = meter.create_counter("coach.tool_calls", unit="{call}", description="Tool calls requested by the model")

# Local models take tens of seconds per turn; the default buckets (≤10 s) would put everything in +Inf.
_TURN_SECONDS = [1, 2.5, 5, 10, 20, 30, 45, 60, 90, 120, 180, 300]
_initialised = False


def init_metrics() -> None:
    """Install the MeterProvider once per process (idempotent: safe to call from create_app in tests)."""
    global _initialised
    if _initialised:
        return
    provider = MeterProvider(
        resource=Resource.create({"service.name": "running-coach"}),
        metric_readers=[PrometheusMetricReader()],  # registers in prometheus_client's default registry
        views=[
            View(instrument_name="coach.turn.duration", aggregation=ExplicitBucketHistogramAggregation(_TURN_SECONDS))
        ],
    )
    metrics.set_meter_provider(provider)
    _initialised = True
