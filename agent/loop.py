import json
import uuid
import logging
from typing import TypedDict, List, Dict, Literal
from langgraph.graph import StateGraph, END
from agent.scoping import ScopingSession
from data.state import ProjectState
from data.logger import Logger
from agent.suggestion import suggest_next_task
from agent.agent_utils import classify_guardian_intent, generate_guardian_response
from data.schemas import SessionEntry
from datetime import datetime
from data.storage import Storage

PHASE_SCOPING = "scoping"
PHASE_GUARDIAN = "guardian"

logger = logging.getLogger(__name__)


# ── 1. STATE ─────────────────────────────────────────────────────────────────
class AgentState(TypedDict):
    user_id: str
    phase: str
    user_message: str
    response: str
    messages: List[Dict[str, str]]
    scoping: ScopingSession
    project_state: ProjectState | None
    logger: Logger | None
    storage: Storage | None
    just_completed_scoping: bool
    current_session: SessionEntry | None



# ── 2. NODES ─────────────────────────────────────────────────────────────────

async def scoping_node(state: AgentState) -> AgentState:
    """Handles one turn of the scoping conversation."""
    scoping = state["scoping"]
    response = await scoping.run_conversation_turn(state["user_message"])
    return {**state, "response": response, "phase": PHASE_SCOPING}


async def finish_scoping_node(state: AgentState) -> AgentState:
    """Called once when scoping is complete — parses vision doc and saves it."""
    scoping = state["scoping"]
    vision_doc = await scoping.scoping_session()

    project_state = ProjectState(
        vision_doc=vision_doc,
        feature_log=[],
    )

    project_state.total_tokens = scoping.total_tokens

    # 2. Create the FIRST SessionEntry for the Guardian Phase
    # This officially starts the "Work Log"
    # new_session = state["storage"].start_session()

    state["logger"].log_llm_call(
        function_name="scoping_session",
        prompt="Full scoping conversation",
        response=json.dumps(vision_doc.model_dump()),
        tokens=scoping.total_tokens,
        user_id=state["user_id"],
    )

    clean_response = state["response"].replace("SCOPING_COMPLETE", "").strip()
    clean_response += "\n\n✅ Scoping complete! Your vision doc has been saved. Want to move to the first task?"
    
    final_messages = scoping.chat_messages.copy()
    final_messages.append({"role": "assistant", "content": clean_response})

    return {
        **state,
        "phase": PHASE_GUARDIAN,
        "project_state": project_state,
        "response": clean_response,
        "messages": final_messages,
        "just_completed_scoping": True,
    }


async def guardian_node(state: AgentState) -> AgentState:
    project_state = state["project_state"]
    user_msg = state["user_message"]
    session = state.get("current_session")

    if session is None:
        print("DEBUG: Session is missing from state!")
    
    # 1. Initialize & Update Active History
    if "messages" not in state or state["messages"] is None:
        state["messages"] = []
    state["messages"].append({"role": "user", "content": user_msg})

    # 2. Generate the "Eyes" of the AI
    # project_context = get_project_summary(project_state)
    
    # 3. Intent Routing & Skill Execution
    skill_tokens = 0
    skill_output = ""

    if state.get("just_completed_scoping"):
        res = await suggest_next_task(project_state)
        skill_output = f"INITIAL_SUGGESTION: {res['feature_name']} because {res['reason']}"
        # Add tokens from suggestion to the session's total
        skill_tokens += res.get("tokens", 0) # Grabs the new field!
        state["just_completed_scoping"] = False 
    else:
        res = await classify_guardian_intent(user_msg)
        intent = res["prediction"]
        # Add tokens from intent classification to the session's total
        skill_tokens += res["tokens"]
        if intent == "SUGGEST":
            res = await suggest_next_task(project_state)
            skill_output = f"SUGGESTION: {res['feature_name']} - {res['reason']}"
            # Add tokens from suggestion to the session's total
            skill_tokens += res.get("tokens", 0) # Grabs the new field!
        elif intent == "START":
            # Logic to update project_state.active_feature_id happens here
            skill_output = "ACTION: Feature marked as started. Monitoring mode ON."
            skill_tokens = 0
        elif intent == "COMPLETE":
            skill_output = "ACTION: Verifying completion against vision..."
            skill_tokens = 0
        else:
            skill_output = "CHAT: No specific skill triggered. (Drift detection active)"

    # 4. Generate Final Response with Context
    # We pass only the last 10 messages for token efficiency
    llm_res = await generate_guardian_response(
        project_state=project_state,  # change this to project context, because it is expensive this way
        user_msg=user_msg,
        skill_output=skill_output,
        history=state["messages"]  
    )

    final_response = llm_res["text"]
    skill_tokens += llm_res.get("tokens", 0)
    # add the tokens to the projectstate for overall accounting
    if project_state:
        project_state.total_tokens += skill_tokens
    
    state["messages"].append({"role": "assistant", "content": final_response})

    # 5. SYNC TO SESSION ENTRY (The Permanent Ledger)
    if session:
        # Accumulate Tokens for this turn into the SessionEntry's total
        session.totalTokensUsed += skill_tokens
        print(f"DEBUG: Total tokens used in this turn: {skill_tokens}, Total tokens in session now: {session.totalTokensUsed}")
        
        # Sync the entire message list
        # This overwrites the old session history with the updated board
        session.messages = state["messages"]
        print("DEBUG: Session messages updated. Total messages in session:", len(session.messages))

    return {**state, "response": final_response, "current_session": session}


