import json
import os
import uuid
from typing import TypedDict, Literal
from langgraph.graph import StateGraph, END
from openai import OpenAI
from agent.scoping import ScopingSession
from data.state import ProjectState
from data.logger import Logger
from agent.suggestion import suggest_next_task
from agent.agent_utils import classify_guardian_intent, generate_guardian_response

PHASE_SCOPING = "scoping"
PHASE_GUARDIAN = "guardian"

client = OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1"
)

CONVERSATION_MODEL = os.getenv("CONVERSATION_MODEL", "google/gemini-2.0-flash-lite-001")


# ── 1. STATE ─────────────────────────────────────────────────────────────────
class AgentState(TypedDict):
    session_id: str
    phase: str
    user_message: str
    response: str
    scoping: ScopingSession
    project_state: ProjectState | None
    logger: Logger | None
    just_completed_scoping: bool


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

    #storage = Storage()
    #storage.initialize_feature_log(vision_doc)

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
        session_id=state["session_id"],
    )

    clean_response = state["response"].replace("SCOPING_COMPLETE", "").strip()
    clean_response += "\n\n✅ Scoping complete! Your vision doc has been saved. Want to move to the first task?"

    return {
        **state,
        "phase": PHASE_GUARDIAN,
        "project_state": project_state,
        "response": clean_response,
        "just_completed_scoping": True,
    }


async def guardian_node(state: AgentState) -> AgentState:
    project_state = state["project_state"]
    user_msg = state["user_message"]
    
    # --- STEP 1: INITIAL STATE TRIGGER (Transition from Scoping) ---
    if state.get("just_completed_scoping"):
        res = await suggest_next_task(project_state)
        skill_output = f"INITIAL_SUGGESTION: {res['feature_name']} because {res['reason']}"
        state["just_completed_scoping"] = False 
    
    else:
        # --- STEP 2: INTENT ROUTING ---
        intent = await classify_guardian_intent(user_msg)
        
        if intent == "SUGGEST":
            # SKILL: SUGGESTION ENGINE
            # Logic: Analyzes feature log + vision to find the next priority.
            res = await suggest_next_task(project_state)
            skill_output = f"SUGGESTION: {res['feature_name']} - {res['reason']}"

        elif intent == "START":
            # SKILL: START_FEATURE
            # Logic: Updates project_state.active_feature_id. 
            # This 'locks' the developer into a specific goal.
            # result = await start_feature_logic(project_state, user_msg)
            skill_output = "ACTION: Feature marked as started. Monitoring mode ON."

        elif intent == "COMPLETE":
            # SKILL: VISION_ALIGNMENT_CHECK
            # Logic: The 'Judge'. Compares user's work vs. Success Criteria.
            # If PASS: Mark feature as complete in feature_log.
            # If FAIL: Explain what is missing.
            # result = await vision_alignment_check(project_state, user_msg)
            skill_output = "ACTION: Verifying completion against vision..."

        else:
            # SKILL: MONITOR_FOR_DRIFT (Passive Skill)
            # Logic: This runs during 'CHAT'. It checks if the user is 
            # talking about features NOT in the vision doc (Scope Creep).
            # drift_report = await monitor_for_drift(project_state, user_msg)
            skill_output = "CHAT: No specific skill triggered. (Drift detection active)"

    # --- STEP 3: CONVERSATION WRAPPER ---
    final_response = await generate_guardian_response(
        project_state=project_state,
        user_msg=user_msg,
        skill_output=skill_output
    )

    return {**state, "response": final_response}


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
        self.session_id: str = str(uuid.uuid4())
        self.phase: str = PHASE_SCOPING
        self.scoping: ScopingSession = ScopingSession()
        self.project_state: ProjectState | None = None
        self.logger: Logger = Logger()
        self.just_completed_scoping: bool = False


# ── 6. run_agent ──────────────────────────────────────────────────────────────

async def run_agent(user_message: str, status: str, project_state: ProjectState, session: AgentSession) -> str:
    """
    Main entry point. Member C calls this from Gradio.
    Builds input state from session, runs the graph, syncs result back to session.
    """
    if not user_message or not user_message.strip():
        return "Please type a message to get started."

    input_state: AgentState = {
        "session_id": session.session_id,
        "phase": PHASE_SCOPING if status == "new" else PHASE_GUARDIAN,
        "user_message": user_message,
        "response": "",
        "scoping": session.scoping,
        "project_state": project_state if status == "existing" else session.project_state,
        "logger": session.logger,
        "just_completed_scoping": session.just_completed_scoping,
    }

    result = await agent_graph.ainvoke(input_state)

    # sync updated state back to session
    session.phase = result["phase"]
    session.project_state = result["project_state"]
    session.just_completed_scoping = result["just_completed_scoping"]

    return {
        "response": result["response"],
        "project_state": result["project_state"],
        "phase": result["phase"]
    }