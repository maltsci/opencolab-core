import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.constants import ROLE_ADMIN, ROLE_PI, ROLE_RESEARCHER
from app.core.database import get_db
from app.core.dependencies import require_role
from app.core.security import (
    encrypt_api_key,
    hash_password,
    mask_api_key,
    decrypt_api_key,
)
from app.models.llm_key import LLMKey
from app.models.llm_profile import LLMProfile
from app.models.skill_pack import SkillPackRecord
from app.models.task_definition import TaskDefinitionRecord
from app.models.user import User, Workspace
from app.schemas.admin import (
    CreateUserRequest,
    LLMKeyCreate,
    LLMKeyResponse,
    LLMKeyUpdate,
    UpdateUserRequest,
)
from app.schemas.auth import UserResponse
from app.schemas.llm_profile import (
    LLMProfileCreate,
    LLMProfileModelProbeRequest,
    LLMProfileModelsResponse,
    LLMProfileProbeRequest,
    LLMProfileProbeResponse,
    LLMProfileResponse,
    LLMProfileUpdate,
)
from app.schemas.skill_pack import SkillPackResponse, SkillPackUpdateRequest
from app.schemas.task import TaskDefinition, TaskDefinitionCreate, TaskDefinitionUpdate
from app.services.llm_key_service import test_llm_key_config
from app.services.skill_pack_service import (
    SkillPackValidationError,
    get_current_skill_pack,
    skill_pack_task_id,
    store_skill_pack_zip,
)
from app.services.task_service import (
    BuiltInTaskDefinitionError,
    DuplicateTaskDefinitionError,
    UnknownTaskDefinitionError,
    create_task_definition,
    delete_task_definition,
    list_all_task_definitions,
    update_task_definition,
)
from app.services.llm_profile_service import (
    fetch_models,
    test_connection,
    test_model,
)
from app.services.runtime_config import (
    get_all_runtime_config,
    get_runtime_value,
    is_setup_complete,
    set_runtime_values,
)

router = APIRouter(prefix="/admin", tags=["admin"])

admin_dep = require_role(ROLE_ADMIN)
user_manager_dep = require_role(ROLE_ADMIN, ROLE_PI)


async def _resolve_probe_api_key(
    body: LLMProfileProbeRequest,
    db: AsyncSession,
) -> str:
    if body.key:
        return body.key

    if body.profile_id:
        result = await db.execute(
            select(LLMProfile).where(LLMProfile.id == body.profile_id)
        )
        profile = result.scalar_one_or_none()
        if profile is None:
            raise HTTPException(status_code=404, detail="LLM profile not found")
        return decrypt_api_key(profile.encrypted_key)

    raise HTTPException(
        status_code=422,
        detail="API key is required when no saved LLM profile is provided.",
    )


# --- User management ---


@router.get("/users", response_model=list[UserResponse])
async def list_users(
    db: AsyncSession = Depends(get_db), _=Depends(user_manager_dep)
):
    result = await db.execute(select(User))
    return [UserResponse.model_validate(u) for u in result.scalars().all()]


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: CreateUserRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(user_manager_dep),
):
    _require_can_create_user(current_user, body.role)
    existing = await db.execute(select(User).where(User.username == body.username))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Username already exists")

    user = User(
        username=body.username,
        hashed_password=hash_password(body.password),
        role=body.role,
        display_name=body.display_name,
    )
    db.add(user)
    await db.flush()

    workspace = Workspace(researcher_id=user.id)
    db.add(workspace)
    await db.commit()
    await db.refresh(user)
    return UserResponse.model_validate(user)


@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    body: UpdateUserRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(user_manager_dep),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    _require_can_update_user(current_user, user, body)

    if body.role is not None:
        user.role = body.role
    if body.password is not None:
        user.hashed_password = hash_password(body.password)
    if body.display_name is not None:
        user.display_name = body.display_name.strip() or None

    await db.commit()
    await db.refresh(user)
    return UserResponse.model_validate(user)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(admin_dep),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    await db.delete(user)
    await db.commit()
    return None


