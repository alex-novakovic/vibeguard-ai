from data.schemas import VisionDoc
from data.schemas import FeatureLogItem
from typing import List

class ProjectState:
    def __init__(self, vision_doc: VisionDoc, feature_log: List[FeatureLogItem]):
        # Convert dict to VisionDoc if necessary
        self.vision_doc = vision_doc if isinstance(vision_doc, VisionDoc) else VisionDoc(**vision_doc)
        
        # Convert list of dicts to list of FeatureLogItems
        self.feature_log = [
            f if isinstance(f, FeatureLogItem) else FeatureLogItem(**f) 
            for f in feature_log
        ]
        self.active_feature_id = None
        self.current_cycle_tokens = 0

    def update_state(self, vision_doc: VisionDoc, feature_log: List[FeatureLogItem], feature_id: str, tokens: int):
        self.vision_doc = vision_doc
        self.feature_log = feature_log
        self.active_feature_id = feature_id
        self.current_cycle_tokens = tokens