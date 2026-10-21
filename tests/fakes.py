"""A scripted chat model: replays the given AIMessages in order and records the
prompts it received, so agent/API tests run offline and deterministically."""

import json
from collections.abc import Iterator, Sequence
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult


class FakeChatModel(BaseChatModel):
    responses: list[Any]  # AIMessage, or an Exception to raise
    calls: list[list[BaseMessage]] = []

    @property
    def _llm_type(self) -> str:
        return "fake"

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> "FakeChatModel":
        return self

    def _next(self, messages: list[BaseMessage]) -> AIMessage:
        self.calls.append(list(messages))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=self._next(messages))])

    def _stream(
        self, messages, stop=None, run_manager: CallbackManagerForLLMRun | None = None, **kwargs
    ) -> Iterator[ChatGenerationChunk]:
        # Stream text word by word (like a real model), tool calls in one final chunk.
        message = self._next(messages)
        words = message.text.split(" ") if message.text else []
        for i, word in enumerate(words):
            chunk = ChatGenerationChunk(message=AIMessageChunk(content=word if i == 0 else f" {word}"))
            if run_manager:
                run_manager.on_llm_new_token(chunk.text, chunk=chunk)
            yield chunk
        yield ChatGenerationChunk(
            message=AIMessageChunk(
                content="",
                tool_call_chunks=[
                    {"name": c["name"], "args": json.dumps(c["args"]), "id": c["id"], "index": i}
                    for i, c in enumerate(message.tool_calls)
                ],
                usage_metadata=message.usage_metadata,
            )
        )


def tool_call(name: str, args: dict, id: str = "call-1") -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": id}])


def reply(text: str) -> AIMessage:
    return AIMessage(content=text, usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15})