def _require_can_create_user(current_user: User, role: str) -> None:
    if current_user.role == ROLE_ADMIN:
        return
    if role not in {ROLE_RESEARCHER, ROLE_PI}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


def _require_can_update_user(
    current_user: User,
    target_user: User,
    body: UpdateUserRequest,
) -> None:
    if current_user.role == ROLE_ADMIN:
        return

    if target_user.role == ROLE_ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if body.role is not None and body.role not in {ROLE_RESEARCHER, ROLE_PI}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    target_is_self = target_user.id == current_user.id
    target_is_researcher = target_user.role == ROLE_RESEARCHER
    if target_is_self or target_is_researcher:
        return

    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


# --- Skill Packs ---


def _skill_pack_response(record: SkillPackRecord) -> SkillPackResponse:
    return SkillPackResponse.model_validate(record)


@router.post(
    "/skill-packs",
    response_model=SkillPackResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_skill_pack(
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(admin_dep),
):
    try:
        pack = await store_skill_pack_zip(
            await file.read(),
            db=db,
            created_by=current_user.id,
        )
    except SkillPackValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _skill_pack_response(pack)


@router.get("/skill-packs", response_model=list[SkillPackResponse])
async def list_skill_packs(
    db: AsyncSession = Depends(get_db),
    _=Depends(admin_dep),
):
    result = await db.execute(
        select(SkillPackRecord).order_by(SkillPackRecord.id, SkillPackRecord.version.desc())
    )
    current_by_id: dict[str, SkillPackRecord] = {}
    for record in result.scalars().all():
        current_by_id.setdefault(record.id, record)
    return [_skill_pack_response(record) for record in current_by_id.values()]


@router.get("/skill-packs/{pack_id}/versions", response_model=list[SkillPackResponse])
async def list_skill_pack_versions(
    pack_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(admin_dep),
):
    result = await db.execute(
        select(SkillPackRecord)
        .where(SkillPackRecord.id == pack_id)
        .order_by(SkillPackRecord.version.desc())
    )
    records = list(result.scalars().all())
    if not records:
        raise HTTPException(status_code=404, detail="Skill pack not found")
    return [_skill_pack_response(record) for record in records]


@router.patch("/skill-packs/{pack_id}", response_model=SkillPackResponse)
async def update_skill_pack(
    pack_id: str,
    body: SkillPackUpdateRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(admin_dep),
):
    pack = await get_current_skill_pack(db, pack_id=pack_id)
    if pack is None:
        raise HTTPException(status_code=404, detail="Skill pack not found")
    for field, value in body.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(pack, field, value)

    task = await db.scalar(
        select(TaskDefinitionRecord).where(
            TaskDefinitionRecord.id == skill_pack_task_id(pack_id)
        )
    )
    if task is not None:
        task.name = pack.name
        task.description = pack.description
        task.is_enabled = pack.is_enabled
    await db.commit()
    await db.refresh(pack)
    return _skill_pack_response(pack)


@router.delete("/skill-packs/{pack_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_skill_pack(
    pack_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(admin_dep),
):
    result = await db.execute(
        select(SkillPackRecord).where(SkillPackRecord.id == pack_id)
    )
    records = list(result.scalars().all())
    if not records:
        raise HTTPException(status_code=404, detail="Skill pack not found")
    for record in records:
        await db.delete(record)

    task = await db.scalar(
        select(TaskDefinitionRecord).where(
            TaskDefinitionRecord.id == skill_pack_task_id(pack_id)
        )
    )
    if task is not None:
        task.is_enabled = False

    pack_dir = Path(settings.skill_pack_dir) / pack_id
    if pack_dir.exists():
        shutil.rmtree(pack_dir)
    await db.commit()
    return None


@router.get("/tasks", response_model=list[TaskDefinition])
async def list_tasks(
    db: AsyncSession = Depends(get_db),
    _=Depends(admin_dep),
):
    return await list_all_task_definitions(db)


@router.post(
    "/tasks",
    response_model=TaskDefinition,
    status_code=status.HTTP_201_CREATED,
)
async def create_task(
    body: TaskDefinitionCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(admin_dep),
):
    try:
        return await create_task_definition(body, db)
    except DuplicateTaskDefinitionError as exc:
        raise HTTPException(
            status_code=409,
            detail="A custom task with this id already exists",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/tasks/{task_id}", response_model=TaskDefinition)
async def update_task(
    task_id: str,
    body: TaskDefinitionUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(admin_dep),
):
    try:
        return await update_task_definition(task_id, body, db)
    except UnknownTaskDefinitionError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(admin_dep),
):
    try:
        await delete_task_definition(task_id, db)
    except BuiltInTaskDefinitionError as exc:
        raise HTTPException(
            status_code=400,
            detail="Built-in tasks cannot be deleted",
        ) from exc
    except UnknownTaskDefinitionError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc
    return None


def _build_llm_profile_response(profile: LLMProfile) -> LLMProfileResponse:
    return LLMProfileResponse(
        id=profile.id,
        name=profile.name,
        provider=profile.provider,
        api_base=profile.api_base,
        model=profile.model,
        status=profile.status,
        last_tested_at=profile.last_tested_at,
        last_test_result=profile.last_test_result,
        masked_key=mask_api_key(decrypt_api_key(profile.encrypted_key)),
    )


@router.get("/llm-profiles", response_model=list[LLMProfileResponse])
async def list_llm_profiles(
    db: AsyncSession = Depends(get_db), _=Depends(admin_dep)
):
    result = await db.execute(select(LLMProfile))
    profiles = result.scalars().all()
    return [_build_llm_profile_response(profile) for profile in profiles]


@router.post(
    "/llm-profiles",
    response_model=LLMProfileResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_llm_profile(
    body: LLMProfileCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(admin_dep),
):
    profile = LLMProfile(
        name=body.name,
        provider=body.provider,
        api_base=body.api_base.strip() if body.api_base else None,
        encrypted_key=encrypt_api_key(body.key),
        model=body.model,
        status="unknown",
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return _build_llm_profile_response(profile)


@router.put("/llm-profiles/{profile_id}", response_model=LLMProfileResponse)
async def update_llm_profile(
    profile_id: str,
    body: LLMProfileUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(admin_dep),
):
    result = await db.execute(select(LLMProfile).where(LLMProfile.id == profile_id))
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="LLM profile not found")

    profile.name = body.name
    profile.provider = body.provider
    profile.api_base = body.api_base.strip() if body.api_base else None
    profile.model = body.model
    if body.key:
        profile.encrypted_key = encrypt_api_key(body.key)

    await db.commit()
    await db.refresh(profile)
    return _build_llm_profile_response(profile)


@router.delete("/llm-profiles/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_llm_profile(
    profile_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(admin_dep),
):
    result = await db.execute(select(LLMProfile).where(LLMProfile.id == profile_id))
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="LLM profile not found")
    await db.delete(profile)
    await db.commit()
    return None


@router.post("/llm-profiles/{profile_id}/activate")
async def activate_llm_profile(
    profile_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(admin_dep),
):
    result = await db.execute(select(LLMProfile).where(LLMProfile.id == profile_id))
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="LLM profile not found")

    await set_runtime_values({"active_llm_profile_id": profile.id}, db)
    return {"status": "ok", "active_llm_profile_id": profile.id}


