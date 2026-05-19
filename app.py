import gradio as gr
import uuid
import asyncio
from agent.agent_session import AgentSession, PHASE_GUARDIAN
from agent.loop import Agent
from interfaces import StorageBackend, AgentFunctions
from data.storage import Storage
from data.db import init_db
from utils.exceptions import (
    DatabaseError,
    VibeGuardError,
    RateLimitReached,
    ModelTimeout,
    EmptyResponse,
    ParsingFailed,
)

storage: StorageBackend = Storage()
agent: AgentFunctions = Agent()

_session_states: dict = {}

WELCOME = "Hi! I'm **VibeGuard AI**. Let's scope your project first.\n\n**What are you building?**"


async def on_startup(user_id): 
    if not user_id:
        user_id = str(uuid.uuid4())

    try:
     await init_db()
    except DatabaseError as e:
        msg = f"⚠️ Database connection failed: {e}"
        return user_id, [{"role": "assistant", "content": msg}], None, None, "new", None, AgentSession()
    
     # first visit — generate once, stored in browser
    try:
        session = AgentSession()
        session.user_id = user_id
        status, state = await storage.load_or_create_project(user_id)
        new_session_entry = await storage.start_session(user_id) #ovo je promenjeno jer nije vise ceo session_log zajedno
        state.session_log.append(new_session_entry)

    except ParsingFailed as e:
        msg = f"⚠️ {e}"
        return user_id, [{"role": "assistant", "content": msg}], None, None, "new", None, AgentSession()
    
    except VibeGuardError as e:
        msg = f"⚠️ {e}"
        return user_id, [{"role": "assistant", "content": msg}], None, None, "new", None, AgentSession()

    session.project_state = state
    if status == "existing":
        session.phase = PHASE_GUARDIAN
        return (
            user_id,
            [{"role": "assistant", "content": "Welcome back! Your project is loaded. Start a feature below."}],
            state.vision_doc.model_dump(),
            state.feature_log,
            status,
            state,
            session,
        )
    return (
        user_id,
        [{"role": "assistant", "content": WELCOME}],
        None,
        None,
        status,
        state,
        session,
    )


async def on_exit(request: gr.Request):
    entry = _session_states.pop(request.session_hash, None)
    if entry is None:
        return
    
    session_id = entry["session_id"]
    session = entry["agent_session"]
    
    if session is None or session.project_state is None:
        return
        
    try:
        proj_state = session.project_state
        user_id = session.user_id  # Uzimamo user_id koji imamo sačuvan u session objektu
        
        # 1. Pozivamo novu end_session sa tačnim argumentima
        updated_session_entry = await storage.end_session(
            user_id=user_id,
            session_id=session_id,
            total_tokens=proj_state.current_cycle_tokens,
        )
        
        # 2. Usklađujemo listu u memoriji (session_log)
        # Prolazimo kroz listu i zamenjujemo staru sesiju sa ovom ažuriranom iz baze
        if proj_state.session_log:
            for i, old_entry in enumerate(proj_state.session_log):
                if old_entry.workSessionId == session_id:
                    proj_state.session_log[i] = updated_session_entry
                    break
        
        # 3. Istresamo sve ostale izmene (npr. ako je bilo izmena u vision_doc ili feature_log)
        await storage.dump_logs(proj_state.vision_doc, proj_state.feature_log, proj_state.session_log)
        
    except VibeGuardError:
        pass


async def on_send(message, history, session, status, proj_state, initialized, request: gr.Request):
    def _agent_error(msg):
        err_history = history + [
            {"role": "user", "content": message},
            {"role": "assistant", "content": msg},
        ]
        return err_history, err_history, "", gr.update(), gr.update(), initialized, status, proj_state

    try:
        response, session = await agent.run_agent(message, status, session)
    except RateLimitReached:
        return _agent_error("⚠️ Rate limit reached. Please wait a moment and try again.")
    except ModelTimeout:
        return _agent_error("⚠️ The AI took too long to respond. Please try again.")
    except EmptyResponse:
        return _agent_error("⚠️ The AI returned an empty response. Please try again.")
    except ParsingFailed:
        return _agent_error("⚠️ Failed to parse the AI's response. Please try again.")
    except VibeGuardError as e:
        return _agent_error(f"⚠️ An error occurred: {e}")

    history = history + [
        {"role": "user", "content": message},
        {"role": "assistant", "content": response},
    ]

    if session.phase == PHASE_GUARDIAN and session.project_state and not initialized:
        vision_doc = session.project_state.vision_doc
        log_data = await storage.initialize_feature_log(vision_doc)
        session.project_state.feature_log = log_data
        _session_states[request.session_hash]["agent_session"] = session.project_state
        return history, history, "", vision_doc.model_dump(), log_data, True, "existing", session.project_state

    if session.project_state: #NEW
        await storage.dump_logs(session.project_state.vision_doc, session.project_state.feature_log, session.project_state.session_log)

    return history, history, "", gr.update(), gr.update(), initialized, status, proj_state


with gr.Blocks(title="VibeGuard AI") as demo:
    user_id_browser   = gr.BrowserState(None)
    session_state     = gr.State(None)
    history_state     = gr.State([])
    status_state      = gr.State("new")           # "new" | "existing" from load_or_create_project
    proj_state_state  = gr.State(None)                                             # ProjectState object from Member B
    initialized_state = gr.State(False)           # True after initialize_feature_log is called

    gr.Markdown("# VibeGuard AI\n*Stop tinkering. Start shipping.*")

    with gr.Row():
        with gr.Column(scale=2):
            chatbot = gr.Chatbot(
                value=[{"role": "assistant", "content": WELCOME}],
                label="Agent",
                height=500,
                buttons=["copy"],
            )
            with gr.Row():
                msg_input = gr.Textbox(
                    placeholder="Type here and press Enter…",
                    show_label=False,
                    scale=5,
                    autofocus=True,
                )
                send_btn = gr.Button("Send", variant="primary", scale=1)

        with gr.Column(scale=1, min_width=300):
            with gr.Accordion("Vision Document", open=True):
                vision_display = gr.JSON(label=None, value=None)
            with gr.Accordion("Feature Log", open=True):
                log_display = gr.JSON(label=None, value=None)

    _send_inputs  = [msg_input, history_state, session_state, status_state, proj_state_state, initialized_state]
    _send_outputs = [chatbot, history_state, msg_input, vision_display, log_display, initialized_state, status_state, proj_state_state]

    send_btn.click(on_send, inputs=_send_inputs, outputs=_send_outputs)
    msg_input.submit(on_send, inputs=_send_inputs, outputs=_send_outputs)
    demo.load(
        on_startup,
        inputs=[user_id_browser],
        outputs=[user_id_browser, chatbot, vision_display, log_display, status_state, proj_state_state, session_state],
    )
    demo.unload(on_exit)

###NEWWWW
async def main():

    # 2. Start the Gradio app
    demo.launch(theme=gr.themes.Soft(), share=False)

if __name__ == "__main__":
    # Except demo.launch(), we don't need to run the event loop here since Gradio will handle it.
    asyncio.run(main())
