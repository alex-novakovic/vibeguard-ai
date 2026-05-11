from data.schemas import VisionDoc, SessionLog

class ProjectState:
    def __init__(self, vision_doc: VisionDoc = None, feature_log: dict = None, session_log: SessionLog = SessionLog()):
        self.vision_doc = vision_doc
        self.feature_log = feature_log
        self.session_log = session_log
        self.active_feature_id = None
        self.previous_feature_id = None
        self.current_cycle_tokens = 0