@router.post("/llm-profiles/fetch-models", response_model=LLMProfileModelsResponse)
async def fetch_llm_profile_models(
    body: LLMProfileProbeRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(admin_dep),
):
    api_key = await _resolve_probe_api_key(body, db)
    return {"models": await fetch_models(body.provider, body.api_base, api_key)}


@router.post("/llm-profiles/test-connection", response_model=LLMProfileProbeResponse)
async def test_llm_profile_connection(
    body: LLMProfileProbeRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(admin_dep),
):
    try:
        api_key = await _resolve_probe_api_key(body, db)
        return await test_connection(body.provider, body.api_base, api_key)
    except Exception as exc:
        return {
            "ok": False,
            "status": "connection_failed",
            "message": str(exc),
            "models": None,
        }


@router.post("/llm-profiles/test-model", response_model=LLMProfileProbeResponse)
async def test_llm_profile_model(
    body: LLMProfileModelProbeRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(admin_dep),
):
    api_key = await _resolve_probe_api_key(body, db)
    return await test_model(body.provider, body.api_base, api_key, body.model)


# --- LLM Keys ---


@router.get("/llm-keys", response_model=list[LLMKeyResponse])
async def list_llm_keys(
    db: AsyncSession = Depends(get_db), _=Depends(admin_dep)
):
    result = await db.execute(select(LLMKey))
    keys = result.scalars().all()
    return [
        LLMKeyResponse(
            id=k.id,
            provider=k.provider,
            name=k.name,
            api_base=k.api_base,
            masked_key=mask_api_key(decrypt_api_key(k.encrypted_key)),
        )
        for k in keys
    ]


