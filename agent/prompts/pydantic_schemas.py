from pydantic import BaseModel, Field
from typing import Optional, Literal


class BacklogItem(BaseModel):
    id: str = Field(pattern=r"^F\d{3}$")
    name: str
    description: str
    priority: Literal["critical", "high", "medium", "low"]
    status: Literal["to_do", "in_progress", "done"]
    estimatedMinutes: int
    dependencies: list[str] = Field(default_factory=list)
    confidence: Literal["high", "low"]
    scopeFlag: bool
    scopeFlagReason: Optional[str] = None


class VisionDoc(BaseModel):
    model_config = {"extra": "forbid"}

    projectName: str
    visionStatement: str
    targetUser: str
    problemStatement: str

    availableTime: Optional[str] = None
    availableTimeHours: int
    experienceLevel: Optional[str] = None
    successCriteria: str
    constraints: Optional[str] = None

    techStack: list[str] = Field(default_factory=list)
    externalDependencies: list[str] = Field(default_factory=list)
    niceToHave: list[str] = Field(default_factory=list)

    backlog: list[BacklogItem] = Field(default_factory=list)