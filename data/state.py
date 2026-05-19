from typing import List, Optional
from data.schemas import VisionDoc, FeatureLogItem, SessionEntry

class ProjectState:
    def __init__(
        self, 
        vision_doc: Optional[VisionDoc] = None, 
        feature_log: Optional[List[FeatureLogItem]] = None, 
        session_log: Optional[List[SessionEntry]] = None
    ):
        # Ova tri polja punimo podacima koje asinhrono povučemo iz baze
        self.vision_doc = vision_doc
        self.feature_log = feature_log if feature_log is not None else []
        self.session_log = session_log if session_log is not None else []
        
        # Ova polja se automatski inicijalizuju i funkcija ne mora da ih naglašava
        self.active_feature_id = None
        self.previous_feature_id = None
        self.current_cycle_tokens = 0