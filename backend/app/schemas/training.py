from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class TrainingCourseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    content_language: Literal["auto", "zh-CN", "en-US"] = "auto"
    scope_type: Literal["lab", "project"] = "lab"
    project_id: str | None = None


class TrainingCourseUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    content_language: Literal["auto", "zh-CN", "en-US"] | None = None


class TrainingCourseAssetCreate(BaseModel):
    research_asset_ids: list[str] = Field(min_length=1, max_length=50)


class TrainingModuleCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=5000)


class TrainingModuleUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=5000)


class TrainingUnitCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    pass_score: int = Field(default=80, ge=1, le=100)


class TrainingUnitAssetCreate(BaseModel):
    course_asset_ids: list[str] = Field(max_length=50)


class TrainingUnitLessonUpdate(BaseModel):
    lesson_markdown: str = Field(min_length=1, max_length=50000)


class TrainingModuleAssignmentCreate(BaseModel):
    trainee_ids: list[str] = Field(min_length=1, max_length=100)


class TrainingKnowledgePointCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(min_length=1, max_length=5000)
    course_asset_id: str
    excerpt_text: str = Field(min_length=1, max_length=4000)
    origin_chunk_ref: str | None = None


class TrainingKnowledgePointUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(min_length=1, max_length=5000)


class TrainingAssignmentCreate(BaseModel):
    trainee_id: str
    due_at: datetime | None = None


class TrainingAssignmentBatchCreate(BaseModel):
    trainee_ids: list[str] = Field(min_length=1, max_length=100)
    due_at: datetime | None = None


class TrainingCourseAssetResponse(BaseModel):
    id: str
    research_asset_id: str
    asset_revision_id: str
    title: str
    position: int
    source_id: str | None


class TrainingKnowledgePointResponse(BaseModel):
    id: str
    unit_id: str | None
    title: str
    description: str
    review_status: str
    evidence_excerpt: str
    course_asset_id: str
    origin_chunk_ref: str | None
    assessment_question: dict | None


class TrainingCourseAssigneeResponse(BaseModel):
    user_id: str
    display_name: str
    status: str


class TrainingModuleAssigneeResponse(TrainingCourseAssigneeResponse):
    requires_retraining: bool


class TrainingUnitLessonResponse(BaseModel):
    id: str
    outline: list[str]
    lesson_markdown: str
    evidence: list[dict]
    visuals: list[dict]
    status: str


class TrainingUnitResponse(BaseModel):
    id: str
    title: str
    description: str | None
    position: int
    status: str
    pass_score: int
    course_asset_ids: list[str]
    knowledge_points: list[TrainingKnowledgePointResponse]
    lesson: TrainingUnitLessonResponse | None = None


class TrainingModuleResponse(BaseModel):
    id: str
    title: str
    description: str | None
    position: int
    status: str
    revision_number: int
    units: list[TrainingUnitResponse]
    assignees: list[TrainingModuleAssigneeResponse]


class TrainingCourseVersionResponse(BaseModel):
    id: str
    version_number: int
    status: str
    assets: list[TrainingCourseAssetResponse]
    knowledge_points: list[TrainingKnowledgePointResponse]
    assignees: list[TrainingCourseAssigneeResponse]
    modules: list[TrainingModuleResponse]


class TrainingCourseResponse(BaseModel):
    id: str
    name: str
    description: str | None
    content_language: str
    scope_type: str
    project_id: str | None
    lifecycle_status: str
    can_manage: bool
    version: TrainingCourseVersionResponse


class TrainingAssignmentResponse(BaseModel):
    id: str
    course_id: str
    course_name: str
    course_version_id: str
    status: str
    due_at: datetime | None
    assigned_at: datetime


class TrainingModuleAssignmentResponse(BaseModel):
    id: str
    course_id: str
    course_name: str
    module_id: str
    module_title: str
    status: str
    requires_retraining: bool
    latest_unit_assessment_score: int | None
    assigned_at: datetime


class TrainingOverviewModuleResponse(BaseModel):
    assignment_id: str
    module_id: str
    module_title: str
    status: str
    requires_retraining: bool
    latest_unit_assessment_score: int | None


class TrainingOverviewCourseResponse(BaseModel):
    course_id: str
    course_name: str
    course_assignment_id: str | None
    status: str
    due_at: datetime | None
    next_kind: Literal["module", "course"]
    next_assignment_id: str
    modules: list[TrainingOverviewModuleResponse]


class TrainingModuleLearningResponse(BaseModel):
    assignment_id: str
    course_id: str
    course_name: str
    module_id: str
    module_title: str
    module_description: str | None
    status: str
    requires_retraining: bool
    display_language: Literal["zh-CN", "en-US"]
    units: list[TrainingUnitResponse]


class TrainingUnitQuestionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=8000)
    language: Literal["zh-CN", "en-US"] | None = None


class TrainingUnitMessageResponse(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class TrainingUnitAnswerResponse(BaseModel):
    answer: str
    evidence: list[dict]
    history: list[TrainingUnitMessageResponse]


class TrainingUnitAssessmentAnswerRequest(BaseModel):
    answers: dict[str, str] = Field(min_length=1, max_length=20)
    language: Literal["zh-CN", "en-US"] | None = None


class TrainingUnitAssessmentResponse(BaseModel):
    id: str
    unit_id: str
    attempt_number: int
    questions: list[dict]
    status: str
    pass_score: int
    score: int | None
    passed: bool
    feedback: str | None
    display_language: Literal["zh-CN", "en-US"]


class TrainingAssignmentBatchResponse(BaseModel):
    assignments: list[TrainingAssignmentResponse]
    skipped_trainee_ids: list[str]


class TrainingLearningReportCourseResponse(BaseModel):
    course_id: str
    course_name: str
    assignment_status: str
    assigned_at: datetime
    total_topics: int
    completed_topics: int
    practice_average_score: float | None
    final_assessment_status: str | None
    final_assessment_score: int | None
    last_answered_at: datetime | None


class TrainingLearningReportResponse(BaseModel):
    trainee_id: str
    trainee_name: str
    courses: list[TrainingLearningReportCourseResponse]


class TrainingPracticeStartRequest(BaseModel):
    knowledge_point_id: str


class TrainingPracticeAnswerRequest(BaseModel):
    answer_text: str = Field(min_length=1, max_length=8000)


class TrainingPracticeResponse(BaseModel):
    id: str
    knowledge_point_id: str
    question_text: str
    question_type: Literal["single_choice", "short_answer"]
    options: list[dict[str, str]] | None
    status: str
    answer_text: str | None
    verdict: str | None
    score: int | None
    feedback_text: str | None


class TrainingNextStepResponse(BaseModel):
    knowledge_point_id: str | None
    reason: Literal["not_started", "needs_review", "complete"]


class TrainingFinalAssessmentResponse(BaseModel):
    id: str
    question_text: str
    status: str
    score: int | None
    feedback_text: str | None


class TrainingFinalAssessmentAnswerRequest(BaseModel):
    answer_text: str = Field(min_length=1, max_length=12000)
