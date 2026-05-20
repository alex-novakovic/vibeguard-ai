import gradio as gr
import uuid
import time
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
_drift_vars: dict = {"last_send": None, "status": "new"}

WELCOME = "Hi! I'm **VibeGuard AI**. Let's scope your project first.\n\n**What are you building?**"


async def on_startup(user_id, request: gr.Request): 

    if not user_id:
        #user_id = "3d82f33d-a13d-4557-bde1-7a7ff5dd1ef2"
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
        #ovde treba dodati izvlacenje session_id iz new_session_entry i cuvanje u session objektu, a zatim i cuvanje tog session objekta u _session_states
        session_id = new_session_entry.workSessionId
        state.session_log.append(new_session_entry)
        _session_states[request.session_hash] = {}
        _session_states[request.session_hash]["session_id"] = session_id
    except ParsingFailed as e:
        msg = f"⚠️ {e}"
        return user_id, [{"role": "assistant", "content": msg}], None, None, None, "new", AgentSession()
    except DatabaseError as e:
        msg = f"⚠️ {e}"
        return user_id, [{"role": "assistant", "content": msg}], None, None, None, "new", AgentSession()
    except VibeGuardError as e:
        msg = f"⚠️ {e}"
        return user_id, [{"role": "assistant", "content": msg}], None, None, None, "new", AgentSession()

    session.project_state = state
    _session_states[request.session_hash]["agent_session"] = session
    _drift_vars["status"] = status
    if status == "existing":
        session.phase = PHASE_GUARDIAN
        # restore active feature and set is_returning
        #features = state.feature_log.get("features", {})
        #active = next((fid for fid, f in features.items() if f["status"] == "in_progress"),None)
        #session.is_returning = active is not None  # ← set here
        return (
            user_id,
            [{"role": "assistant", "content": "Welcome back! Your project is loaded. Start a feature below."}],
            state.vision_doc.model_dump(),
            state.feature_log,
            state.session_log,
            status,
            session,
            True  # ← initialized_state = True, skip initialize_feature_log entirely
        )
    return (
        user_id,
        [{"role": "assistant", "content": WELCOME}],
        None,
        None,
        state.session_log,  # Ovo će biti None za novi projekat, ali je važno da se vrati kao None, a ne kao prazan niz
        status,
        session,
        False  # ← initialized_state = False, will initialize on first send
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


async def on_drift_check(history, session):
    last_send = _drift_vars["last_send"]
    status = _drift_vars["status"]
    if status != "existing" or last_send is None or time.time() - last_send < 20:
        return gr.update(), gr.update(), gr.update(), gr.update()

    gr.Warning("Time for check")
    _drift_vars["last_send"] = time.time()
    session.drift_status = "COLLECTING"

    try:
        response, session = await agent.run_agent("DRIFT", status, session)
    except RateLimitReached:
        response = "⚠️ Rate limit reached. Please wait a moment and try again."
    except ModelTimeout:
        response = "⚠️ The AI took too long to respond. Please try again."
    except EmptyResponse:
        response = "⚠️ The AI returned an empty response. Please try again."
    except ParsingFailed:
        response = "⚠️ Failed to parse the AI's response. Please try again."
    except VibeGuardError as e:
        response = f"⚠️ An error occurred: {e}"

    history = history + [{"role": "assistant", "content": response}]
    fx = (
        f'<img src="x?t={int(time.time())}" style="display:none" '
        f"onerror=\"window.playBeep&&window.playBeep();document.title='\\u26a0\\ufe0f Time for check'\">"
    )
    return history, history, session, gr.update(value=fx)


async def on_send(message, history, session, status, initialized, request: gr.Request):
    if not message.strip():
        return history, history, "", gr.update(), gr.update(), gr.update(), initialized, status, session, gr.update()

    def _agent_error(msg):
        err_history = history + [
            {"role": "user", "content": message},
            {"role": "assistant", "content": msg},
        ]
        _drift_vars["last_send"] = time.time()
        return err_history, err_history, gr.update(value="", interactive=False), gr.update(), gr.update(), gr.update(), initialized, status, session, gr.update(interactive=False)

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
    if session.phase == PHASE_GUARDIAN:
        proj_state = session.project_state
        prev = proj_state.previous_feature_id
        active = proj_state.active_feature_id

        if not initialized:
            proj_state.feature_log = storage.initialize_feature_log(proj_state.vision_doc)
            _session_states[request.session_hash]["agent_session"] = session
            _drift_vars["last_send"] = time.time()
            _drift_vars["status"] = "existing"
            await storage.dump_logs(session.project_state.vision_doc, session.project_state.feature_log, session.project_state.session_log)
            return history, history, "", proj_state.vision_doc.model_dump(), proj_state.feature_log, gr.update(), True, "existing", session, gr.update()

        if prev is None and active is not None:
            proj_state.feature_log = storage.log_feature_cycle(proj_state.feature_log, active, "start", None, None)
        elif prev == active:
            if session.drift_note is not None and session.alignment_note is not None:
               proj_state.feature_log = storage.log_feature_cycle(proj_state.feature_log, active, "in_progress", session.alignment_note, session.drift_note)
               session.alignment_note = None
               session.drift_note = None
            elif session.alignment_note is not None:
                proj_state.feature_log = storage.log_feature_cycle(proj_state.feature_log, active, "in_progress", session.alignment_note, None)
                session.alignment_note = None
            elif session.drift_note is not None:
                proj_state.feature_log = storage.log_feature_cycle(proj_state.feature_log, active, "in_progress", None, session.drift_note)
                session.drift_note = None
        elif prev is not None and active is None:
            proj_state.feature_log = storage.log_feature_cycle(proj_state.feature_log, prev, "complete", session.alignment_note, None)
            session.alignment_note = None
            
        _session_states[request.session_hash]["agent_session"] = session
        _drift_vars["last_send"] = time.time()
        await storage.dump_logs(session.project_state.vision_doc, session.project_state.feature_log, session.project_state.session_log)
        return history, history, "", gr.update(), proj_state.feature_log, gr.update(), initialized, status, session, gr.update()

    _drift_vars["last_send"] = time.time()
    await storage.dump_logs(session.project_state.vision_doc, session.project_state.feature_log, session.project_state.session_log)
    return history, history, "", gr.update(), gr.update(), gr.update(), initialized, status, session, gr.update()


_DRIFT_JS = """
document.addEventListener('click', function() {
    if (!window._audioCtx) {
        window._audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    }
    if (window._audioCtx.state === 'suspended') {
        window._audioCtx.resume();
    }
});
window.addEventListener('focus', function() {
    if (document.title.startsWith('⚠')) document.title = 'VibeGuard AI';
});
window.playBeep = function() {
    if (!window._audioCtx) return;
    var ctx = window._audioCtx;
    var osc = ctx.createOscillator();
    var gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.type = 'sine';
    osc.frequency.value = 660;
    gain.gain.setValueAtTime(0.4, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.8);
    osc.start(ctx.currentTime);
    osc.stop(ctx.currentTime + 0.8);
};
"""

with gr.Blocks(title="VibeGuard AI") as demo:
    user_id_browser   = gr.BrowserState(None)
    session_state     = gr.State(None)
    history_state     = gr.State([])
    status_state      = gr.State("new")           # "new" | "existing" from load_or_create_project
    initialized_state = gr.State(False)           # True after initialize_feature_log is called

    drift_fx = gr.HTML(value="")

    gr.Markdown("# VibeGuard AI\n*Stop tinkering. Start shipping.*")

    with gr.Row():
        with gr.Column(scale=2):
            chatbot = gr.Chatbot(
                value=[{"role": "assistant", "content": WELCOME}],
                label="Agent",
                height=500,
                buttons=["copy"],
                autoscroll=True,
            )
            with gr.Row():
                msg_input = gr.Textbox(
                    placeholder="Type here and press Enter…",
                    show_label=False,
                    scale=5,
                    autofocus=True,
                )
                send_btn = gr.Button("Send", variant="primary", scale=1, interactive=False)

        with gr.Column(scale=1, min_width=300):
            with gr.Accordion("Vision Document", open=False):
                vision_display = gr.JSON(label=None, value=None)
            with gr.Accordion("Feature Log", open=False):
                log_display = gr.JSON(label=None, value=None)
            with gr.Accordion("Session Log", open=False):
                session_display = gr.JSON(label=None, value=None)

    _send_inputs  = [msg_input, history_state, session_state, status_state, initialized_state]
    _send_outputs = [chatbot, history_state, msg_input, vision_display, log_display, session_display, initialized_state, status_state, session_state, send_btn]

    msg_input.change(fn=lambda x: gr.update(interactive=bool(x.strip())), inputs=[msg_input], outputs=[send_btn])
    send_btn.click(on_send, inputs=_send_inputs, outputs=_send_outputs)
    msg_input.submit(on_send, inputs=_send_inputs, outputs=_send_outputs)
    demo.load(
        on_startup,
        inputs=[user_id_browser],
        outputs=[user_id_browser, chatbot, vision_display, log_display, session_display, status_state, session_state, initialized_state],
    )

    timer_drift = gr.Timer(10)
    timer_drift.tick(fn=on_drift_check, inputs=[history_state, session_state], outputs=[chatbot, history_state, session_state, drift_fx], trigger_mode="multiple")

    demo.unload(on_exit)

if __name__ == "__main__":
    demo.queue()
    demo.launch(theme=gr.themes.Soft(), share=False, js=_DRIFT_JS)

