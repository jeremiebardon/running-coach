"""HTTP contract (camelCase on the wire, snake_case in Python)."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from pydantic.alias_generators import to_camel


class _Camel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ChatRequest(_Camel):
    message: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
    session_id: Annotated[str, StringConstraints(min_length=1, max_length=100)] | None = Field(
        None, description="Send back the sessionId from a previous answer to continue the conversation."
    )


class Usage(_Camel):
    input_tokens: int
    output_tokens: int


class ChatResponse(_Camel):
    session_id: str
    answer: str
    tools: list[str] = Field(description="Tools the coach called this turn, in order.")
    steps: int = Field(description="Model calls this turn.")
    usage: Usage


class Health(_Camel):
    status: str
    data_source: str
