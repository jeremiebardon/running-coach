"""Metrics → Prometheus (pull: GET /metrics). Traces go to Phoenix; this is a separate pipeline.

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

from opentelemetry import metrics
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.view import ExplicitBucketHistogramAggregation, View
from opentelemetry.sdk.resources import Resource

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
