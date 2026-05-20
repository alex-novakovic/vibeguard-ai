import json
from typing import Literal
from langgraph.graph import StateGraph, END
from data.state import ProjectState
from agent.agent_session import AgentSession, AgentState, PHASE_GUARDIAN, PHASE_SCOPING
from interfaces import AgentFunctions
from agent.suggestion import suggest_next_task
from agent.agent_utils import classify_guardian_intent, generate_guardian_response
from agent.config import logger
from agent.start_feature import extract_feature_id_from_msg, start_feature
from agent.complete import handle_completion_flow, apply_completion_res
from agent.drift import handle_drift_flow, apply_drift_res



# ── 2. NODES ─────────────────────────────────────────────────────────────────
# Each node receives the full state, does work, returns updated state

async def scoping_node(state: AgentState) -> AgentState:
    """Handles one turn of the scoping conversation."""
    scoping = state["scoping"]
    response = await scoping.run_conversation_turn(state["user_message"])

    return {**state, "response": response, "phase": PHASE_SCOPING}


async def finish_scoping_node(state: AgentState) -> AgentState:
    """Called once when scoping is complete — parses vision doc."""
    scoping = state["scoping"]
    vision_doc = await scoping.scoping_session()

    project_state = ProjectState(
        vision_doc=vision_doc,
        feature_log=[]
    )

    state["logger"].log_llm_call(
        function_name="scoping_session",
        prompt=state["scoping"].chat_messages,
        response=json.dumps(vision_doc.model_dump()),
        tokens=scoping.total_tokens,
        user_id=state["user_id"]
    )

    project_state.current_cycle_tokens = scoping.total_tokens                    # reset for guardian cycle
    clean_response = state["response"].replace("SCOPING_COMPLETE", "").strip()
    clean_response += "\n\n✅ Scoping complete! Your vision doc has been saved. Want to move to the first task?"

    return {
        **state,
        "phase": PHASE_GUARDIAN,
        "project_state": project_state,
        "response": clean_response,
        "scoping": None,
        "just_completed_scoping": True
    }


async def guardian_node(state: AgentState) -> AgentState:
    """Handles messages during guardian phase."""
    project_state = state["project_state"]
    user_msg = state["user_message"]

    skill_tokens = 0
    skill_output = ""
    tokens_accounted = False 

    current_completion_status = state.get("completion_status", "IDLE")
    current_drift_status      = state.get("drift_status", "IDLE")
    
    # 1. ADD USER MESSAGE TO HISTORY IMMEDIATELY
    if "messages" not in state or state["messages"] is None:
        state["messages"] = []
    state["messages"].append({"role": "user", "content": user_msg})
    
    active_feature_id = next((fid for fid, f in project_state.feature_log["features"].items() if f["status"] == "in_progress"), None)

    last_assistant_msg = next((m["content"] for m in reversed(state["messages"]) if m["role"] == "assistant"), None)

    if state.get("just_completed_scoping"):
        res = await suggest_next_task(project_state)
        skill_output = f"INITIAL_SUGGESTION: {res['feature_name']} because {res['reason']}"
        skill_tokens += res.get("tokens", 0)
        state["just_completed_scoping"] = False
    elif current_completion_status == "COLLECTING":                      
        completion_res = await handle_completion_flow(state, user_msg, project_state)
        skill_output, skill_tokens, state, tokens_accounted = apply_completion_res(completion_res, state, project_state, skill_tokens)
    elif current_drift_status == "COLLECTING":                      
        drift_res = await handle_drift_flow(state, user_msg, project_state)
        skill_output, skill_tokens, state = apply_drift_res(drift_res, state, project_state)
    else:
        res = await classify_guardian_intent(user_msg, active_feature_id=active_feature_id, last_assistant_msg=last_assistant_msg,is_returning=state.get("is_returning", False))
        intent = res["prediction"]
        skill_tokens += res["tokens"]

        match intent:
            case "SUGGEST":
                res = await suggest_next_task(project_state)
                skill_output = f"SUGGESTION: {res['feature_name']} - {res['reason']}"
                skill_tokens += res.get("tokens", 0)

            case "START":
                res = await extract_feature_id_from_msg(user_msg, project_state.feature_log, state["messages"][-10:])
                skill_tokens += res.get("tokens", 0)
                action_result = await start_feature(project_state, res["feature_id"])
                match action_result["flag"]:
                    case "RESUMING":
                        skill_output = f"ACTION: Resuming {res['feature_id']} - picking up where we left off."
                    case "ERROR":
                        skill_output = f"CHAT: Could not start feature — {action_result['message']}"
                    case "START":
                        skill_output = f"ACTION: Feature {res['feature_id']} marked as started. Monitoring mode ON."

            case "COMPLETE":  # just the first message on completion, if the message explains enough, great, if not, current_completion_status == "COLLECTING"
                # First message claiming completion — enter the flow
                completion_res = await handle_completion_flow(state, user_msg, project_state)
                skill_output, skill_tokens, state, tokens_accounted = apply_completion_res(completion_res, state, project_state, skill_tokens)
            case "CHAT":
                if active_feature_id:
                    feature_name = project_state.feature_log["features"][active_feature_id]["name"]
                    project_state.previous_feature_id = active_feature_id
                    skill_output = f"CHAT: User is asking a general question. Remind them they are currently working on {active_feature_id} - {feature_name} and steer back to it."
                else:
                    skill_output = "CHAT: No specific skill triggered."

            case _:
                skill_output = "CHAT: Unrecognized intent."
    
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
    if not tokens_accounted:
        state.feature_tokens += skill_tokens
    
    state["messages"].append({"role": "assistant", "content": final_response})

    return {**state, "response": final_response, "messages": state["messages"],"project_state": project_state}


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
            "guardian": "guardian"
        }
    )

    # after scoping node — check if complete
    graph.add_conditional_edges(
        "scoping",
        route_after_scoping,
        {
            "finish_scoping": "finish_scoping",
            "end": END
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
            return "Please type a message to get started.", session

        # Setup baseline state values or fetch ongoing sub-flow parameter configurations
        initial_completion_status = getattr(session, "completion_status", "IDLE")
        initial_completion_context = getattr(session, "completion_context", {"collected_info": [], "attempts": 0})
        initial_drift_status = getattr(session, "drift_status", "IDLE")
        initial_drift_context = getattr(session, "drift_context", {"collected_info": [], "attempts": 0})

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
            "logger":logger,
            "is_returning": session.is_returning,
            "completion_status": initial_completion_status,
            "completion_context": initial_completion_context,
            "alignment_note":session.alignment_note,
            "drift_status" : initial_drift_status,
            "drift_context" : initial_drift_context,
            "drift_note":session.drift_note,
            "feature_tokens":session.feature_tokens
          }

        # run the graph
        result = await agent_graph.ainvoke(input_state)

        # sync updated state back to session
        session.phase = result["phase"]
        session.project_state = result["project_state"]
        session.just_completed_scoping = result["just_completed_scoping"]
        session.scoping = result["scoping"]
        session.messages = result["messages"]
        session.is_returning = False

        # Save our new sub-flow tracker states into memory context
        session.completion_status = result["completion_status"]
        session.completion_context = result["completion_context"]
        session.alignment_note = result["alignment_note"]

        session.drift_status  = result["drift_status"]
        session.drift_context = result["drift_context"]
        session.drift_note    = result["drift_note"]

        return result["response"], session