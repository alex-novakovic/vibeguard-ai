import os
import json
from datetime import datetime, timezone
from agent.scoping import run_conversation_turn, scoping_session
from data.state import ProjectState
from data.logger import log_llm_call

# phase constants
PHASE_SCOPING = "scoping"
PHASE_GUARDIAN = "guardian"

# agent state
agent_state = {
    "phase": PHASE_SCOPING,
    "conversation_history": [],  # used during scoping only
    "project_state": None,       # set after scoping completes
    "current_cycle_tokens":0             # track tokens used
}


def _detect_scoping_complete(response: str) -> bool:
    """
    Detects whether the agent has finished the scoping session.
    Looks for a signal phrase in the model's response.
    The CONVERSATION_PROMPT must instruct the model to say
    'SCOPING_COMPLETE' when all questions have been answered.
    """
    return "SCOPING_COMPLETE" in response.upper()


def _finish_scoping() -> str:
    """
    Called once when scoping is detected as complete.
    Parses conversation history into vision doc and saves it.
    """
    vision_doc = scoping_session()

    # update agent state
    # or maybe write this info into the ProjectState? and WHO will write it?
    # agent_state["project_state"].update_state(vision_doc, [], None, 0)
    agent_state["phase"] = PHASE_GUARDIAN
    agent_state["project_state"] = ProjectState(
        vision_doc=vision_doc,
        feature_log=[],
    )
    
    # set total tokens after creation
    agent_state["project_state"].current_cycle_tokens = agent_state["current_cycle_tokens"]

    # log the scoping API call
    # def log_llm_call(function_name: str, prompt: str, response: str, tokens: int):
    
    log_llm_call(
        function_name="scoping_session",
        prompt="Scoping conversation",
        response=json.dumps(vision_doc),
        tokens=agent_state["current_cycle_tokens"]
    )

    return vision_doc


def _handle_scoping_phase(user_message: str) -> str:
    """
    Handles a conversation turn during the scoping phase.
    Appends to history and checks for completion.
    """
    # get response from model
    response, current_cycle_tokens = run_conversation_turn(user_message)

    # store turn in conversation history
    agent_state["conversation_history"].append({"role": "user", "content": user_message})
    agent_state["conversation_history"].append({"role": "model", "content": response})
    agent_state["current_cycle_tokens"] += current_cycle_tokens if current_cycle_tokens else 0

    # check if scoping is done
    if _detect_scoping_complete(response):
        _finish_scoping()
        clean_response = response.replace("SCOPING_COMPLETE", "").strip()
        return clean_response + "\n\n✅ Scoping complete! Your vision doc has been saved."

    return response


def _handle_guardian_phase(user_message: str) -> str:
    """
    Handles messages during the guardian phase.
    Routes to suggest_next_task(), drift monitor, etc.
    Placeholder until those functions are implemented.
    """
    # TODO: wire in suggest_next_task() and monitor_for_drift()
    # when Member A builds those in the next task
    return (
        f"[Guardian mode active] I see you're working on: "
        f"{agent_state['project_state'].vision_doc.get('product_name', 'your project')}. "
        f"Guardian features coming soon."
    )


def run_agent(user_message: str, status: str, project_state: ProjectState) -> tuple[str,int]:
    """
    Main entry point. Member C calls this from Gradio.
    Routes user message to the correct phase handler.

    Args:
        user_message: raw string from the chat input

    Returns:
        Agent response string to display in chat
    """
    if not user_message or not user_message.strip():
        return "Please type a message to get started."

    if status == "new":
        agent_state["phase"] = PHASE_SCOPING
        return _handle_scoping_phase(user_message)

    elif status == "existing":
        agent_state["phase"] = PHASE_GUARDIAN
        agent_state["project_state"] = project_state  # already loaded, ready to use
        return _handle_guardian_phase(user_message)
    else:
        return "Unknown agent phase. Please restart the session."
    
    

    
