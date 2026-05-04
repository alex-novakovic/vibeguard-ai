import json
import uuid
from typing import TypedDict, Literal
from langgraph.graph import StateGraph, END
from agent.scoping import ScopingSession
from data.state import ProjectState
from data.logger import log_llm_call
from data.storage import initialize_feature_log
PHASE_SCOPING = "scoping"
PHASE_GUARDIAN = "guardian"


# ── 1. STATE ─────────────────────────────────────────────────────────────────
# This is what flows through the graph — replaces agent_state dict
class AgentState(TypedDict):
    session_id: str
    phase: str
    user_message: str
    response: str
    scoping: ScopingSession
    project_state: ProjectState | None


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
        session_id=state["session_id"],
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

    log_llm_call(
        function_name="scoping_session",
        prompt="Full scoping conversation",
        response=json.dumps(vision_doc),
        tokens=scoping.total_tokens,
        session_id=state["session_id"],
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

def _detect_scoping_complete(response: str) -> bool:
    last_line = response.strip().split("\n")[-1].strip().upper()
    return last_line == "SCOPING_COMPLETE"

def route_after_scoping(state: AgentState) -> Literal["finish_scoping", "end"]:
    """After scoping node runs — did the model signal completion?"""
    if _detect_scoping_complete(state["response"]):
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


# ── 5. AgentSession — now just holds session-level state ─────────────────────

class AgentSession:
    """
    Holds per-user state that persists between graph runs.
    The graph itself is stateless — AgentSession carries state across turns.
    """
    def __init__(self):
        self.session_id: str = str(uuid.uuid4())
        self.phase: str = PHASE_SCOPING
        self.scoping: ScopingSession = ScopingSession()
        self.project_state: ProjectState | None = None


    def _detect_scoping_complete(self, response: str) -> bool:
        last_line = response.strip().split("\n")[-1].strip().upper()
        return last_line == "SCOPING_COMPLETE"

    async def _finish_scoping(self):
        vision_doc = await self.scoping.scoping_session()

        initialize_feature_log(vision_doc.model_dump())

        self.phase = PHASE_GUARDIAN
        self.project_state = ProjectState(
            vision_doc=vision_doc,
            feature_log={}, ##adjusted to pydantic
        )
        self.project_state.current_cycle_tokens = self.scoping.total_tokens

        log_llm_call(
            function_name="scoping_session",
            prompt="Full scoping conversation",
            response=json.dumps(vision_doc.model_dump()), #adjusted to pydantic
            tokens=self.scoping.total_tokens,
            session_id=self.session_id,
        )

    async def _handle_scoping_phase(self, user_message: str) -> str:
        response = await self.scoping.run_conversation_turn(user_message)
        
        # If we want to log each turn with tokens
        '''
        log_llm_call(
            function_name="run_conversation_turn",
            prompt=user_message,
            response=response,
            tokens=self.scoping.last_turn_tokens,
            session_id=self.session_id,
        )
        '''

        if self._detect_scoping_complete(response):
            await self._finish_scoping()
            clean_response = response.replace("SCOPING_COMPLETE", "").strip()
            return clean_response + "\n\n✅ Scoping complete! Your vision doc has been saved."

        return response

    async def _handle_guardian_phase(self, user_message: str) -> str:
        # TODO: wire in suggest_next_task() and monitor_for_drift()
        project_name = self.project_state.vision_doc.projectName #adjusted to pydantic
        return f"[Guardian mode active] Working on: {project_name}. Guardian features coming soon."

# ── 6. run_agent — same signature as before ───────────────────────────────────

async def run_agent(user_message: str, status: str, project_state: ProjectState, session: AgentSession) -> str:
    """
    Main entry point — same signature as before.
    Now runs the LangGraph instead of if/elif routing.
    """
    if not user_message or not user_message.strip():
        return "Please type a message to get started."

    # build input state for this turn
    input_state: AgentState = {
        "session_id": session.session_id,
        "phase": session.phase,
        "user_message": user_message,
        "response": "",
        "scoping": session.scoping,
        "project_state": session.project_state if status == "existing" else None,
    }

    # run the graph
    result = await agent_graph.ainvoke(input_state)

    # sync updated state back to session
    session.phase = result["phase"]
    session.project_state = result["project_state"]

    return result["response"]