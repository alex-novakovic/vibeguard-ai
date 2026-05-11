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
        self.previous_feature_id = None
        # counts total tokens used so far
        self.total_tokens = 0
        