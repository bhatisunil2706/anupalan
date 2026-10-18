"""incident timeline, followers and threaded email updates

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-18 09:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app import rls
from app.config import get_settings

revision: str = '0007'
down_revision: Union[str, None] = '0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'incident_events',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('org_id', sa.Uuid(), nullable=False),
        sa.Column('incident_id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=True),
        sa.Column('kind', sa.String(length=30), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['incident_id'], ['incidents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_incident_events_org_id'), 'incident_events', ['org_id'], unique=False)
    op.create_index(op.f('ix_incident_events_incident_id'), 'incident_events', ['incident_id'], unique=False)
    op.add_column('incidents', sa.Column('reported_by_id', sa.Uuid(), nullable=True))
    op.add_column('incidents', sa.Column('follower_ids', sa.JSON(), server_default='[]', nullable=False))
    op.add_column('incidents', sa.Column('email_subject', sa.String(length=400), server_default='', nullable=False))
    op.create_foreign_key('incidents_reported_by_id_fkey', 'incidents', 'users', ['reported_by_id'], ['id'],
                          ondelete='SET NULL')
    op.add_column('notifications', sa.Column('thread', sa.String(length=200), server_default='', nullable=False))
    op.add_column('notifications', sa.Column('subject', sa.String(length=400), server_default='', nullable=False))

    # Existing incidents: a fixed email subject, and the lead as the first follower.
    op.execute("UPDATE incidents SET email_subject = left('INC-' || number || ': ' || title, 400)")
    op.execute("UPDATE incidents SET follower_ids = json_build_array(lead_id::text) WHERE lead_id IS NOT NULL")

    bind = op.get_bind()
    settings = get_settings()
    rls.apply_policies(bind)
    rls.ensure_runtime_role(bind, settings.runtime_db_role, settings.runtime_db_password)
    rls.grant_runtime(bind, settings.runtime_db_role)


def downgrade() -> None:
    op.drop_column('notifications', 'subject')
    op.drop_column('notifications', 'thread')
    op.drop_constraint('incidents_reported_by_id_fkey', 'incidents', type_='foreignkey')
    op.drop_column('incidents', 'email_subject')
    op.drop_column('incidents', 'follower_ids')
    op.drop_column('incidents', 'reported_by_id')
    op.drop_index(op.f('ix_incident_events_incident_id'), table_name='incident_events')
    op.drop_index(op.f('ix_incident_events_org_id'), table_name='incident_events')
    op.drop_table('incident_events')
