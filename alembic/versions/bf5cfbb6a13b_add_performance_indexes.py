"""add_performance_indexes

Revision ID: bf5cfbb6a13b
Revises: c1f96c3b2c41
Create Date: 2026-02-22 00:51:43.081327

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


INDEX_SPECS: list[tuple[str, str, list[str]]] = [
    ("ix_appt_contact", "appointments", ["contact_id"]),
    ("ix_appt_dept_start", "appointments", ["department_id", "scheduled_start"]),
    (
        "ix_appt_reminder",
        "appointments",
        ["status", "reminder_sent", "scheduled_start"],
    ),
    ("ix_appt_status_start", "appointments", ["status", "scheduled_start"]),
    ("ix_audit_action_created", "audit_logs", ["action", "created_at"]),
    ("ix_audit_resource", "audit_logs", ["resource_type", "resource_id"]),
    ("ix_audit_user", "audit_logs", ["user_id", "created_at"]),
    ("ix_calls_contact", "calls", ["contact_id"]),
    ("ix_calls_dept_started", "calls", ["department_id", "started_at"]),
    ("ix_calls_language", "calls", ["detected_language"]),
    ("ix_calls_resolution", "calls", ["resolution_status"]),
    ("ix_calls_status", "calls", ["status"]),
    ("ix_conv_turns_call_seq", "conversation_turns", ["call_id", "sequence"]),
]


# revision identifiers, used by Alembic.
revision: str = 'bf5cfbb6a13b'
down_revision: Union[str, Sequence[str], None] = 'c1f96c3b2c41'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _index_exists(index_name: str, table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    indexes = inspector.get_indexes(table_name)
    return any(index["name"] == index_name for index in indexes)


def upgrade() -> None:
    """Upgrade schema."""
    for index_name, table_name, columns in INDEX_SPECS:
        if not _index_exists(index_name, table_name):
            op.create_index(index_name, table_name, columns, unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    for index_name, table_name, _ in reversed(INDEX_SPECS):
        if _index_exists(index_name, table_name):
            op.drop_index(index_name, table_name=table_name)