# ── 3. EDGES ─────────────────────────────────────────────────────────────────

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

    graph.add_node("scoping", scoping_node)
    graph.add_node("finish_scoping", finish_scoping_node)
    graph.add_node("guardian", guardian_node)

    graph.set_conditional_entry_point(
        route_entry,
        {
            "scoping": "scoping",
            "guardian": "guardian",
        }
    )

    graph.add_conditional_edges(
        "scoping",
        route_after_scoping,
        {
            "finish_scoping": "finish_scoping",
            "end": END,
        }
    )

    graph.add_edge("finish_scoping", END)
    graph.add_edge("guardian", END)

    return graph.compile()


agent_graph = build_agent_graph()


# ── 5. AgentSession ───────────────────────────────────────────────────────────

class AgentSession:
    """
    Holds per-user state that persists between graph runs.
    The graph itself is stateless — AgentSession carries state across turns.
    """
    def __init__(self):
        self.user_id: str = str(uuid.uuid4())
        self.phase: str = PHASE_SCOPING
        self.scoping: ScopingSession = ScopingSession()
        self.project_state: ProjectState | None = None
        self.logger: Logger = Logger()
        self.storage: Storage = Storage()
        self.just_completed_scoping: bool = False
        # We don't create a SessionEntry until the Guardian phase starts
        self.current_session: SessionEntry | None = None


# ── 6. run_agent ──────────────────────────────────────────────────────────────

async def run_agent(user_message: str, status: str, session: AgentSession) -> str:
    """
    Main entry point. Member C calls this from Gradio.
    Builds input state from session, runs the graph, syncs result back to session.
    """
    if not user_message or not user_message.strip():
        return "Please type a message to get started."
    
    # 1. Safety check for active_messages
    active_messages = []
    if session.phase == PHASE_GUARDIAN:
        # If the session exists, grab messages. 
        # If it doesn't exist yet (first turn of Guardian), keep it empty.
        if session.current_session:
            active_messages = session.current_session.messages

    input_state: AgentState = {
        "user_id": session.user_id,
        "phase": PHASE_SCOPING if status == "new" else PHASE_GUARDIAN,
        "user_message": user_message,
        "messages": active_messages,
        "response": "",
        "scoping": session.scoping,
        "project_state": session.project_state,
        "storage": session.storage,
        "logger": session.logger,
        "just_completed_scoping": session.just_completed_scoping,
        "current_session": session.current_session # only tracked during Guardian phase
    }

    result = await agent_graph.ainvoke(input_state)

    # sync updated state back to session
    session.phase = result["phase"]
    session.project_state = result["project_state"]
    session.response = result["response"]
    session.just_completed_scoping = result["just_completed_scoping"]

    # Only sync messages if we are in Guardian mode
    if session.phase == PHASE_GUARDIAN and result.get("current_session"):
        session.current_session = result["current_session"]

    return session
