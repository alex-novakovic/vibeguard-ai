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

    json_instruction = (
        "\n\nReturn your final assessment strictly as a JSON object with the keys "
        "'is_aligned' (boolean) and 'feedback' (string)."
    )

    full_prompt = ALIGNMENT_PROMPT.format(
        planned_feature=planned_feature,
        actual_work=actual_work,
        vision_context=vision_context
    ) + json_instruction

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
            "alignment_note": None
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
            "alignment_note": None
        }

    alignment_res = await vision_alignment_check(
        planned_feature=f"{active_feat.get('name')}: {backlog_item.description}",
        actual_work=combined_answers,
        vision_context=get_alignment_context(project_state.vision_doc)
    )
    tokens_used += alignment_res["tokens"]

    # compute remaining after this feature completes
    remaining = [
    item for item in project_state.vision_doc.backlog
    if item.status == "to_do" and item.id != active_feature_id
    ]  

    return {
        "skill_output": ((
        f"ALIGNMENT_SUCCESS — no tasks remaining, this is the final feature. "
        f"Congratulate the user on completing the full MVP. Do NOT ask about next tasks. {alignment_res['feedback']}."
        if not remaining
        else f"ALIGNMENT_SUCCESS — {len(remaining)} task(s) remaining. {alignment_res['feedback']}. Feature is now marked COMPLETE."
    )
    if alignment_res["is_aligned"]
    else (
        f"ALIGNMENT_FAILED — {len(remaining)} task(s) remaining. {alignment_res['feedback']}. Do NOT mark as complete. Explain the drift."
        if remaining
        else f"ALIGNMENT_FAILED — this is the final feature but it needs fixes. {alignment_res['feedback']}. Do NOT mark as complete. Explain the drift."
    )
    ),
        "next_status": "IDLE",
        "context": {"collected_info": [], "attempts": 0},
        "tokens": tokens_used,
        "is_aligned": alignment_res["is_aligned"],
        "alignment_note": alignment_res["feedback"]
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
        target_feature = next((f for f in project_state.vision_doc.backlog if getattr(f, "id", None) == active_feature_id), None)
        if target_feature:
            f_name = getattr(target_feature, "name", "Unknown")
            f_desc = getattr(target_feature, "description", "No description provided.")
            task_context = f"Feature: {f_name}\nDescription/Requirements: {f_desc}"

    # 2. Inject this task target into the prompt
    prompt = f"""
    You are a technical manager checking if a developer has provided enough information to verify their task is complete.

    TARGET TASK REQUIREMENTS:
    {task_context}

    DEVELOPER'S PROGRESS EXPLANATION:
    "{gathered_text}"

    TASK:
    Has the developer provided enough information to reasonably conclude the task is done?

    ACCEPT as sufficient (return YES) if the developer:
    - Describes what they built, even in high-level terms
    - Explains the problem they solved or the outcome they achieved
    - Says it works or is tested, even without deep technical detail
    - Uses problem-solution framing with a clear outcome ("it wasn't working because X, I fixed it, now it works")
    - Accumulates enough context across multiple messages that together describe completion

    REJECT as insufficient (return NO) only if:
    - The answer is purely vague ("done", "finished", "it works") with zero supporting detail
    - The description clearly refers to a different feature entirely
    - The developer admits it is not working or not complete

    DO NOT require:
    - Specific file names, component names, or library names
    - Mention of the exact technology from the task requirements (e.g. "Ethereum" or "RPC")
    - Database schema details or exact implementation steps
    - Code-level specifics

    EXAMPLES:
    - "done" → NO (zero detail)
    - "it works now" → NO (no supporting detail)
    - "The balance wasn't showing because of a decimal conversion issue. I fixed it and now it displays correctly." → YES (problem-solution with clear outcome)
    - "I connected to the API and the data shows up on screen" → YES (outcome described)
    - "I worked on the dashboard instead" → NO (wrong feature)
    - "I tried but kept getting errors" → NO (not complete)

    Respond with EXACTLY 'YES' or 'NO'. No punctuation, no explanation.
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
    tokens_accounted = False

    # Path 2: aligned — mark complete
    if next_status == "IDLE" and completion_res.get("is_aligned") is True:
        state["feature_tokens"] += skill_tokens

        state["logger"].log_llm_call(
        function_name="feature_completed",
        prompt=f"Feature {project_state.active_feature_id} completion check",
        response=state["alignment_note"],
        tokens=state["feature_tokens"],
        user_id=state["user_id"]
       )
        
        project_state.previous_feature_id = project_state.active_feature_id
        project_state.active_feature_id = None
        project_state.current_cycle_tokens = state["feature_tokens"]
        state["feature_tokens"] = 0
        tokens_accounted = True

    # Path 3: not aligned — reopen the feature so it stays in_progress
    elif next_status == "IDLE" and completion_res.get("is_aligned") is False:
        state["feature_tokens"] += skill_tokens

        state["logger"].log_llm_call(
        function_name="feature_not_completed",
        prompt=f"Feature {project_state.active_feature_id} completion check",
        response=state["alignment_note"],
        tokens=state["feature_tokens"],
        user_id=state["user_id"]
    )
        project_state.previous_feature_id = project_state.active_feature_id
        # active_feature_id stays set — feature remains in_progress for adjustment
        tokens_accounted = True

    return skill_output, skill_tokens, state, tokens_accounted