import gradio as gr
import json
import queue
import threading
from datetime import datetime, timezone
from pathlib import Path

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
    return "new"

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


WELCOME = "Hi! I'm **VibeGuard AI**. Let's scope your project first.\n\n**What are you building?**"

with gr.Blocks(title="VibeGuard AI") as demo:

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

if __name__ == "__main__":
    demo.launch(theme=gr.themes.Soft())

