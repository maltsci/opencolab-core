import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.agent_runtime import router as agent_runtime_router
from app.api.admin import router as admin_router
from app.api.agents import router as agents_router
from app.api.auth import router as auth_router
from app.api.health import router as health_router
from app.api.knowledge_governance import router as knowledge_governance_router
from app.api.messages import router as messages_router
from app.api.notes import router as notes_router
from app.api.notifications import router as notifications_router
from app.api.orchestration import router as orchestration_router
from app.api.project_activities import router as project_activities_router
from app.api.project_plans import router as project_plans_router
from app.api.projects import router as projects_router
from app.api.research_assets import router as research_assets_router
from app.api.research_directions import (
    relation_router as research_direction_relations_router,
)
from app.api.research_directions import router as research_directions_router
from app.api.people import router as people_router
from app.api.research_groups import router as research_groups_router
from app.api.research_object_relations import router as research_object_relations_router
from app.api.research_objects import router as research_objects_router
from app.api.research_threads import router as research_threads_router
from app.api.sessions import router as sessions_router
from app.api.sources import router as sources_router
from app.api.tags import router as tags_router
from app.api.tasks import router as tasks_router
from app.api.training import router as training_router
from app.api.websocket import router as ws_router
from app.api.workflows import router as workflows_router
from app.core.config import settings
from app.core.database import async_session_factory
from app.core.logging_config import setup_logging, shutdown_logging
from app.core.seed import seed_default_admin
from app.services.task_service import seed_default_task_definitions
from app.services.source_cleanup import mark_stale_sources_failed

setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Write PID for process management (check status, stop)
    log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
    os.makedirs(log_dir, exist_ok=True)
    pid_file = os.path.join(log_dir, "backend.pid")
    # With uvicorn --reload, we are a worker; store parent (reloader) PID
    pid = os.getppid() if os.getppid() != 1 else os.getpid()
    with open(pid_file, "w") as f:
        f.write(str(pid))

    from app.core.database import check_db_connection

    await check_db_connection()
    logger.info(
        "PostgreSQL connection OK (%s:%s)",
        settings.postgres_host,
        settings.postgres_port,
    )

    async with async_session_factory() as db:
        await seed_default_admin(db)
    async with async_session_factory() as db:
        await seed_default_task_definitions(db)
    # Any source still in a non-terminal processing_state is left over from a
    # previous (crashed or restarted) run — the asyncio task is gone, so flip
    # it to failed instead of leaving it stuck.
    async with async_session_factory() as db:
        await mark_stale_sources_failed(db)
    yield
    try:
        if os.path.exists(pid_file):
            os.remove(pid_file)
    except OSError:
        pass
    shutdown_logging()


app = FastAPI(title=settings.app_name, lifespan=lifespan)

api = "/api/v1"

app.include_router(health_router, prefix=api)
app.include_router(auth_router, prefix=api)
app.include_router(admin_router, prefix=api)
app.include_router(projects_router, prefix=api)
app.include_router(project_plans_router, prefix=api)
app.include_router(project_activities_router, prefix=api)
app.include_router(sessions_router, prefix=api)
app.include_router(tasks_router, prefix=api)
app.include_router(training_router, prefix=api)
app.include_router(agents_router, prefix=api)
app.include_router(agent_runtime_router, prefix=api)
app.include_router(workflows_router, prefix=api)
app.include_router(research_assets_router, prefix=api)
app.include_router(research_directions_router, prefix=api)
app.include_router(people_router, prefix=api)
app.include_router(research_direction_relations_router, prefix=api)
app.include_router(research_groups_router, prefix=api)
app.include_router(knowledge_governance_router, prefix=api)
app.include_router(research_objects_router, prefix=api)
app.include_router(research_object_relations_router, prefix=api)
app.include_router(research_threads_router, prefix=api)
app.include_router(tags_router, prefix=api)
app.include_router(sources_router, prefix=api)
app.include_router(messages_router, prefix=api)
app.include_router(notes_router, prefix=api)
app.include_router(notifications_router, prefix=api)
app.include_router(orchestration_router, prefix=api)
app.include_router(ws_router, prefix=api)
