"""Add users.departments for RBAC document access control.

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-15

``departments`` is the set a user may retrieve from. ``employee`` carries one
entry, ``manager`` several, ``admin`` an empty array (meaning "all"). Shared
company-wide documents have ``documents.department IS NULL`` and are visible to
everyone regardless of this column.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "departments",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "departments")
