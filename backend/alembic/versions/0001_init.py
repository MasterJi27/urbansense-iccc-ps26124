"""create urbansense schema via metadata

Revision ID: 0001
Revises:
Create Date: 2026-09-02
"""

from alembic import op
from sqlalchemy import text

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        bind.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
    from app.database import Base
    from app.models import *  # noqa: F401,F403

    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    from app.database import Base

    Base.metadata.drop_all(bind=op.get_bind())
