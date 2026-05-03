class ProjectState:
    def __init__(self, vision_doc: dict, feature_log: dict):
        self.vision_doc = vision_doc
        self.feature_log = feature_log
        self.active_feature_id = None
        self.current_cycle_tokens = 0

    def update_state(self, vision_doc, feature_log, feature_id, tokens):
        self.vision_doc = vision_doc
        self.feature_log = feature_log
        self.active_feature_id = feature_id
        self.current_cycle_tokens = tokens