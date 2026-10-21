from langgraph.graph import MessagesState


class CoachState(MessagesState):
    """Graph state: the conversation (`messages`, appended via the add_messages reducer).

    Add fields here as the agent grows — e.g. a training plan being drafted, a
    cached athlete profile, or a router decision for sub-agents.
    """
