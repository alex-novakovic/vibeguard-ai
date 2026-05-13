from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from datetime import datetime, timezone
from beanie import Document

# --- POMOĆNI MODELI (Pydantic BaseModel) ---

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

# --- BEANIE DOKUMENTI (MongoDB Kolekcije) ---

class VisionDoc(Document):
    user_id: str = Field(index=True)
    createdAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
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

    class Settings:
        name = "vision_docs"
        indexes = ["user_id"]

class FeatureLogItem(Document):
    user_id: str = Field(index=True)
    feature_id: str = Field(description="ID iz backloga, npr. F001")
    name: str
    status: Literal["to_do", "in_progress", "complete"]
    cycles: List[dict]  # start_time, end_time, alignment_note, tokens_used
    drift_events: List[dict]

    class Settings:
        name = "feature_logs"
        indexes = [
            [("user_id", 1), ("feature_id", 1)]
        ]

class SessionEntry(Document):
    user_id: str = Field(index=True)
    workSessionId: str
    startTime: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    endTime: Optional[datetime] = None
    featureCyclesCompleted: List[str] = []
    driftEventsCount: int = 0
    tokensUsed: int = 0
    totalTokensUsed: int = 0
    totalDurationMinutes: int = 0

    class Settings:
        name = "session_entries"
        indexes = ["user_id", "workSessionId"]