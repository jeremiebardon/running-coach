"""Wire LangChain/LangGraph → OpenTelemetry → Phoenix.

- `register()` from phoenix.otel installs a tracer provider that exports
  OpenInference spans to Phoenix over OTLP.
- `LangChainInstrumentor` makes every graph node, LLM call and tool call emit a
  span — no tracing code in the agent itself (the runner only adds the root
  `coach.turn` span carrying the session id).
"""

import logging
import warnings

from opentelemetry.sdk.trace import TracerProvider

from running_coach.settings import get_settings

log = logging.getLogger(__name__)

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
