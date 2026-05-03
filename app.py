import gradio as gr
import json
import queue
import threading
import anthropic
from datetime import datetime, timezone
from pathlib import Path
from agent.loop import run_agent, agent_state, PHASE_GUARDIAN


# ── STUBS — replace with real imports once Member A/B code is ready ──────────
# from agent.scoping import scoping_session
# from agent.drift import monitor_for_drift
# from agent.suggestion import suggest_next_task
# from agent.alignment import vision_alignment_check
# from data.storage import initialize_feature_log, log_feature_cycle
# from data.state import load_or_create_project

def scoping_session(conversation_history: list) -> dict:
    """STUB. Real version: Member A calls Claude API, returns vision_doc."""
    return {
        "product_name": "VibeGuard AI",
        "one_sentence_benefit": "Keeps vibe-coders on track from first idea to shipped feature.",
        "must_have_features": ["Scoping session", "Feature log", "Drift detection"],
        "feature_ids": ["scoping_session", "feature_log", "drift_detection"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

def initialize_feature_log(vision_doc: dict) -> str:
    """STUB. Real version: Member B creates feature_log.json, returns its path."""
    return "data/logs/feature_log.json"

def load_or_create_project(state) -> str:
    """STUB. Real version: Member B checks if vision.json exists on disk.
    Returns 'existing' if found (loads it into state), 'new' if not."""
    return "existing"

def log_feature_cycle(
    feature_id: str,
    event: str,
    token_count: int = 0,
    alignment_note: str = None,
) -> dict:
    """STUB. Real version: Member B writes to feature_log.json."""
    return {
        "feature_id": feature_id,
        "event": event,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "token_count": token_count,
        "alignment_note": alignment_note,
    }

def monitor_for_drift(
    feature_id: str,
    user_description: str,
    time_spent_minutes: int,
    current_file: str,
) -> dict:
    """STUB. Real version: Member A compares activity against vision_doc."""
    return {
        "is_drift": False,
        "nudge_message": f"You're {time_spent_minutes} min into `{feature_id}` — on track. Keep going!",
    }

def suggest_next_task() -> dict:
    """STUB. Real version: Member A reads log + vision_doc, calls Claude."""
    return {
        "feature_id": "feature_log",
        "feature_name": "Feature Log",
        "reason": "Core to your vision and still unstarted.",
    }

def vision_alignment_check(feature_id: str, alignment_note: str) -> dict:
    """STUB. Real version: Member A compares alignment_note against vision_doc."""
    return {
        "is_aligned": True,
        "feedback": "This work aligns with your core product goal.",
    }

class ProjectStateSTUB:
    """STUB. Real version: Member B provides project state"""
    vision_doc = None
    feature_log = None
    def __init__(self):
        with open("data/logs/vision.json", "r") as f:
            self.vision_doc = json.load(f)

        with open("data/logs/feature_log.json", "r") as f:
            self.feature_log = json.load(f)

def on_startup(state):
    result = load_or_create_project(state)
    if result == "existing":
        # vision_doc already loaded into state by the real function
        welcome = "Welcome back! Your project is loaded. Start a feature below."
        return (
            [{"role": "assistant", "content": welcome}],
            state.vision_doc,    # populate sidebar immediately
            state.feature_log,   # populate feature_log sidebar immediately
            "active",            # skip scoping
        )
    else:
        return (
            [{"role": "assistant", "content": WELCOME}],
            None,                # sidebar empty
            None,                # feature_log sidebar empty
            "scoping",
        )

def on_send(message, history):
    response = run_agent(message)
    history = history + [
        {"role": "user", "content": message},
        {"role": "assistant", "content": response},
    ]

    # scoping just completed on this turn
    if agent_state["phase"] == PHASE_GUARDIAN:
        vision_doc = agent_state["project_state"]["vision_doc"]
        log_path = initialize_feature_log(vision_doc)
        log_data = json.loads(Path(log_path).read_text())
        return history, history, "", vision_doc, log_data

    return history, history, "", gr.update(), gr.update()


WELCOME = "Hi! I'm **VibeGuard AI**. Let's scope your project first.\n\n**What are you building?**"

with gr.Blocks(title="VibeGuard AI") as demo:
    # declare alongside the UI components, inside gr.Blocks
    history_state = gr.State([])          # list of {"role": ..., "content": ...}
    phase_state   = gr.State("scoping")   # "scoping" | "guardian"
    project_state = gr.State(ProjectStateSTUB())   # will hold a ProjectState instance

    gr.Markdown("# VibeGuard AI\n*Stop tinkering. Start shipping.*")

    with gr.Row():

        # ── LEFT: chat panel ──────────────────────────────────────────────────
        with gr.Column(scale=2):
            chatbot = gr.Chatbot(
                value=[{"role": "assistant", "content": WELCOME}],
                label="Agent",
                height=500,
                buttons = ["copy"]
            )
            with gr.Row():
                msg_input = gr.Textbox(
                    placeholder="Type here and press Enter…",
                    show_label=False,
                    scale=5,
                    autofocus=True
                )
                send_btn = gr.Button("Send", variant="primary", scale=1)
                

        # ── RIGHT: sidebar ───────────────────────────────────────────────────
        with gr.Column(scale=1, min_width=300):
            with gr.Accordion("Vision Document", open=True):
                vision_display = gr.JSON(label=None, value=None)
            with gr.Accordion("Feature Log", open=True):
                log_display = gr.JSON(label=None, value=None)

        send_btn.click(
            on_send,
            inputs=[msg_input, history_state],
            outputs=[chatbot, history_state, msg_input, vision_display, log_display]
        )

        msg_input.submit(
            on_send,
            inputs=[msg_input, history_state],
            outputs=[chatbot, history_state, msg_input, vision_display, log_display],
        )


        demo.load(
            on_startup,
            inputs=[project_state],                        # gr.State holding ProjectState
            outputs=[chatbot, vision_display, log_display, phase_state],
        )

if __name__ == "__main__":
    demo.launch(theme=gr.themes.Soft(), share=False)
