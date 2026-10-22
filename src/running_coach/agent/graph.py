"""The coach as an explicit LangGraph StateGraph.

    START ─▶ agent ─(tool calls?)─▶ tools ─┐
               ▲  └─(no)─▶ END             │
               └───────────────────────────┘

`agent` asks the model what to do next; `tools` executes the requested tool
calls; the loop runs until the model answers without calling a tool. Growing
the agent = adding nodes/edges here (a planner, a router to sub-agents, a
human-approval step…).
"""

import asyncio

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from running_coach.agent.prompts import coach_instructions
from running_coach.agent.tools import make_tools
from running_coach.data.base import Clock, TrainingData


class CoachState(MessagesState):
    """Graph state: the conversation (`messages`, appended via the add_messages reducer).

    Add fields here as the agent grows — e.g. a training plan being drafted, a
    cached athlete profile, or a router decision for sub-agents.
    """


MAX_STEPS = 8
"""Max model calls per turn. Each step is 2 graph supersteps (agent + tools)."""
RECURSION_LIMIT = 2 * MAX_STEPS + 1


def build_graph(
    model: BaseChatModel,
    data: TrainingData,
    clock: Clock,
    checkpointer: BaseCheckpointSaver | None = None,
) -> CompiledStateGraph:
    tools = make_tools(data, clock)
    model_with_tools = model.bind_tools(tools)

    async def agent(state: CoachState) -> dict:
        # The system prompt is rebuilt on every call (it carries today's date) and
        # never stored in the state, so it doesn't pile up in the conversation.
        system = SystemMessage(coach_instructions(clock.today()))
        response = await model_with_tools.ainvoke([system, *state["messages"]])
        return {"messages": [response]}

    builder = StateGraph(CoachState)
    builder.add_node("agent", agent)
    builder.add_node("tools", ToolNode(tools))
    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", tools_condition)  # → "tools" or END
    builder.add_edge("tools", "agent")
    return builder.compile(checkpointer=checkpointer, name="running-coach")


async def make_graph() -> CompiledStateGraph:
    """Graph factory for `langgraph dev` (LangGraph Studio, see langgraph.json).

    Studio provides its own persistence, so no checkpointer here. Built in a worker
    thread: reading .env and fixture files would block the dev server's event loop.
    """
    return await asyncio.to_thread(_graph_from_settings)


def _graph_from_settings() -> CompiledStateGraph:
    from running_coach.agent.llm import build_model
    from running_coach.data import athlete_clock, build_data_source
    from running_coach.settings import get_settings

    settings = get_settings()
    clock = athlete_clock(settings)
    return build_graph(build_model(settings.coach_model), build_data_source(settings, clock), clock)
