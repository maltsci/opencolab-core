import logging
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import ROLE_ADMIN, ROLE_PI
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.asset_revision import AssetRevision
from app.models.project import ResearcherProject
from app.models.research_asset import ResearchAsset
from app.models.training import (
    TrainingAssignment,
    TrainingCourse,
    TrainingCourseAsset,
    TrainingCourseVersion,
    TrainingFinalAssessment,
    TrainingKnowledgeEvidence,
    TrainingKnowledgePoint,
    TrainingModule,
    TrainingModuleAssignment,
    TrainingPracticeAttempt,
    TrainingUnit,
    TrainingUnitAssessmentAttempt,
    TrainingUnitAsset,
    TrainingUnitLesson,
)
from app.models.user import User
from app.schemas.training import (
    TrainingAssignmentCreate,
    TrainingAssignmentBatchCreate,
    TrainingAssignmentBatchResponse,
    TrainingAssignmentResponse,
    TrainingCourseAssetCreate,
    TrainingCourseCreate,
    TrainingCourseResponse,
    TrainingCourseUpdate,
    TrainingKnowledgePointCreate,
    TrainingKnowledgePointUpdate,
    TrainingModuleCreate,
    TrainingModuleUpdate,
    TrainingModuleAssignmentCreate,
    TrainingModuleAssignmentResponse,
    TrainingModuleLearningResponse,
    TrainingOverviewCourseResponse,
    TrainingOverviewModuleResponse,
    TrainingPracticeAnswerRequest,
    TrainingPracticeResponse,
    TrainingPracticeStartRequest,
    TrainingNextStepResponse,
    TrainingModuleResponse,
    TrainingUnitCreate,
    TrainingUnitAssetCreate,
    TrainingUnitLessonUpdate,
    TrainingUnitAnswerResponse,
    TrainingUnitAssessmentAnswerRequest,
    TrainingUnitAssessmentResponse,
    TrainingUnitMessageResponse,
    TrainingUnitQuestionRequest,
    TrainingUnitResponse,
    TrainingFinalAssessmentResponse,
    TrainingFinalAssessmentAnswerRequest,
    TrainingLearningReportCourseResponse,
    TrainingLearningReportResponse,
)
from app.services.training_service import (
    assignment_response,
    answer_unit_question,
    authorize_asset_for_course,
    can_manage_course,
    course_response,
    extract_course_knowledge_points,
    ensure_editable,
    ensure_publishable,
    get_course_or_404,
    get_version_or_404,
    evaluate_practice_answer,
    evaluate_unit_assessment,
    evaluate_final_assessment_answer,
    generate_practice_question,
    generate_course_modules_from_assets,
    generate_unit_lesson,
    generate_unit_assessment,
    practice_response,
    require_course_manager,
    resolve_training_language,
    revise_training_module,
    translate_module_learning_content,
    translate_unit_assessment_content,
    unit_response,
)

router = APIRouter(prefix="/training", tags=["training"])
logger = logging.getLogger(__name__)


def unit_assessment_response(
    attempt: TrainingUnitAssessmentAttempt,
    unit: TrainingUnit,
    *,
    display_language: Literal["zh-CN", "en-US"],
    questions: list[dict] | None = None,
    feedback: str | None = None,
) -> TrainingUnitAssessmentResponse:
    hidden = {"correct_option_id", "reference_answer", "evidence_ids"}
    visible_questions = [
        {key: value for key, value in question.items() if key not in hidden}
        for question in (questions or attempt.questions_json)
    ]
    return TrainingUnitAssessmentResponse(
        id=attempt.id,
        unit_id=unit.id,
        attempt_number=attempt.attempt_number,
        questions=visible_questions,
        status=attempt.status,
        pass_score=unit.pass_score,
        score=attempt.score,
        passed=attempt.passed,
        feedback=feedback if feedback is not None else attempt.feedback_text,
        display_language=display_language,
    )


def _latest_unit_score_subquery():
    return (
        select(TrainingUnitAssessmentAttempt.score)
        .where(
            TrainingUnitAssessmentAttempt.module_assignment_id
            == TrainingModuleAssignment.id,
            TrainingUnitAssessmentAttempt.module_revision
            == TrainingModuleAssignment.required_revision,
            TrainingUnitAssessmentAttempt.status == "evaluated",
        )
        .order_by(
            TrainingUnitAssessmentAttempt.answered_at.desc(),
            TrainingUnitAssessmentAttempt.attempt_number.desc(),
        )
        .limit(1)
        .correlate(TrainingModuleAssignment)
        .scalar_subquery()
    )


