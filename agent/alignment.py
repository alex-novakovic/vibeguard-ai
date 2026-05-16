import json
import logging 
from agent.config import CONVERSATION_MODEL, client
from agent.prompts.alignment_prompt import ALIGNMENT_PROMPT
from data.schemas import  VisionDoc
from data.state import ProjectState
from agent.agent_session import AgentState

logger = logging.getLogger(__name__)

async def vision_alignment_check(
    planned_feature: str, 
    actual_work: str, 
    vision_context: str
) -> dict:
    """
    Evaluates if the developer's work matches the vision.
    Returns a dict: {"is_aligned": bool, "feedback": str, "tokens": int}
    """

    full_prompt = ALIGNMENT_PROMPT.format(
        planned_feature=planned_feature,
        actual_work=actual_work,
        vision_context=vision_context
    )

    try:
        # Using asyncio.to_thread to keep the LLM call from blocking your async loop
        response = await client.chat.completions.create (
            model=CONVERSATION_MODEL, # Or a smaller, faster model if preferred
            messages=[{"role": "user", "content": full_prompt}],
            response_format={"type": "json_object"},
            temperature=0.0 # We want objective, consistent grading
        )

        result = json.loads(response.choices[0].message.content)
    
        result = {
            "is_aligned": result.get("is_aligned"),
            "feedback": result.get("feedback"),
            "tokens": response.usage.total_tokens
        }

        return result

    except Exception as e:
        logger.error(f"Vision Alignment Error: {e}")
        # Default to safe failure: don't mark as complete if the check crashes
        return {
            "is_aligned": False, 
            "feedback": "The alignment check encountered a technical error.",
            "tokens": 0
        }
    
async def handle_completion_flow(state: AgentState, user_msg: str, project_state: ProjectState) -> dict:
    """
    Manages the state transitions and text aggregation during a multi-turn completion check.
    """
    context = state.get("completion_context")
    if not context or not isinstance(context, dict) or "collected_info" not in context:
        context = {"collected_info": [], "attempts": 0}

    context["collected_info"].append(user_msg)
    context["attempts"] += 1

    combined_answers = "\n".join(context["collected_info"])
    tokens_used = 0

    active_feature_id = next(
        (fid for fid, f in project_state.feature_log["features"].items() if f["status"] == "in_progress"),
        None
    )

    is_enough, evaluation_tokens = await evaluate_context_sufficiency(combined_answers, project_state, active_feature_id)
    tokens_used += evaluation_tokens

    if not is_enough and context["attempts"] < 3:
        return {
            "skill_output": (
                "SKILL: COMPLETION_INTERVIEW. The user wants to mark their work as complete, but details are insufficient. "
                "Ask them specific, conversational questions about *how* they built it, what exactly was changed, "
                "or if they ran into any blocking errors."
            ),
            "next_status": "COLLECTING",
            "context": context,
            "tokens": tokens_used,
            "is_aligned": None,
            "alignment_note": None,
        }

    features = project_state.feature_log.get("features", {})
    active_feat = features.get(active_feature_id)
    backlog_item = next((b for b in project_state.vision_doc.backlog if b.id == active_feature_id), None)

    if not active_feat or not backlog_item:
        return {
            "skill_output": "CHAT: Could not find the active feature or backlog item to verify against.",
            "next_status": "IDLE",
            "context": {"collected_info": [], "attempts": 0},
            "tokens": tokens_used,
            "is_aligned": None,
            "alignment_note": None,
        }

    alignment_res = await vision_alignment_check(
        planned_feature=f"{active_feat.get('name')}: {backlog_item.description}",
        actual_work=combined_answers,
        vision_context=get_alignment_context(project_state.vision_doc)
    )
    tokens_used += alignment_res["tokens"]

    return {
        "skill_output": (
            f"ALIGNMENT_SUCCESS: {alignment_res['feedback']}. Feature is now marked COMPLETE."
            if alignment_res["is_aligned"]
            else f"ALIGNMENT_FAILED: {alignment_res['feedback']}. Do NOT mark as complete. Explain the drift."
        ),
        "next_status": "IDLE",
        "context": {"collected_info": [], "attempts": 0},
        "tokens": tokens_used,
        "is_aligned": alignment_res["is_aligned"],
        "alignment_note": alignment_res["feedback"],
    }


