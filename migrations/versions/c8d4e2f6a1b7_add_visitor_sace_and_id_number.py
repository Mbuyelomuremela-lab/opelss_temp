"""add visitor sace_number and encrypted id_number

Revision ID: c8d4e2f6a1b7
Revises: b2d9c4e7a1f3
Create Date: 2026-11-25 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c8d4e2f6a1b7'
down_revision: Union[str, Sequence[str], None] = 'b2d9c4e7a1f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema. Columns are nullable so existing visitor records stay valid."""
    with op.batch_alter_table("visitors") as batch_op:
        batch_op.add_column(sa.Column("sace_number", sa.String(length=8), nullable=True))
        batch_op.add_column(sa.Column("id_number_encrypted", sa.String(length=255), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("visitors") as batch_op:
        batch_op.drop_column("id_number_encrypted")
        batch_op.drop_column("sace_number")
