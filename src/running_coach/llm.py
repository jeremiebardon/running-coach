"""Chat-model provider adapter.

Models are named "provider:model" (e.g. "ollama:qwen3:14b",
"anthropic:claude-sonnet-5-5"), so switching provider is a config change.
Add a provider here (OpenAI, Bedrock, vLLM…) and nothing else in the app moves:
the agent only sees LangChain's `BaseChatModel` interface.
"""

from langchain_core.language_models import BaseChatModel

from running_coach.settings import Settings, get_settings


def build_model(spec: str, settings: Settings | None = None) -> BaseChatModel:
    settings = settings or get_settings()
    provider, sep, name = spec.partition(":")
    if not sep or not name:
        raise ValueError(f'Model must be "provider:model", got "{spec}"')

    match provider:
        case "ollama":
            from langchain_ollama import ChatOllama

            # reasoning=True keeps "thinking" models' (qwen3, deepseek-r1) <think> text
            # out of the answer: it goes to additional_kwargs["reasoning_content"].
            return ChatOllama(model=name, base_url=settings.ollama_base_url, reasoning=True)
        case "anthropic":
            from langchain_anthropic import ChatAnthropic

            # No temperature: recent Claude models reject non-default sampling params.
            return ChatAnthropic(model=name, max_tokens=16000)
        case _:
            raise ValueError(f'Unknown model provider "{provider}" (expected "ollama" or "anthropic")')
