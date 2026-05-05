from pydantic import BaseModel
from typing import Optional, List, Literal

class BacklogItem(BaseModel):
    id: str
    name: str
    description: str
    priority: Literal["critical", "high", "medium", "low"]
    status: Literal["to_do"]
    estimatedMinutes: int
    dependencies: List[str]
    confidence: Literal["high", "low"]
    scopeFlag: bool
    scopeFlagReason: Optional[str] = None

class VisionDoc(BaseModel):
    createdAt: str
    projectName: str
    visionStatement: str
    targetUser: str
    problemStatement: str
    availableTime: Optional[str] = None
    availableTimeHours: int
    experienceLevel: Optional[str] = None
    successCriteria: str
    constraints: Optional[str] = None
    techStack: List[str]
    externalDependencies: List[str]
    niceToHave: List[str]
    backlog: List[BacklogItem]

class FeatureLogItem(BaseModel):
    model_config = {"frozen": False} #allow mutation for in-place updates
    name: str
    status: Literal["to_do", "in_progress", "complete"]
    cycles: List[dict]
    drift_events: List[dict]
