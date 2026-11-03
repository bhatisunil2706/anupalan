"""financial regulator reporting clocks on incidents

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-03 10:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0008'
down_revision: Union[str, None] = '0007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('incidents', sa.Column('regulators', sa.JSON(), server_default='[]', nullable=False))
    op.add_column('incidents', sa.Column('regulator_reported', sa.JSON(), server_default='{}', nullable=False))


def downgrade() -> None:
    op.drop_column('incidents', 'regulator_reported')
    op.drop_column('incidents', 'regulators')
