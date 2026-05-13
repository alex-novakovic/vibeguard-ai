import json
from typing import Dict, TypedDict, Literal, List
from langgraph.graph import StateGraph, END
from agent.scoping import ScopingSession
from data.state import ProjectState
from data.logger import Logger
from agent.agent_session import AgentSession, PHASE_GUARDIAN, PHASE_SCOPING
from interfaces import AgentFunctions
from agent.suggestion import suggest_next_task
from agent.agent_utils import classify_guardian_intent, generate_guardian_response
from agent.config import logger



# ── 1. STATE ─────────────────────────────────────────────────────────────────
# This is what flows through the graph — replaces agent_state dict
class AgentState(TypedDict):
    user_id: str
    phase: str
    user_message: str
    messages: List[Dict[str, str]]
    response: str
    scoping: ScopingSession
    project_state: ProjectState | None
    logger: Logger | None
    just_completed_scoping: bool


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
    clean_response += "\n\n✅ Scoping complete! Your vision doc has been saved. Want to move to the first task?"

    return {
        **state,
        "phase": PHASE_GUARDIAN,
        "project_state": project_state,
        "response": clean_response,
        "just_completed_scoping": True
    }


async def guardian_node(state: AgentState) -> AgentState:
    """Handles messages during guardian phase."""
    project_state = state["project_state"]
    user_msg = state["user_message"]

    # 1. ADD USER MESSAGE TO HISTORY IMMEDIATELY
    if "messages" not in state or state["messages"] is None:
        state["messages"] = []
    state["messages"].append({"role": "user", "content": user_msg})

    if state.get("just_completed_scoping"):
        res = await suggest_next_task(project_state)
        skill_output = f"INITIAL_SUGGESTION: {res['feature_name']} because {res['reason']}"
        # Add tokens from suggestion to the session's total
        # skill_tokens += res.get("tokens", 0)
        state["just_completed_scoping"] = False
    else:
        res = await classify_guardian_intent(user_msg)
        intent = res["prediction"]
        # Add tokens from intent classification to the session's total
        # skill_tokens += res["tokens"]
        if intent == "SUGGEST":
            res = await suggest_next_task(project_state)
            skill_output = f"SUGGESTION: {res['feature_name']} - {res['reason']}"
            # Add tokens from suggestion to the session's total
            # skill_tokens += res.get("tokens", 0)
    
    # 4. Generate Final Response with Context
    # We pass only the last 10 messages for token efficiency
    llm_res = await generate_guardian_response(
        project_state=project_state,  # change this to project context, because it is expensive this way
        user_msg=user_msg,
        skill_output=skill_output,
        history=state["messages"]  
    )

    final_response = llm_res["text"]
    # skill_tokens += llm_res.get("tokens", 0)
    # add the tokens to the projectstate for overall accounting
    # if project_state:
        # project_state.total_tokens += skill_tokens
    
    state["messages"].append({"role": "assistant", "content": final_response})

    return {**state, "response": final_response, "messages": state["messages"]}


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
            "messages": session.messages,  # pass the full conversation history
            "scoping": session.scoping,
            "project_state": session.project_state,
            "just_completed_scoping": session.just_completed_scoping,
            "logger":logger
        }

        # run the graph
        result = await agent_graph.ainvoke(input_state)

        # sync updated state back to session
        session.phase = result["phase"]
        session.project_state = result["project_state"]
        session.just_completed_scoping = result["just_completed_scoping"]
        session.messages = result["messages"]

        return result["response"], session
