import logging
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.constants import ROLE_ADMIN
from app.core.security import hash_password
from app.models.user import User, Workspace

logger = logging.getLogger(__name__)

DEFAULT_ADMIN_USERNAME = "admin"


async def seed_default_admin(db: AsyncSession) -> None:
    result = await db.execute(
        select(User).where(User.username == DEFAULT_ADMIN_USERNAME)
    )
    if result.scalar_one_or_none():
        return

    # First run: admin does not exist yet — password must be configured
    if not settings.admin_password:
        logger.critical(
            "OPENCOLAB_ADMIN_PASSWORD is not set. "
            "Set it in .env or as an environment variable before the first run."
        )
        sys.exit(1)

    admin = User(
        username=DEFAULT_ADMIN_USERNAME,
        hashed_password=hash_password(settings.admin_password),
        role=ROLE_ADMIN,
    )
    db.add(admin)
    await db.flush()

    workspace = Workspace(researcher_id=admin.id)
    db.add(workspace)
    await db.commit()

    logger.info("Default admin user created (username: %s)", DEFAULT_ADMIN_USERNAME)
