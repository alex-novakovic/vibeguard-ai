from data.schemas import VisionDoc
from data.schemas import FeatureLogItem

class ProjectState:
    def __init__(self, vision_doc: VisionDoc, feature_log: FeatureLogItem):
        self.vision_doc = vision_doc
        self.feature_log = feature_log
        self.active_feature_id = None
        self.current_cycle_tokens = 0

    def update_state(self, vision_doc: VisionDoc, feature_log: FeatureLogItem, feature_id: str, tokens: int):
        self.vision_doc = vision_doc
        self.feature_log = feature_log
        self.active_feature_id = feature_id
        self.current_cycle_tokens = tokens