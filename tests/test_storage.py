import pytest
from pydantic import ValidationError

from data.schemas import BacklogItem, VisionDoc
from data.state import ProjectState


# ── shared fixtures ───────────────────────────────────────────────────────────

VALID_BACKLOG_ITEM = {
    "id": "F001",
    "name": "User Authentication",
    "description": "Login and registration flow",
    "priority": "high",
    "status": "to_do",
    "estimatedMinutes": 120,
    "dependencies": [],
    "confidence": "high",
    "scopeFlag": False,
}

VALID_VISION_DOC = {
    "user_id": "test-user-123",
    "createdAt": "2026-01-01T00:00:00",
    "projectName": "VibeGuard",
    "visionStatement": "AI-powered project guardian",
    "targetUser": "Solo developers",
    "problemStatement": "Scope creep kills MVPs",
    "availableTimeHours": 40,
    "successCriteria": "MVP deployed and tested",
    "techStack": ["Python", "LangGraph"],
    "externalDependencies": ["OpenRouter API"],
    "niceToHave": ["Dark mode"],
    "backlog": [VALID_BACKLOG_ITEM],
}


# ════════════════════════════════════════════════════════════════
# 1. VISION DOC VALIDATION
# Tests that VisionDoc accepts a complete valid dictionary and
# rejects dictionaries that are missing mandatory fields.
# (Pydantic replaces an explicit validate_vision_doc function.)
# ════════════════════════════════════════════════════════════════

class TestVisionDocValidation:

    def test_valid_vision_doc_is_accepted(self):
        """
        A fully populated dictionary must produce a VisionDoc
        without raising any exception.
        """
        doc = VisionDoc(**VALID_VISION_DOC)
        assert doc.projectName == "VibeGuard"

    def test_missing_project_name_raises(self):
        """
        projectName is mandatory — omitting it must raise ValidationError.
        """
        bad = {k: v for k, v in VALID_VISION_DOC.items() if k != "projectName"}
        with pytest.raises(ValidationError):
            VisionDoc(**bad)

    def test_missing_vision_statement_raises(self):
        """
        visionStatement is mandatory — omitting it must raise ValidationError.
        """
        bad = {k: v for k, v in VALID_VISION_DOC.items() if k != "visionStatement"}
        with pytest.raises(ValidationError):
            VisionDoc(**bad)

    def test_missing_backlog_raises(self):
        """
        backlog is mandatory — omitting it must raise ValidationError.
        """
        bad = {k: v for k, v in VALID_VISION_DOC.items() if k != "backlog"}
        with pytest.raises(ValidationError):
            VisionDoc(**bad)

    def test_optional_fields_default_to_none(self):
        """
        availableTime, experienceLevel, and constraints are optional.
        When omitted they must default to None, not raise.
        """
        doc = VisionDoc(**VALID_VISION_DOC)
        assert doc.availableTime is None
        assert doc.constraints is None
        assert doc.experienceLevel is None


# ════════════════════════════════════════════════════════════════
# 2. PYDANTIC TYPE ENFORCEMENT
# Tests that BacklogItem and VisionDoc reject incorrect data types.
# Minimum requirement: a string where a list is expected must
# raise a ValidationError.
# ════════════════════════════════════════════════════════════════

class TestBacklogItemEnforcement:

    def test_valid_backlog_item_is_accepted(self):
        """
        A correctly typed BacklogItem must be created without error.
        """
        item = BacklogItem(**VALID_BACKLOG_ITEM)
        assert item.id == "F001"

    def test_dependencies_as_string_raises(self):
        """
        dependencies expects List[str]. Passing a plain string must
        raise ValidationError, not silently coerce the value.
        """
        bad = {**VALID_BACKLOG_ITEM, "dependencies": "F000"}
        with pytest.raises(ValidationError):
            BacklogItem(**bad)

    def test_invalid_priority_literal_raises(self):
        """
        priority is Literal["critical","high","medium","low"].
        Any value outside that set must raise ValidationError.
        """
        bad = {**VALID_BACKLOG_ITEM, "priority": "urgent"}
        with pytest.raises(ValidationError):
            BacklogItem(**bad)

    def test_invalid_confidence_is_coerced_to_low(self):
        """
        confidence validator coerces unrecognised values to 'low' instead of raising.
        """
        item = BacklogItem(**{**VALID_BACKLOG_ITEM, "confidence": "medium"})
        assert item.confidence == "low"

    def test_scope_flag_reason_defaults_to_none(self):
        """
        scopeFlagReason is optional — it must default to None when absent.
        """
        item = BacklogItem(**VALID_BACKLOG_ITEM)
        assert item.scopeFlagReason is None


class TestVisionDocEnforcement:

    def test_tech_stack_as_string_raises(self):
        """
        techStack expects List[str]. Passing a plain string must
        raise ValidationError.
        """
        bad = {**VALID_VISION_DOC, "techStack": "Python"}
        with pytest.raises(ValidationError):
            VisionDoc(**bad)

    def test_backlog_as_string_raises(self):
        """
        backlog expects List[BacklogItem]. Passing a plain string must
        raise ValidationError.
        """
        bad = {**VALID_VISION_DOC, "backlog": "some feature"}
        with pytest.raises(ValidationError):
            VisionDoc(**bad)

    def test_available_time_hours_as_string_raises(self):
        """
        availableTimeHours expects int. Passing a non-numeric string
        must raise ValidationError.
        """
        bad = {**VALID_VISION_DOC, "availableTimeHours": "forty"}
        with pytest.raises(ValidationError):
            VisionDoc(**bad)


# ════════════════════════════════════════════════════════════════
# 3. STATE MANAGEMENT
# Tests that ProjectState initialises correctly and that all
# internal attributes are properly mapped from the input data.
# ════════════════════════════════════════════════════════════════

class TestProjectStateInit:

    def test_defaults_when_created_with_no_args(self):
        """
        A default ProjectState must have vision_doc as None, feature_log
        as an empty list, both feature ID fields as None, and token counter at 0.
        """
        state = ProjectState()
        assert state.vision_doc is None
        assert state.feature_log == []
        assert state.active_feature_id is None
        assert state.previous_feature_id is None
        assert state.current_cycle_tokens == 0

    def test_vision_doc_is_mapped_from_input(self):
        """
        When a VisionDoc is passed, state.vision_doc must reference
        the same object with all its fields intact.
        """
        doc = VisionDoc(**VALID_VISION_DOC)
        state = ProjectState(vision_doc=doc)
        assert state.vision_doc is doc
        assert state.vision_doc.projectName == "VibeGuard"

    def test_feature_log_is_mapped_from_input(self):
        """
        When a feature_log list is passed, state.feature_log must
        reference exactly that list.
        """
        feature_log = []
        state = ProjectState(feature_log=feature_log)
        assert state.feature_log is feature_log

    def test_token_counter_starts_at_zero_with_data(self):
        """
        Even when vision_doc and feature_log are provided, the token
        counter must still start at 0.
        """
        doc = VisionDoc(**VALID_VISION_DOC)
        state = ProjectState(vision_doc=doc)
        assert state.current_cycle_tokens == 0

    def test_active_feature_ids_are_none_on_fresh_state(self):
        """
        A newly created state has no active or previous feature —
        both must be None regardless of what data was passed in.
        """
        doc = VisionDoc(**VALID_VISION_DOC)
        state = ProjectState(vision_doc=doc)
        assert state.active_feature_id is None
        assert state.previous_feature_id is None