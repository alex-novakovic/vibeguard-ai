from typing import List, Optional
from data.schemas import VisionDocData, FeatureLogItem, SessionEntry

class ProjectState:
    def __init__(
        self, 
        vision_doc: Optional[VisionDocData] = None,
        feature_log: Optional[List[FeatureLogItem]] = None, 
        session_log: Optional[List[SessionEntry]] = None
    ):
        
        self.vision_doc = vision_doc
        self.feature_log = feature_log if feature_log is not None else []
        self.session_log = session_log if session_log is not None else []
       
        self.active_feature_id = None
        self.previous_feature_id = None
        self.current_cycle_tokens = 0