def get_alignment_context(vision: VisionDoc) -> str:
    """Combines key fields into a compact context string for the LLM."""
    return (
        f"Project: {vision.projectName}\n"
        f"Goal: {vision.visionStatement}\n"
        f"Success Criteria: {vision.successCriteria}\n"
        f"Stack: {', '.join(vision.techStack)}\n"
        f"Constraints: {vision.constraints}"
    )

async def evaluate_context_sufficiency(
    gathered_text: str, 
    project_state: ProjectState, 
    active_feature_id: str | None = None
) -> tuple[bool, int]:
    """Asks the LLM if the user has provided enough concrete technical details compared to the target task description."""
    
    # 1. Look up the task description from the backlog if an ID is provided
    task_context = "No specific feature context provided."
    if active_feature_id and hasattr(project_state, "vision_doc") and hasattr(project_state.vision_doc, "backlog"):
        # Assuming backlog is a list of features/tasks
        target_feature = next((f for f in project_state.vision_doc.backlog if getattr(f, "id", None) == active_feature_id), None)
        if target_feature:
            f_title = getattr(target_feature, "title", "Unknown")
            f_desc = getattr(target_feature, "description", "No description provided.")
            task_context = f"Feature: {f_title}\nDescription/Requirements: {f_desc}"

    # 2. Inject this task target into the prompt
    prompt = f"""
    You are a technical manager checking if a developer has provided enough information about their task completion.
    
    TARGET TASK REQUIREMENTS:
    {task_context}

    DEVELOPER'S PROGRESS EXPLANATION:
    "{gathered_text}"

    TASK:
    Based on the Target Task Requirements, has the developer provided enough concrete, specific technical details regarding what they changed, built, or verified? 
    (e.g., did they mention specific components, database changes, logic updates, or file completions that match the requirement?)

    Respond with EXACTLY 'YES' or 'NO'. Do not include extra punctuation, markdown formatting, or explanation.
    """
    try:
        response = await client.chat.completions.create(
            model=CONVERSATION_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        prediction = response.choices[0].message.content.strip().upper()
        
        # Clean up any accidental formatting the LLM might have returned
        if "YES" in prediction:
            prediction = "YES"
        elif "NO" in prediction:
            prediction = "NO"

        tokens = response.usage.total_tokens if response.usage else 0
        return (prediction == "YES", tokens)
    except Exception as e:
        logger.error(f"Context sufficiency check failed: {e}")
        return (True, 0)  # Fallback to true to prevent infinite lock loops on failure
    
def apply_completion_res(completion_res: dict, state: AgentState, project_state: ProjectState, skill_tokens: int):
    """Unpacks completion flow result and applies state transitions."""
    skill_output = completion_res["skill_output"]
    skill_tokens += completion_res["tokens"]
    state["completion_status"] = completion_res["next_status"]
    state["completion_context"] = completion_res["context"]

    if completion_res.get("alignment_note"):
        state["alignment_note"] = completion_res["alignment_note"]

    next_status = completion_res["next_status"]

    # Path 2: aligned — mark complete
    if next_status == "IDLE" and completion_res.get("is_aligned") is True:

        state["logger"].log_llm_call(
        function_name="feature_completed",
        prompt=f"Feature {project_state.active_feature_id} completion check",
        response=state["alignment_note"],
        tokens=project_state.current_cycle_tokens,
        user_id=state["user_id"],
       )
        
        project_state.previous_feature_id = project_state.active_feature_id
        project_state.active_feature_id = None
        project_state.current_cycle_tokens = 0

    # Path 3: not aligned — reopen the feature so it stays in_progress
    elif next_status == "IDLE" and completion_res.get("is_aligned") is False:
        project_state.previous_feature_id = project_state.active_feature_id
        # active_feature_id stays set — feature remains in_progress for adjustment

        state["logger"].log_llm_call(
        function_name="feature_not_completed",
        prompt=f"Feature {project_state.active_feature_id} completion check",
        response=state["alignment_note"],
        tokens=project_state.current_cycle_tokens,
        user_id=state["user_id"],
    )

    return skill_output, skill_tokens, state