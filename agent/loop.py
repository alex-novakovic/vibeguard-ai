import json
from typing import TypedDict, Literal
from langgraph.graph import StateGraph, END
from agent.scoping import ScopingSession
from data.state import ProjectState
from data.logger import Logger
from agent.agent_session import AgentSession, PHASE_GUARDIAN, PHASE_SCOPING
from interfaces import AgentFunctions



# ── 1. STATE ─────────────────────────────────────────────────────────────────
# This is what flows through the graph — replaces agent_state dict
class AgentState(TypedDict):
    user_id: str
    phase: str
    user_message: str
    response: str
    scoping: ScopingSession
    project_state: ProjectState | None
    logger: Logger | None


# ── 2. NODES ─────────────────────────────────────────────────────────────────
# Each node receives the full state, does work, returns updated state

async def scoping_node(state: AgentState) -> AgentState:
    """Handles one turn of the scoping conversation."""
    scoping = state["scoping"]
    response = await scoping.run_conversation_turn(state["user_message"])

    '''
    log_llm_call(
        function_name="run_conversation_turn",
        prompt=state["user_message"],
        response=response,
        tokens=scoping.total_tokens,
        user_id=state["user_id"],
    )
    '''

    return {**state, "response": response, "phase": PHASE_SCOPING}


async def finish_scoping_node(state: AgentState) -> AgentState:
    """Called once when scoping is complete — parses vision doc."""
    scoping = state["scoping"]
    vision_doc = await scoping.scoping_session()

    project_state = ProjectState(
        vision_doc=vision_doc,
        feature_log=[],
    )
    project_state.current_cycle_tokens = scoping.total_tokens

    state["logger"].log_llm_call(
        function_name="scoping_session",
        prompt="Full scoping conversation",
        response=json.dumps(vision_doc.model_dump()),
        tokens=scoping.total_tokens,
        user_id=state["user_id"],
    )

    clean_response = state["response"].replace("SCOPING_COMPLETE", "").strip()
    clean_response += "\n\n✅ Scoping complete! Your vision doc has been saved."

    return {
        **state,
        "phase": PHASE_GUARDIAN,
        "project_state": project_state,
        "response": clean_response,
    }


async def guardian_node(state: AgentState) -> AgentState:
    """Handles messages during guardian phase."""
    # TODO: wire in suggest_next_task() and monitor_for_drift()
    project_name = state["project_state"].vision_doc.get("projectName", "your project")
    response = f"[Guardian mode active] Working on: {project_name}. Guardian features coming soon."
    return {**state, "response": response}


# ── 3. EDGES ─────────────────────────────────────────────────────────────────
# Conditions that decide which node runs next

def detect_scoping_complete(response: str) -> bool:
    last_line = response.strip().split("\n")[-1].strip().upper()
    return last_line == "SCOPING_COMPLETE"

def route_after_scoping(state: AgentState) -> Literal["finish_scoping", "end"]:
    """After scoping node runs — did the model signal completion?"""
    if detect_scoping_complete(state["response"]):
        return "finish_scoping"
    return "end"

def route_entry(state: AgentState) -> Literal["scoping", "guardian"]:
    """Entry point — which phase are we in?"""
    return state["phase"]


# ── 4. BUILD THE GRAPH ────────────────────────────────────────────────────────

def build_agent_graph():
    graph = StateGraph(AgentState)

    # add nodes
    graph.add_node("scoping", scoping_node)
    graph.add_node("finish_scoping", finish_scoping_node)
    graph.add_node("guardian", guardian_node)

    # entry point — routes to scoping or guardian based on phase
    graph.set_conditional_entry_point(
        route_entry,
        {
            "scoping": "scoping",
            "guardian": "guardian",
        }
    )

    # after scoping node — check if complete
    graph.add_conditional_edges(
        "scoping",
        route_after_scoping,
        {
            "finish_scoping": "finish_scoping",
            "end": END,
        }
    )

    # finish_scoping and guardian always end
    graph.add_edge("finish_scoping", END)
    graph.add_edge("guardian", END)

    return graph.compile()


# compile once at module level
agent_graph = build_agent_graph()


# ── 5. run_agent — same signature as before ───────────────────────────────────
class Agent(AgentFunctions):
    async def run_agent(self, user_message: str, status: str, session: AgentSession) -> tuple:
        """
        Main entry point — same signature as before.
        Now runs the LangGraph instead of if/elif routing.
        """
        if not user_message or not user_message.strip():
            return "Please type a message to get started."

        # build input state for this turn
        input_state: AgentState = {
            "user_id": session.user_id,
            "phase": session.phase,
            "user_message": user_message,
            "response": "",
            "scoping": session.scoping,
            "project_state": session.project_state,
            "logger": session.logger
        }

        # run the graph
        result = await agent_graph.ainvoke(input_state)

        # sync updated state back to session
        session.phase = result["phase"]
        session.project_state = result["project_state"]

        return result["response"], session