@router.get("/me", response_model=list[TrainingOverviewCourseResponse])
async def get_my_training_overview(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    course_rows = list((await db.execute(
        select(TrainingAssignment, TrainingCourseVersion, TrainingCourse)
        .join(
            TrainingCourseVersion,
            TrainingCourseVersion.id == TrainingAssignment.course_version_id,
        )
        .join(TrainingCourse, TrainingCourse.id == TrainingCourseVersion.course_id)
        .where(
            TrainingAssignment.trainee_id == user.id,
            TrainingAssignment.status != "cancelled",
        )
        .order_by(TrainingAssignment.created_at.desc(), TrainingAssignment.id.desc())
    )).all())
    latest_score = _latest_unit_score_subquery()
    module_rows = list((await db.execute(
        select(
            TrainingModuleAssignment,
            TrainingModule,
            TrainingCourseVersion,
            TrainingCourse,
            latest_score.label("latest_unit_assessment_score"),
        )
        .join(TrainingModule, TrainingModule.id == TrainingModuleAssignment.module_id)
        .join(
            TrainingCourseVersion,
            TrainingCourseVersion.id == TrainingModule.course_version_id,
        )
        .join(TrainingCourse, TrainingCourse.id == TrainingCourseVersion.course_id)
        .where(TrainingModuleAssignment.trainee_id == user.id)
        .order_by(
            TrainingModule.position,
            TrainingModuleAssignment.created_at,
            TrainingModuleAssignment.id,
        )
    )).all())

    grouped: dict[str, dict] = {}
    for assignment, _version, course in course_rows:
        grouped[course.id] = {
            "course": course,
            "course_assignment": assignment,
            "modules": [],
            "sort_at": assignment.created_at,
        }
    for assignment, module, _version, course, score in module_rows:
        item = grouped.setdefault(course.id, {
            "course": course,
            "course_assignment": None,
            "modules": [],
            "sort_at": assignment.created_at,
        })
        item["modules"].append((assignment, module, score))
        if assignment.created_at > item["sort_at"]:
            item["sort_at"] = assignment.created_at

    overview: list[TrainingOverviewCourseResponse] = []
    for item in sorted(grouped.values(), key=lambda value: value["sort_at"], reverse=True):
        course = item["course"]
        course_assignment = item["course_assignment"]
        modules = item["modules"]
        incomplete_module = next(
            (row for row in modules if row[0].status != "completed"),
            None,
        )
        if incomplete_module is not None:
            next_kind = "module"
            next_assignment_id = incomplete_module[0].id
        elif course_assignment is not None:
            next_kind = "course"
            next_assignment_id = course_assignment.id
        else:
            next_kind = "module"
            next_assignment_id = modules[-1][0].id

        if course_assignment is not None and course_assignment.status == "completed":
            overview_status = "completed"
        elif modules and all(row[0].status == "completed" for row in modules):
            overview_status = "in_progress" if course_assignment is not None else "completed"
        elif (
            course_assignment is not None and course_assignment.status == "in_progress"
        ) or any(row[0].status != "not_started" for row in modules):
            overview_status = "in_progress"
        else:
            overview_status = "not_started"

        overview.append(TrainingOverviewCourseResponse(
            course_id=course.id,
            course_name=course.name,
            course_assignment_id=course_assignment.id if course_assignment else None,
            status=overview_status,
            due_at=course_assignment.due_at if course_assignment else None,
            next_kind=next_kind,
            next_assignment_id=next_assignment_id,
            modules=[TrainingOverviewModuleResponse(
                assignment_id=assignment.id,
                module_id=module.id,
                module_title=module.title,
                status=assignment.status,
                requires_retraining=assignment.requires_retraining,
                latest_unit_assessment_score=score,
            ) for assignment, module, score in modules],
        ))
    return overview


@router.get(
    "/module-assignments/me",
    response_model=list[TrainingModuleAssignmentResponse],
)
async def list_my_training_module_assignments(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    latest_score = _latest_unit_score_subquery()
    rows = list(
        (
            await db.execute(
                select(
                    TrainingModuleAssignment,
                    TrainingModule,
                    TrainingCourseVersion,
                    TrainingCourse,
                    latest_score.label("latest_unit_assessment_score"),
                )
                .join(TrainingModule, TrainingModule.id == TrainingModuleAssignment.module_id)
                .join(
                    TrainingCourseVersion,
                    TrainingCourseVersion.id == TrainingModule.course_version_id,
                )
                .join(TrainingCourse, TrainingCourse.id == TrainingCourseVersion.course_id)
                .where(TrainingModuleAssignment.trainee_id == user.id)
                .order_by(
                    TrainingModuleAssignment.created_at.desc(),
                    TrainingModuleAssignment.id.desc(),
                )
            )
        ).all()
    )
    return [
        TrainingModuleAssignmentResponse(
            id=assignment.id,
            course_id=course.id,
            course_name=course.name,
            module_id=module.id,
            module_title=module.title,
            status=assignment.status,
            requires_retraining=assignment.requires_retraining,
            latest_unit_assessment_score=latest_unit_assessment_score,
            assigned_at=assignment.created_at,
        )
        for assignment, module, _version, course, latest_unit_assessment_score in rows
    ]


@router.get(
    "/module-assignments/{assignment_id}/learning",
    response_model=TrainingModuleLearningResponse,
)
async def get_training_module_learning_path(
    assignment_id: str,
    language: Literal["zh-CN", "en-US"] | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    assignment = await db.get(TrainingModuleAssignment, assignment_id)
    if assignment is None or assignment.trainee_id != user.id:
        raise HTTPException(status_code=404, detail="Training module assignment not found")
    module = await db.get(TrainingModule, assignment.module_id)
    if module is None:
        raise HTTPException(status_code=404, detail="Training module not found")
    version = await db.get(TrainingCourseVersion, module.course_version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Training course version not found")
    course = await get_course_or_404(db, version.course_id)
    units = list(
        (
            await db.scalars(
                select(TrainingUnit)
                .where(
                    TrainingUnit.module_id == module.id,
                    TrainingUnit.status == "approved",
                )
                .order_by(TrainingUnit.position, TrainingUnit.id)
            )
        ).all()
    )
    for unit in units:
        bindings = list(
            (
                await db.scalars(
                    select(TrainingUnitAsset).where(TrainingUnitAsset.unit_id == unit.id)
                )
            ).all()
        )
        for binding in bindings:
            course_asset = await db.get(TrainingCourseAsset, binding.course_asset_id)
            if course_asset is None:
                raise HTTPException(status_code=404, detail="Course material unavailable")
            asset = await db.get(ResearchAsset, course_asset.research_asset_id)
            revision = await db.get(AssetRevision, course_asset.asset_revision_id)
            if asset is None or revision is None:
                raise HTTPException(status_code=404, detail="Course material unavailable")
            await authorize_asset_for_course(db, user, asset, revision)
    if assignment.status == "not_started":
        assignment.status = "in_progress"
        await db.commit()
    display_language = language or resolve_training_language(
        course.content_language, f"{course.name}\n{module.title}"
    )
    try:
        course_name, module_title, module_description, translated_units = (
            await translate_module_learning_content(
                db,
                course=course,
                module=module,
                units=units,
                target_language=display_language,
            )
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Training content translation failed")
        raise HTTPException(
            status_code=502, detail="Training content translation failed"
        ) from exc
    return TrainingModuleLearningResponse(
        assignment_id=assignment.id,
        course_id=course.id,
        course_name=course_name,
        module_id=module.id,
        module_title=module_title,
        module_description=module_description,
        status=assignment.status,
        requires_retraining=assignment.requires_retraining,
        display_language=display_language,
        units=translated_units,
    )


@router.post(
    "/module-assignments/{assignment_id}/units/{unit_id}/ask",
    response_model=TrainingUnitAnswerResponse,
)
async def ask_training_unit_question(
    assignment_id: str,
    unit_id: str,
    body: TrainingUnitQuestionRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    assignment = await db.get(TrainingModuleAssignment, assignment_id)
    if assignment is None or assignment.trainee_id != user.id:
        raise HTTPException(status_code=404, detail="Training module assignment not found")
    unit = await db.get(TrainingUnit, unit_id)
    if unit is None or unit.module_id != assignment.module_id or unit.status != "approved":
        raise HTTPException(status_code=404, detail="Training unit not found")
    try:
        answer, evidence, history = await answer_unit_question(
            db,
            assignment=assignment,
            unit=unit,
            user=user,
            question=body.question,
            display_language=body.language,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Training unit answer failed") from exc
    return TrainingUnitAnswerResponse(
        answer=answer,
        evidence=evidence,
        history=[
            TrainingUnitMessageResponse(role=item.role, content=item.content)
            for item in history
        ],
    )


@router.post(
    "/module-assignments/{assignment_id}/units/{unit_id}/assessment",
    response_model=TrainingUnitAssessmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def start_training_unit_assessment(
    assignment_id: str,
    unit_id: str,
    language: Literal["zh-CN", "en-US"] | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    assignment = await db.get(TrainingModuleAssignment, assignment_id)
    if assignment is None or assignment.trainee_id != user.id:
        raise HTTPException(status_code=404, detail="Training module assignment not found")
    unit = await db.get(TrainingUnit, unit_id)
    if unit is None or unit.module_id != assignment.module_id or unit.status != "approved":
        raise HTTPException(status_code=404, detail="Training unit not found")
    try:
        attempt = await generate_unit_assessment(
            db,
            assignment=assignment,
            unit=unit,
            user=user,
            display_language=language,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Training unit assessment generation failed") from exc
    display_language = language or resolve_training_language(
        "auto", "\n".join(item["prompt"] for item in attempt.questions_json)
    )
    return unit_assessment_response(
        attempt, unit, display_language=display_language
    )


@router.get(
    "/unit-assessments/{attempt_id}",
    response_model=TrainingUnitAssessmentResponse,
)
async def get_training_unit_assessment(
    attempt_id: str,
    language: Literal["zh-CN", "en-US"] = Query(),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    attempt = await db.get(TrainingUnitAssessmentAttempt, attempt_id)
    if attempt is None:
        raise HTTPException(status_code=404, detail="Training unit assessment not found")
    assignment = await db.get(TrainingModuleAssignment, attempt.module_assignment_id)
    if assignment is None or assignment.trainee_id != user.id:
        raise HTTPException(status_code=404, detail="Training unit assessment not found")
    unit = await db.get(TrainingUnit, attempt.unit_id)
    if unit is None or unit.module_id != assignment.module_id:
        raise HTTPException(status_code=404, detail="Training unit not found")
    questions, feedback = await translate_unit_assessment_content(
        db,
        attempt=attempt,
        questions=attempt.questions_json,
        feedback=attempt.feedback_text,
        target_language=language,
    )
    return unit_assessment_response(
        attempt,
        unit,
        display_language=language,
        questions=questions,
        feedback=feedback,
    )


@router.post(
    "/unit-assessments/{attempt_id}/answer",
    response_model=TrainingUnitAssessmentResponse,
)
async def answer_training_unit_assessment(
    attempt_id: str,
    body: TrainingUnitAssessmentAnswerRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    attempt = await db.get(TrainingUnitAssessmentAttempt, attempt_id)
    if attempt is None:
        raise HTTPException(status_code=404, detail="Training unit assessment not found")
    assignment = await db.get(TrainingModuleAssignment, attempt.module_assignment_id)
    if assignment is None or assignment.trainee_id != user.id:
        raise HTTPException(status_code=404, detail="Training unit assessment not found")
    unit = await db.get(TrainingUnit, attempt.unit_id)
    if unit is None or unit.module_id != assignment.module_id:
        raise HTTPException(status_code=404, detail="Training unit not found")
    try:
        await evaluate_unit_assessment(
            db,
            attempt=attempt,
            assignment=assignment,
            unit=unit,
            answers={key: value.strip() for key, value in body.answers.items()},
            display_language=body.language,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Training unit assessment grading failed") from exc
    display_language = body.language or resolve_training_language(
        "auto", attempt.feedback_text or ""
    )
    questions = attempt.questions_json
    feedback = attempt.feedback_text
    if body.language is not None:
        questions, feedback = await translate_unit_assessment_content(
            db,
            attempt=attempt,
            questions=attempt.questions_json,
            feedback=attempt.feedback_text,
            target_language=body.language,
        )
    return unit_assessment_response(
        attempt,
        unit,
        display_language=display_language,
        questions=questions,
        feedback=feedback,
    )


@router.post(
    "/courses/{course_id}/modules",
    response_model=TrainingModuleResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_training_module(
    course_id: str,
    body: TrainingModuleCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    course = await get_course_or_404(db, course_id)
    await require_course_manager(db, user, course)
    version = await get_version_or_404(db, course.id)
    position = (await db.scalar(select(func.count(TrainingModule.id)).where(
        TrainingModule.course_version_id == version.id
    ))) or 0
    module = TrainingModule(
        course_version_id=version.id,
        title=body.title.strip(),
        description=body.description.strip() if body.description else None,
        position=position,
        created_by=user.id,
    )
    db.add(module)
    await db.commit()
    return TrainingModuleResponse(
        id=module.id, title=module.title, description=module.description,
        position=module.position, status=module.status,
        revision_number=module.revision_number, units=[], assignees=[],
    )


@router.put(
    "/courses/{course_id}/modules/{module_id}",
    response_model=TrainingModuleResponse,
)
async def update_training_module(
    course_id: str,
    module_id: str,
    body: TrainingModuleUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    course = await get_course_or_404(db, course_id)
    await require_course_manager(db, user, course)
    version = await get_version_or_404(db, course.id)
    module = await db.get(TrainingModule, module_id)
    if module is None or module.course_version_id != version.id:
        raise HTTPException(status_code=404, detail="Training module not found")
    title = body.title.strip()
    description = body.description.strip() if body.description else None
    if title != module.title or description != module.description:
        module.title = title
        module.description = description
        if version.status == "published":
            await revise_training_module(db, module)
    await db.commit()
    refreshed = await course_response(db, course, user)
    return next(item for item in refreshed.version.modules if item.id == module.id)


@router.post(
    "/courses/{course_id}/modules/generate",
    response_model=TrainingCourseResponse,
)
async def generate_training_course_modules(
    course_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    course = await get_course_or_404(db, course_id)
    await require_course_manager(db, user, course)
    version = await get_version_or_404(db, course.id)
    try:
        await generate_course_modules_from_assets(
            db, course_version=version, user=user
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail="Training course structure generation failed"
        ) from exc
    return await course_response(db, course, user)


@router.post(
    "/courses/{course_id}/modules/{module_id}/assignments",
    response_model=TrainingModuleResponse,
)
async def assign_training_module(
    course_id: str,
    module_id: str,
    body: TrainingModuleAssignmentCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    course = await get_course_or_404(db, course_id)
    await require_course_manager(db, user, course)
    version = await get_version_or_404(db, course.id)
    module = await db.get(TrainingModule, module_id)
    if module is None or module.course_version_id != version.id:
        raise HTTPException(status_code=404, detail="Training module not found")
    for trainee_id in dict.fromkeys(body.trainee_ids):
        trainee = await db.get(User, trainee_id)
        if trainee is None:
            continue
        exists = await db.scalar(select(TrainingModuleAssignment).where(
            TrainingModuleAssignment.module_id == module.id,
            TrainingModuleAssignment.trainee_id == trainee.id,
        ))
        if exists is None:
            db.add(TrainingModuleAssignment(
                module_id=module.id,
                trainee_id=trainee.id,
                assigned_by=user.id,
                required_revision=module.revision_number,
            ))
    await db.commit()
    refreshed = await course_response(db, course, user)
    return next(item for item in refreshed.version.modules if item.id == module.id)


@router.post(
    "/courses/{course_id}/modules/{module_id}/units",
    response_model=TrainingUnitResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_training_unit(
    course_id: str,
    module_id: str,
    body: TrainingUnitCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    course = await get_course_or_404(db, course_id)
    await require_course_manager(db, user, course)
    version = await get_version_or_404(db, course.id)
    module = await db.get(TrainingModule, module_id)
    if module is None or module.course_version_id != version.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Training module not found")
    position = (await db.scalar(select(func.count(TrainingUnit.id)).where(
        TrainingUnit.module_id == module.id
    ))) or 0
    unit = TrainingUnit(
        module_id=module.id,
        title=body.title.strip(),
        description=body.description.strip() if body.description else None,
        position=position,
        pass_score=body.pass_score,
        created_by=user.id,
    )
    db.add(unit)
    await db.commit()
    return await unit_response(db, unit)


@router.put(
    "/courses/{course_id}/modules/{module_id}/units/{unit_id}/assets",
    response_model=TrainingUnitResponse,
)
@router.post(
    "/courses/{course_id}/modules/{module_id}/units/{unit_id}/assets",
    response_model=TrainingUnitResponse,
)
async def bind_training_unit_assets(
    course_id: str,
    module_id: str,
    unit_id: str,
    body: TrainingUnitAssetCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    course = await get_course_or_404(db, course_id)
    await require_course_manager(db, user, course)
    version = await get_version_or_404(db, course.id)
    module = await db.get(TrainingModule, module_id)
    unit = await db.get(TrainingUnit, unit_id)
    if module is None or module.course_version_id != version.id or unit is None or unit.module_id != module.id:
        raise HTTPException(status_code=404, detail="Training unit not found")
    desired_ids = list(dict.fromkeys(body.course_asset_ids))
    for course_asset_id in desired_ids:
        course_asset = await db.get(TrainingCourseAsset, course_asset_id)
        if course_asset is None or course_asset.course_version_id != version.id:
            raise HTTPException(status_code=422, detail="Course asset is not bound to this version")
    existing_bindings = list((await db.scalars(select(TrainingUnitAsset).where(
        TrainingUnitAsset.unit_id == unit.id
    ))).all())
    existing_ids = {binding.course_asset_id for binding in existing_bindings}
    desired_id_set = set(desired_ids)
    if existing_ids != desired_id_set:
        point_ids = list((await db.scalars(select(TrainingKnowledgePoint.id).where(
            TrainingKnowledgePoint.unit_id == unit.id
        ))).all())
        if point_ids:
            await db.execute(delete(TrainingKnowledgeEvidence).where(
                TrainingKnowledgeEvidence.knowledge_point_id.in_(point_ids)
            ))
            await db.execute(delete(TrainingKnowledgePoint).where(
                TrainingKnowledgePoint.id.in_(point_ids)
            ))
        await db.execute(delete(TrainingUnitLesson).where(
            TrainingUnitLesson.unit_id == unit.id
        ))
        await db.execute(delete(TrainingUnitAsset).where(
            TrainingUnitAsset.unit_id == unit.id,
            TrainingUnitAsset.course_asset_id.not_in(desired_id_set),
        ))
        for course_asset_id in desired_ids:
            if course_asset_id in existing_ids:
                continue
            db.add(TrainingUnitAsset(
                unit_id=unit.id,
                course_asset_id=course_asset_id,
                created_by=user.id,
            ))
        unit.status = "draft"
    await db.commit()
    return await unit_response(db, unit)


@router.post(
    "/courses/{course_id}/modules/{module_id}/units/{unit_id}/lesson/generate",
    response_model=TrainingUnitResponse,
)
async def create_training_unit_lesson(
    course_id: str,
    module_id: str,
    unit_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    course = await get_course_or_404(db, course_id)
    await require_course_manager(db, user, course)
    version = await get_version_or_404(db, course.id)
    module = await db.get(TrainingModule, module_id)
    unit = await db.get(TrainingUnit, unit_id)
    if module is None or module.course_version_id != version.id or unit is None or unit.module_id != module.id:
        raise HTTPException(status_code=404, detail="Training unit not found")
    try:
        await generate_unit_lesson(db, unit=unit, user=user)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Training unit lesson generation failed") from exc
    return await unit_response(db, unit)


@router.put(
    "/courses/{course_id}/modules/{module_id}/units/{unit_id}/lesson",
    response_model=TrainingUnitResponse,
)
async def update_training_unit_lesson(
    course_id: str,
    module_id: str,
    unit_id: str,
    body: TrainingUnitLessonUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    course = await get_course_or_404(db, course_id)
    await require_course_manager(db, user, course)
    version = await get_version_or_404(db, course.id)
    module = await db.get(TrainingModule, module_id)
    unit = await db.get(TrainingUnit, unit_id)
    if (
        module is None
        or module.course_version_id != version.id
        or unit is None
        or unit.module_id != module.id
    ):
        raise HTTPException(status_code=404, detail="Training unit not found")
    lesson = await db.scalar(
        select(TrainingUnitLesson).where(TrainingUnitLesson.unit_id == unit.id)
    )
    if lesson is None:
        raise HTTPException(status_code=404, detail="Training unit lesson not found")
    if lesson.status != "pending":
        raise HTTPException(
            status_code=409, detail="Approved training unit lesson is not editable"
        )
    lesson_markdown = body.lesson_markdown.strip()
    if not lesson_markdown:
        raise HTTPException(status_code=422, detail="Training unit lesson cannot be blank")
    lesson.lesson_markdown = lesson_markdown
    await db.commit()
    return await unit_response(db, unit)


@router.post(
    "/courses/{course_id}/modules/{module_id}/units/{unit_id}/lesson/approve",
    response_model=TrainingUnitResponse,
)
async def approve_training_unit_lesson(
    course_id: str,
    module_id: str,
    unit_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    course = await get_course_or_404(db, course_id)
    await require_course_manager(db, user, course)
    version = await get_version_or_404(db, course.id)
    module = await db.get(TrainingModule, module_id)
    unit = await db.get(TrainingUnit, unit_id)
    if module is None or module.course_version_id != version.id or unit is None or unit.module_id != module.id:
        raise HTTPException(status_code=404, detail="Training unit not found")
    lesson = await db.scalar(select(TrainingUnitLesson).where(TrainingUnitLesson.unit_id == unit.id))
    if lesson is None:
        raise HTTPException(status_code=404, detail="Training unit lesson not found")
    if version.status == "published" and lesson.status != "approved":
        await revise_training_module(db, module)
    lesson.status = "approved"
    unit.status = "approved"
    points = list((await db.scalars(select(TrainingKnowledgePoint).where(
        TrainingKnowledgePoint.unit_id == unit.id,
        TrainingKnowledgePoint.review_status == "pending",
    ))).all())
    for point in points:
        point.review_status = "approved"
    await db.commit()
    return await unit_response(db, unit)


@router.get("/reports/{trainee_id}", response_model=TrainingLearningReportResponse)
async def get_training_learning_report(
    trainee_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if user.role not in {ROLE_ADMIN, ROLE_PI}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Training report access denied")
    trainee = await db.get(User, trainee_id)
    if trainee is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trainee not found")
    rows = list(
        (
            await db.execute(
                select(TrainingAssignment, TrainingCourseVersion, TrainingCourse)
                .join(TrainingCourseVersion, TrainingCourseVersion.id == TrainingAssignment.course_version_id)
                .join(TrainingCourse, TrainingCourse.id == TrainingCourseVersion.course_id)
                .where(TrainingAssignment.trainee_id == trainee.id, TrainingAssignment.status != "cancelled")
                .order_by(TrainingAssignment.created_at.desc(), TrainingAssignment.id.desc())
            )
        ).all()
    )
    courses: list[TrainingLearningReportCourseResponse] = []
    for assignment, version, course in rows:
        point_ids = list((await db.scalars(select(TrainingKnowledgePoint.id).where(
            TrainingKnowledgePoint.course_version_id == version.id,
            TrainingKnowledgePoint.review_status == "approved",
        ))).all())
        attempts = list((await db.scalars(select(TrainingPracticeAttempt).where(
            TrainingPracticeAttempt.assignment_id == assignment.id,
            TrainingPracticeAttempt.status == "evaluated",
        ))).all())
        scores = [attempt.score for attempt in attempts if attempt.score is not None]
        completed_topic_ids = {attempt.knowledge_point_id for attempt in attempts}
        final_assessment = await db.scalar(select(TrainingFinalAssessment).where(
            TrainingFinalAssessment.assignment_id == assignment.id
        ))
        answered_at = [attempt.answered_at for attempt in attempts if attempt.answered_at is not None]
        if final_assessment is not None and final_assessment.answered_at is not None:
            answered_at.append(final_assessment.answered_at)
        courses.append(TrainingLearningReportCourseResponse(
            course_id=course.id,
            course_name=course.name,
            assignment_status=assignment.status,
            assigned_at=assignment.created_at,
            total_topics=len(point_ids),
            completed_topics=len(completed_topic_ids.intersection(point_ids)),
            practice_average_score=round(sum(scores) / len(scores), 1) if scores else None,
            final_assessment_status=final_assessment.status if final_assessment else None,
            final_assessment_score=final_assessment.score if final_assessment else None,
            last_answered_at=max(answered_at) if answered_at else None,
        ))
    return TrainingLearningReportResponse(
        trainee_id=trainee.id,
        trainee_name=trainee.display_name or trainee.username,
        courses=courses,
    )


@router.get("/courses", response_model=list[TrainingCourseResponse])
async def list_training_courses(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    courses = list(
        (
            await db.scalars(
                select(TrainingCourse)
                .where(TrainingCourse.lifecycle_status == "active")
                .order_by(TrainingCourse.updated_at.desc(), TrainingCourse.id.desc())
            )
        ).all()
    )
    return [
        await course_response(db, course, user)
        for course in courses
        if await can_manage_course(db, user, course)
    ]


@router.post("/courses", response_model=TrainingCourseResponse, status_code=status.HTTP_201_CREATED)
async def create_training_course(
    body: TrainingCourseCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.scope_type == "lab" and user.role not in {ROLE_ADMIN, ROLE_PI}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Lab course creation denied")
    if body.scope_type == "project" and body.project_id is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Project course requires project_id")
    course = TrainingCourse(
        name=body.name.strip(),
        description=body.description,
        content_language=body.content_language,
        scope_type=body.scope_type,
        project_id=body.project_id,
        created_by=user.id,
    )
    if not course.name:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Course name is required")
    if body.scope_type == "project" and not await can_manage_course(db, user, course):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Project course creation denied")
    db.add(course)
    await db.flush()
    version = TrainingCourseVersion(
        course_id=course.id,
        version_number=1,
        description_snapshot=course.description,
        created_by=user.id,
    )
    db.add(version)
    await db.commit()
    return await course_response(db, course, user)


async def get_assignment_practice_context(
    db: AsyncSession, assignment_id: str, user: User, knowledge_point_id: str
) -> tuple[TrainingAssignment, TrainingKnowledgePoint, TrainingKnowledgeEvidence]:
    assignment = await db.get(TrainingAssignment, assignment_id)
    if assignment is None or assignment.trainee_id != user.id or assignment.status == "cancelled":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Training assignment not found")
    version = await db.get(TrainingCourseVersion, assignment.course_version_id)
    if version is None or version.status != "published":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Training course is not published")
    point = await db.get(TrainingKnowledgePoint, knowledge_point_id)
    if (
        point is None
        or point.course_version_id != version.id
        or point.review_status != "approved"
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Training knowledge point not found")
    evidence = await db.scalar(
        select(TrainingKnowledgeEvidence).where(
            TrainingKnowledgeEvidence.knowledge_point_id == point.id
        ).order_by(TrainingKnowledgeEvidence.created_at, TrainingKnowledgeEvidence.id).limit(1)
    )
    if evidence is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Training knowledge point has no evidence")
    course_asset = await db.get(TrainingCourseAsset, evidence.course_asset_id)
    if course_asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course material unavailable")
    asset = await db.get(ResearchAsset, course_asset.research_asset_id)
    revision = await db.get(AssetRevision, course_asset.asset_revision_id)
    if asset is None or revision is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course material unavailable")
    await authorize_asset_for_course(db, user, asset, revision)
    return assignment, point, evidence


async def _next_training_step(
    db: AsyncSession,
    assignment: TrainingAssignment,
) -> TrainingNextStepResponse:
    points = list((await db.scalars(
        select(TrainingKnowledgePoint)
        .where(
            TrainingKnowledgePoint.course_version_id == assignment.course_version_id,
            TrainingKnowledgePoint.review_status == "approved",
        )
        .order_by(TrainingKnowledgePoint.created_at, TrainingKnowledgePoint.id)
    )).all())
    attempts = list((await db.scalars(
        select(TrainingPracticeAttempt)
        .where(TrainingPracticeAttempt.assignment_id == assignment.id, TrainingPracticeAttempt.status == "evaluated")
        .order_by(TrainingPracticeAttempt.answered_at.desc(), TrainingPracticeAttempt.id.desc())
    )).all())
    latest_scores = {}
    for attempt in attempts:
        latest_scores.setdefault(attempt.knowledge_point_id, attempt.score or 0)
    unstarted = next((point for point in points if point.id not in latest_scores), None)
    if unstarted is not None:
        return TrainingNextStepResponse(knowledge_point_id=unstarted.id, reason="not_started")
    weak = min(points, key=lambda point: latest_scores.get(point.id, 100), default=None)
    if weak is not None and latest_scores.get(weak.id, 100) < 80:
        return TrainingNextStepResponse(knowledge_point_id=weak.id, reason="needs_review")
    return TrainingNextStepResponse(knowledge_point_id=None, reason="complete")


@router.get("/assignments/{assignment_id}/next-step", response_model=TrainingNextStepResponse)
async def get_next_training_step(
    assignment_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    assignment = await db.get(TrainingAssignment, assignment_id)
    if assignment is None or assignment.trainee_id != user.id or assignment.status == "cancelled":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Training assignment not found")
    return await _next_training_step(db, assignment)


@router.post("/assignments/{assignment_id}/final-assessment", response_model=TrainingFinalAssessmentResponse, status_code=status.HTTP_201_CREATED)
async def create_final_assessment(
    assignment_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    assignment = await db.get(TrainingAssignment, assignment_id)
    if assignment is None or assignment.trainee_id != user.id or assignment.status == "cancelled":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Training assignment not found")
    next_step = await _next_training_step(db, assignment)
    if next_step.reason != "complete":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Complete all topic practices first",
        )
    existing = await db.scalar(select(TrainingFinalAssessment).where(TrainingFinalAssessment.assignment_id == assignment.id))
    if existing is not None:
        return TrainingFinalAssessmentResponse(id=existing.id, question_text=existing.question_text, status=existing.status, score=existing.score, feedback_text=existing.feedback_text)
    points = list((await db.scalars(select(TrainingKnowledgePoint).where(
        TrainingKnowledgePoint.course_version_id == assignment.course_version_id,
        TrainingKnowledgePoint.review_status == "approved",
    ).order_by(TrainingKnowledgePoint.created_at, TrainingKnowledgePoint.id))).all())
    if not points:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Training course has no knowledge points")
    titles = "; ".join(point.title for point in points)
    version = await db.get(TrainingCourseVersion, assignment.course_version_id)
    course = await db.get(TrainingCourse, version.course_id) if version else None
    if course is None:
        raise HTTPException(status_code=500, detail="Training assignment course missing")
    resolved_language = resolve_training_language(course.content_language, titles)
    question_text = (
        f"请综合说明你将如何应用以下课程主题：{titles}"
        if resolved_language == "zh-CN"
        else f"Provide an integrated explanation of how you would apply these course topics: {titles}"
    )
    assessment = TrainingFinalAssessment(
        assignment_id=assignment.id,
        question_text=question_text,
    )
    db.add(assessment)
    await db.commit()
    return TrainingFinalAssessmentResponse(id=assessment.id, question_text=assessment.question_text, status=assessment.status, score=None, feedback_text=None)


@router.post("/final-assessments/{assessment_id}/answer", response_model=TrainingFinalAssessmentResponse)
async def answer_final_assessment(
    assessment_id: str,
    body: TrainingFinalAssessmentAnswerRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    assessment = await db.get(TrainingFinalAssessment, assessment_id)
    if assessment is None or assessment.status != "pending":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Training final assessment not found")
    assignment = await db.get(TrainingAssignment, assessment.assignment_id)
    if assignment is None or assignment.trainee_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Training final assessment not found")
    points = list((await db.scalars(select(TrainingKnowledgePoint).where(
        TrainingKnowledgePoint.course_version_id == assignment.course_version_id,
        TrainingKnowledgePoint.review_status == "approved",
    ))).all())
    evidence = list((await db.scalars(select(TrainingKnowledgeEvidence).join(
        TrainingKnowledgePoint, TrainingKnowledgePoint.id == TrainingKnowledgeEvidence.knowledge_point_id
    ).where(
        TrainingKnowledgePoint.course_version_id == assignment.course_version_id,
        TrainingKnowledgePoint.review_status == "approved",
    ))).all())
    for evidence_item in evidence:
        course_asset = await db.get(TrainingCourseAsset, evidence_item.course_asset_id)
        if course_asset is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course material unavailable")
        asset = await db.get(ResearchAsset, course_asset.research_asset_id)
        revision = await db.get(AssetRevision, course_asset.asset_revision_id)
        if asset is None or revision is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course material unavailable")
        await authorize_asset_for_course(db, user, asset, revision)
    try:
        score, feedback = await evaluate_final_assessment_answer(
            db, question_text=assessment.question_text, points=points, evidence=evidence, answer_text=body.answer_text.strip()
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Final assessment evaluation failed") from exc
    assessment.answer_text = body.answer_text.strip()
    assessment.score = score
    assessment.feedback_text = feedback
    assessment.status = "evaluated"
    assessment.answered_at = datetime.now(UTC)
    if score >= 80:
        assignment.status = "completed"
    await db.commit()
    return TrainingFinalAssessmentResponse(id=assessment.id, question_text=assessment.question_text, status=assessment.status, score=assessment.score, feedback_text=assessment.feedback_text)


@router.post("/assignments/{assignment_id}/practice", response_model=TrainingPracticeResponse, status_code=status.HTTP_201_CREATED)
async def start_training_practice(
    assignment_id: str,
    body: TrainingPracticeStartRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    assignment, point, evidence = await get_assignment_practice_context(db, assignment_id, user, body.knowledge_point_id)
    existing = await db.scalar(
        select(TrainingPracticeAttempt).where(
            TrainingPracticeAttempt.assignment_id == assignment.id,
            TrainingPracticeAttempt.knowledge_point_id == point.id,
            TrainingPracticeAttempt.status == "pending",
        )
    )
    if existing is not None:
        return practice_response(existing)
    attempt_number = (await db.scalar(select(func.count(TrainingPracticeAttempt.id)).where(
        TrainingPracticeAttempt.assignment_id == assignment.id,
        TrainingPracticeAttempt.knowledge_point_id == point.id,
    ))) or 0
    try:
        question_text = await generate_practice_question(db, point=point, evidence=evidence)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Practice question generation failed") from exc
    attempt = TrainingPracticeAttempt(
        assignment_id=assignment.id,
        knowledge_point_id=point.id,
        attempt_number=attempt_number + 1,
        question_text=question_text,
    )
    assignment.status = "in_progress"
    db.add(attempt)
    await db.commit()
    return practice_response(attempt)


@router.post("/practice/{attempt_id}/answer", response_model=TrainingPracticeResponse)
async def answer_training_practice(
    attempt_id: str,
    body: TrainingPracticeAnswerRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    attempt = await db.get(TrainingPracticeAttempt, attempt_id)
    if attempt is None or attempt.status != "pending":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Training practice attempt not found")
    assignment, point, evidence = await get_assignment_practice_context(
        db, attempt.assignment_id, user, attempt.knowledge_point_id
    )
    try:
        verdict, score, feedback = await evaluate_practice_answer(
        db,
        point=point,
        evidence=evidence,
        question_payload=attempt.question_text,
        answer_text=body.answer_text.strip(),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Practice evaluation failed") from exc
    attempt.answer_text = body.answer_text.strip()
    attempt.status = "evaluated"
    attempt.verdict = verdict
    attempt.score = score
    attempt.feedback_text = feedback
    attempt.answered_at = datetime.now(UTC)
    await db.commit()
    return practice_response(attempt)


@router.get("/courses/{course_id}", response_model=TrainingCourseResponse)
async def get_training_course(
    course_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    course = await get_course_or_404(db, course_id)
    await require_course_manager(db, user, course)
    return await course_response(db, course, user)


@router.put("/courses/{course_id}", response_model=TrainingCourseResponse)
async def update_training_course(
    course_id: str,
    body: TrainingCourseUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    course = await get_course_or_404(db, course_id)
    await require_course_manager(db, user, course)
    version = await get_version_or_404(db, course.id)
    ensure_editable(version)
    name = body.name.strip()
    if not name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Course name is required",
        )
    course.name = name
    course.description = body.description.strip() if body.description else None
    if body.content_language is not None:
        course.content_language = body.content_language
    version.description_snapshot = course.description
    await db.commit()
    return await course_response(db, course, user)


@router.post("/courses/{course_id}/assets", response_model=TrainingCourseResponse)
async def add_course_asset(
    course_id: str,
    body: TrainingCourseAssetCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    course = await get_course_or_404(db, course_id)
    await require_course_manager(db, user, course)
    version = await get_version_or_404(db, course.id)
    ensure_editable(version)
    asset_ids = list(dict.fromkeys(body.research_asset_ids))
    assets: list[tuple[ResearchAsset, AssetRevision]] = []
    for asset_id in asset_ids:
        asset = await db.get(ResearchAsset, asset_id)
        if asset is None or asset.current_revision_id is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Research asset not found")
        revision = await db.get(AssetRevision, asset.current_revision_id)
        if revision is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Asset revision unavailable")
        await authorize_asset_for_course(db, user, asset, revision)
        existing = await db.scalar(
            select(TrainingCourseAsset).where(
                TrainingCourseAsset.course_version_id == version.id,
                TrainingCourseAsset.research_asset_id == asset.id,
            )
        )
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Course asset already bound")
        assets.append((asset, revision))
    position = await db.scalar(
        select(func.count(TrainingCourseAsset.id)).where(
            TrainingCourseAsset.course_version_id == version.id
        )
    )
    for offset, (asset, revision) in enumerate(assets):
        db.add(TrainingCourseAsset(
            course_version_id=version.id,
            research_asset_id=asset.id,
            asset_revision_id=revision.id,
            position=(position or 0) + offset,
            added_by=user.id,
        ))
    await db.commit()
    return await course_response(db, course, user)


@router.delete(
    "/courses/{course_id}/assets/{course_asset_id}",
    response_model=TrainingCourseResponse,
)
async def remove_course_asset(
    course_id: str,
    course_asset_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    course = await get_course_or_404(db, course_id)
    await require_course_manager(db, user, course)
    version = await get_version_or_404(db, course.id)
    ensure_editable(version)
    course_asset = await db.get(TrainingCourseAsset, course_asset_id)
    if course_asset is None or course_asset.course_version_id != version.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Training course asset not found",
        )

    affected_unit_ids = list(
        (
            await db.scalars(
                select(TrainingUnitAsset.unit_id).where(
                    TrainingUnitAsset.course_asset_id == course_asset.id
                )
            )
        ).all()
    )
    if affected_unit_ids:
        await db.execute(
            delete(TrainingUnitLesson).where(
                TrainingUnitLesson.unit_id.in_(affected_unit_ids)
            )
        )
    await db.execute(
        delete(TrainingUnitAsset).where(
            TrainingUnitAsset.course_asset_id == course_asset.id
        )
    )

    point_ids = list(
        (
            await db.scalars(
                select(TrainingKnowledgeEvidence.knowledge_point_id).where(
                    TrainingKnowledgeEvidence.course_asset_id == course_asset.id
                )
            )
        ).all()
    )
    await db.execute(
        delete(TrainingKnowledgeEvidence).where(
            TrainingKnowledgeEvidence.course_asset_id == course_asset.id
        )
    )
    if point_ids:
        await db.execute(
            delete(TrainingKnowledgePoint).where(
                TrainingKnowledgePoint.id.in_(point_ids),
            )
        )

    await db.delete(course_asset)
    await db.commit()
    return await course_response(db, course, user)


@router.post("/courses/{course_id}/knowledge-points", response_model=TrainingCourseResponse)
async def add_knowledge_point(
    course_id: str,
    body: TrainingKnowledgePointCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    course = await get_course_or_404(db, course_id)
    await require_course_manager(db, user, course)
    version = await get_version_or_404(db, course.id)
    ensure_editable(version)
    course_asset = await db.get(TrainingCourseAsset, body.course_asset_id)
    if course_asset is None or course_asset.course_version_id != version.id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Course asset is not bound to this version")
    point = TrainingKnowledgePoint(
        course_version_id=version.id,
        title=body.title.strip(),
        description=body.description.strip(),
        created_by=user.id,
    )
    db.add(point)
    await db.flush()
    db.add(
        TrainingKnowledgeEvidence(
            knowledge_point_id=point.id,
            course_asset_id=course_asset.id,
            excerpt_text=body.excerpt_text.strip(),
            origin_chunk_ref=body.origin_chunk_ref,
            created_by=user.id,
        )
    )
    await db.commit()
    return await course_response(db, course, user)


@router.post("/courses/{course_id}/knowledge-points/extract", response_model=TrainingCourseResponse)
async def extract_knowledge_points(
    course_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    course = await get_course_or_404(db, course_id)
    await require_course_manager(db, user, course)
    version = await get_version_or_404(db, course.id)
    ensure_editable(version)
    try:
        await extract_course_knowledge_points(db, course_version=version, user=user)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Knowledge point extraction failed") from exc
    return await course_response(db, course, user)


@router.post(
    "/courses/{course_id}/knowledge-points/{knowledge_point_id}/approve",
    response_model=TrainingCourseResponse,
)
async def approve_knowledge_point(
    course_id: str,
    knowledge_point_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    course = await get_course_or_404(db, course_id)
    await require_course_manager(db, user, course)
    version = await get_version_or_404(db, course.id)
    ensure_editable(version)
    point = await db.get(TrainingKnowledgePoint, knowledge_point_id)
    if point is None or point.course_version_id != version.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Training knowledge point not found")
    if point.review_status == "pending":
        point.review_status = "approved"
        await db.commit()
    return await course_response(db, course, user)


@router.put(
    "/courses/{course_id}/knowledge-points/{knowledge_point_id}",
    response_model=TrainingCourseResponse,
)
async def update_knowledge_point(
    course_id: str,
    knowledge_point_id: str,
    body: TrainingKnowledgePointUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    course = await get_course_or_404(db, course_id)
    await require_course_manager(db, user, course)
    version = await get_version_or_404(db, course.id)
    ensure_editable(version)
    point = await db.get(TrainingKnowledgePoint, knowledge_point_id)
    if point is None or point.course_version_id != version.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Training knowledge point not found")
    point.title = body.title.strip()
    point.description = body.description.strip()
    await db.commit()
    return await course_response(db, course, user)


@router.delete(
    "/courses/{course_id}/knowledge-points/{knowledge_point_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def discard_knowledge_point(
    course_id: str,
    knowledge_point_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    course = await get_course_or_404(db, course_id)
    await require_course_manager(db, user, course)
    version = await get_version_or_404(db, course.id)
    ensure_editable(version)
    point = await db.get(TrainingKnowledgePoint, knowledge_point_id)
    if point is None or point.course_version_id != version.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Training knowledge point not found")
    if point.review_status != "pending":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Approved knowledge point cannot be discarded")
    evidence = list((await db.scalars(select(TrainingKnowledgeEvidence).where(
        TrainingKnowledgeEvidence.knowledge_point_id == point.id
    ))).all())
    for evidence_item in evidence:
        await db.delete(evidence_item)
    await db.delete(point)
    await db.commit()


@router.post(
    "/courses/{course_id}/assignments/batch",
    response_model=TrainingAssignmentBatchResponse,
    status_code=status.HTTP_201_CREATED,
)
async def assign_training_course_batch(
    course_id: str,
    body: TrainingAssignmentBatchCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    course = await get_course_or_404(db, course_id)
    await require_course_manager(db, user, course)
    if course.lifecycle_status != "active":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Course is archived")
    version = await get_version_or_404(db, course.id)
    if version.status != "published":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Course is not published")
    assignments: list[TrainingAssignmentResponse] = []
    skipped: list[str] = []
    for trainee_id in dict.fromkeys(body.trainee_ids):
        trainee = await db.get(User, trainee_id)
        if trainee is None:
            skipped.append(trainee_id)
            continue
        if course.scope_type == "project":
            membership = await db.scalar(select(ResearcherProject).where(
                ResearcherProject.project_id == course.project_id,
                ResearcherProject.researcher_id == trainee.id,
            ))
            if membership is None:
                skipped.append(trainee_id)
                continue
        exists = await db.scalar(select(TrainingAssignment).where(
            TrainingAssignment.course_version_id == version.id,
            TrainingAssignment.trainee_id == trainee.id,
        ))
        if exists is not None:
            skipped.append(trainee_id)
            continue
        assignment = TrainingAssignment(
            course_version_id=version.id,
            trainee_id=trainee.id,
            assigned_by=user.id,
            due_at=body.due_at,
        )
        db.add(assignment)
        await db.flush()
        assignments.append(await assignment_response(db, assignment))
    await db.commit()
    return TrainingAssignmentBatchResponse(assignments=assignments, skipped_trainee_ids=skipped)


@router.post("/courses/{course_id}/publish", response_model=TrainingCourseResponse)
async def publish_training_course(
    course_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    course = await get_course_or_404(db, course_id)
    await require_course_manager(db, user, course)
    version = await get_version_or_404(db, course.id)
    ensure_editable(version)
    assets = list((await db.scalars(select(TrainingCourseAsset).where(TrainingCourseAsset.course_version_id == version.id))).all())
    points = list((await db.scalars(select(TrainingKnowledgePoint).where(TrainingKnowledgePoint.course_version_id == version.id))).all())
    evidence_count = await db.scalar(
        select(func.count(TrainingKnowledgeEvidence.id))
        .join(TrainingKnowledgePoint, TrainingKnowledgePoint.id == TrainingKnowledgeEvidence.knowledge_point_id)
        .where(TrainingKnowledgePoint.course_version_id == version.id)
    )
    ensure_publishable(assets, points, evidence_count or 0)
    version.status = "published"
    version.published_by = user.id
    version.published_at = datetime.now(UTC)
    await db.commit()
    return await course_response(db, course, user)


@router.post("/courses/{course_id}/assignments", response_model=TrainingAssignmentResponse, status_code=status.HTTP_201_CREATED)
async def assign_training_course(
    course_id: str,
    body: TrainingAssignmentCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    course = await get_course_or_404(db, course_id)
    await require_course_manager(db, user, course)
    if course.lifecycle_status != "active":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Course is archived")
    version = await get_version_or_404(db, course.id)
    if version.status != "published":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Course is not published")
    trainee = await db.get(User, body.trainee_id)
    if trainee is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trainee not found")
    if course.scope_type == "project":
        membership = await db.scalar(
            select(ResearcherProject).where(
                ResearcherProject.project_id == course.project_id,
                ResearcherProject.researcher_id == trainee.id,
            )
        )
        if membership is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Trainee is outside project scope")
    assignment = TrainingAssignment(
        course_version_id=version.id,
        trainee_id=trainee.id,
        assigned_by=user.id,
        due_at=body.due_at,
    )
    db.add(assignment)
    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Training assignment already exists") from exc
    return await assignment_response(db, assignment)


@router.get("/assignments/me", response_model=list[TrainingAssignmentResponse])
async def list_my_training_assignments(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    assignments = list(
        (
            await db.scalars(
                select(TrainingAssignment)
                .where(
                    TrainingAssignment.trainee_id == user.id,
                    TrainingAssignment.status != "cancelled",
                )
                .order_by(TrainingAssignment.created_at.desc())
            )
        ).all()
    )
    return [await assignment_response(db, assignment) for assignment in assignments]


@router.get("/assignments/{assignment_id}/learning", response_model=TrainingCourseResponse)
async def get_assignment_learning_path(
    assignment_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    assignment = await db.get(TrainingAssignment, assignment_id)
    if assignment is None or assignment.status == "cancelled":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Training assignment not found")
    version = await db.get(TrainingCourseVersion, assignment.course_version_id)
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Training course version not found")
    course = await get_course_or_404(db, version.course_id)
    is_assignee = assignment.trainee_id == user.id
    if not is_assignee:
        await require_course_manager(db, user, course)
    if version.status != "published":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Training course is not published")
    course_assets = list(
        (
            await db.scalars(
                select(TrainingCourseAsset).where(
                    TrainingCourseAsset.course_version_id == version.id
                )
            )
        ).all()
    )
    for course_asset in course_assets:
        asset = await db.get(ResearchAsset, course_asset.research_asset_id)
        revision = await db.get(AssetRevision, course_asset.asset_revision_id)
        if asset is None or revision is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course material unavailable")
        await authorize_asset_for_course(db, user, asset, revision)
    return await course_response(db, course, user)
