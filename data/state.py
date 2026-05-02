class ProjectState:
    def __init__(self, vision_doc: dict, feature_log: dict):
        self.vision_doc = vision_doc
        self.feature_log = feature_log
        self.active_feature_id = None
        self.current_cycle_tokens = 0