@router.post("/llm-keys", status_code=status.HTTP_201_CREATED)
async def create_llm_key(
    body: LLMKeyCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(admin_dep),
):
    key = LLMKey(
        provider=body.provider,
        name=body.name,
        api_base=body.api_base.strip() if body.api_base else None,
        encrypted_key=encrypt_api_key(body.key),
    )
    db.add(key)
    await db.commit()
    return {"id": key.id}


@router.put("/llm-keys/{key_id}")
async def update_llm_key(
    key_id: str,
    body: LLMKeyUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(admin_dep),
):
    result = await db.execute(select(LLMKey).where(LLMKey.id == key_id))
    key = result.scalar_one_or_none()
    if not key:
        raise HTTPException(status_code=404, detail="LLM key not found")

    key.provider = body.provider
    key.name = body.name
    key.api_base = body.api_base.strip() if body.api_base else None
    if body.key:
        key.encrypted_key = encrypt_api_key(body.key)

    await db.commit()
    return {"id": key.id}


@router.post("/llm-keys/test")
async def test_llm_key(
    body: LLMKeyCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(admin_dep),
):
    try:
        runtime_model = await get_runtime_value("llm_model", db)
        return await test_llm_key_config(body, test_model=runtime_model)
    except Exception as exc:
        return {"ok": False, "message": str(exc)}


@router.delete("/llm-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_llm_key(
    key_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(admin_dep),
):
    result = await db.execute(select(LLMKey).where(LLMKey.id == key_id))
    key = result.scalar_one_or_none()
    if not key:
        raise HTTPException(status_code=404, detail="LLM key not found")
    await db.delete(key)
    await db.commit()
    return None


# --- System Config ---


class UpdateConfigRequest(BaseModel):
    values: dict[str, str | None]


@router.get("/config")
async def get_config(
    db: AsyncSession = Depends(get_db), _=Depends(admin_dep)
):
    config = await get_all_runtime_config(db)
    # Mask llm_api_key for security
    if config.get("llm_api_key"):
        val = config["llm_api_key"]
        config["llm_api_key"] = val[:4] + "****" + val[-4:] if len(val) > 8 else "****"
    # Mask llm_proxy as it can include credentials in URL (e.g. http://user:pass@host:port)
    if config.get("llm_proxy"):
        val = config["llm_proxy"]
        config["llm_proxy"] = val[:7] + "****" + val[-4:] if len(val) > 12 else "****"
    return config


@router.put("/config")
async def update_config(
    body: UpdateConfigRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(admin_dep),
):
    await set_runtime_values(body.values, db)
    return {"status": "ok"}


@router.get("/config/setup-status")
async def get_setup_status(
    db: AsyncSession = Depends(get_db), _=Depends(admin_dep)
):
    return {"setup_complete": await is_setup_complete(db)}
