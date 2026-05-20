import json
import logging
from agent.config import CONVERSATION_MODEL, client
from data.state import ProjectState
from agent.prompts.drift_prompt import DRIFT_CHECK_PROMPT

logger = logging.getLogger(__name__)


async def check_drift(
    planned_feature: str,
    actual_work: str,
    vision_context: str
) -> dict:
    """
    Evaluates if the developer has drifted.
    Returns: {"is_drifted": bool, "feedback": str, "severity": str, "tokens": int}
    """
    prompt = DRIFT_CHECK_PROMPT.format(
        planned_feature=planned_feature,
        actual_work=actual_work,
        vision_context=vision_context
    )

    try:
        response = await client.chat.completions.create(
            model=CONVERSATION_MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.0
        )

        result = json.loads(response.choices[0].message.content)
        return {
            "is_drifted": result.get("is_drifted", False),
            "feedback":   result.get("feedback", ""),
            "severity":   result.get("severity", "none"),
            "tokens":     response.usage.total_tokens
        }

    except Exception as e:
        logger.error(f"Drift check error: {e}")
        return {
            "is_drifted": False,
            "feedback":   "Drift check encountered a technical error.",
            "severity":   "none",
            "tokens":     0
        }


async def handle_drift_flow(state: dict, user_msg: str, project_state: ProjectState) -> dict:
    """
    Manages the drift interview flow.
    Returns a result dict describing what happened and what to do next.
    """
    active_id = project_state.active_feature_id
    active_feat = next(
    (f for f in project_state.feature_log if f.feature_id == active_id),
    None
)
    backlog_item = next((b for b in project_state.vision_doc.backlog if b.id == active_id), None)

    if not active_feat or not backlog_item:
        return {
            "status":      "IDLE",
            "skill_output": "CHAT: No active feature to check drift against.",
            "drift_note":  None,
            "tokens":      0
        }

    drift_context = state.get("drift_context", {"collected_info": [], "attempts": 0})
    drift_context["collected_info"].append(user_msg)
    drift_context["attempts"] += 1
    tokens_used = 0

    is_sufficient, evaluation_tokens = await evaluate_drift_context_sufficiency(
    gathered_text=" ".join(drift_context["collected_info"]),
    project_state=project_state,
    active_feature_id=active_id
    )

    tokens_used += evaluation_tokens

    if not is_sufficient and drift_context["attempts"] < 3:
        return {
            "status":        "COLLECTING",
            "skill_output":  "DRIFT_INTERVIEW: The developer hasn't been specific enough. Ask them exactly what they are working on right now — what file, what function, what problem are they solving at this moment?",
            "drift_context": drift_context,
            "drift_note":    None,
            "tokens":        tokens_used
        }
    
    # enough context — run the check
    planned = f"{active_feat.get('name')}: {backlog_item.description}"
    actual  = " ".join(drift_context["collected_info"])

    from agent.complete import get_alignment_context
    res = await check_drift(
        planned_feature=planned,
        actual_work=actual,
        vision_context=get_alignment_context(project_state.vision_doc)
    )

    tokens_used += res["tokens"]

    if res["is_drifted"]:
        if res["severity"] == "severe":
            skill_output = f"DRIFT_SEVERE: {res['feedback']}. The developer is significantly off track. Strongly redirect them back to {active_id}."
        else:
            skill_output = f"DRIFT_MILD: {res['feedback']}. Gently remind the developer to refocus on {active_id}."
    else:
        skill_output = f"DRIFT_CLEAR: {res['feedback']}. The developer is on track. Encourage them to keep going."

    return {
        "status":        "IDLE",
        "skill_output":  skill_output,
        "drift_context": {"collected_info": [], "attempts": 0},  # reset
        "drift_note":    res["feedback"] if res["is_drifted"] else None,
        "tokens":        tokens_used
    }

async def evaluate_drift_context_sufficiency(
    gathered_text: str,
    project_state: ProjectState,
    active_feature_id: str | None = None
) -> tuple[bool, int]:
    """
    Asks the LLM if the user has provided enough information about
    their current activity to judge whether they are drifting.
    """
    task_context = "No specific feature context provided."
    if active_feature_id and hasattr(project_state, "vision_doc"):
        target_feature = next((f for f in project_state.vision_doc.backlog if getattr(f, "id", None) == active_feature_id), None)
        if target_feature:
            task_context = f"Feature: {target_feature.name}\nDescription: {target_feature.description}"

    prompt = f"""
    You are checking if a developer has provided enough context about
    their current work to assess whether they are on track or drifting.

    PLANNED TASK:
    {task_context}

    WHAT THE DEVELOPER PROVIDED:
    "{gathered_text}"

    RULES:
    - If the developer shared actual code, a script, or a code snippet → YES immediately, no further analysis needed
    - If the developer mentioned specific function names, file names, API calls, or library names → YES
    - If the developer described a concrete technical action they are performing → YES
    - Only NO if the response is purely vague: "just coding", "working on it", "doing stuff", no technical detail at all

    Respond with EXACTLY 'YES' or 'NO'. No punctuation, no explanation.
    """

    try:
        response = await client.chat.completions.create(
            model=CONVERSATION_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        prediction = response.choices[0].message.content.strip().upper()

        if "YES" in prediction:
            prediction = "YES"
        elif "NO" in prediction:
            prediction = "NO"

        tokens = response.usage.total_tokens if response.usage else 0
        return (prediction == "YES", tokens)

    except Exception as e:
        logger.error(f"Drift context sufficiency check failed: {e}")
        return (True, 0) 


def apply_drift_res(drift_res: dict, state: dict, project_state: ProjectState) -> tuple:
    """
    Applies the drift flow result to state and project_state.
    Returns: (skill_output, skill_tokens, state, tokens_accounted)
    """
    skill_output = drift_res["skill_output"]
    tokens       = drift_res.get("tokens", 0)

    state["drift_status"]  = drift_res["status"]
    state["drift_context"] = drift_res.get("drift_context", state.get("drift_context", {"collected_info": [], "attempts": 0}))
    state["drift_note"]    = drift_res.get("drift_note")

    return skill_output, tokens, state


