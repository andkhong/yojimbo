"""add_performance_indexes

Revision ID: bf5cfbb6a13b
Revises: c1f96c3b2c41
Create Date: 2026-02-22 00:51:43.081327

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


def _index_exists(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    indexes = inspector.get_indexes(table_name)
    return any(index["name"] == index_name for index in indexes)


def _create_index_if_missing(index_name: str, table_name: str, columns: list[str]) -> None:
    if _index_exists(table_name, index_name):
        return
    op.create_index(index_name, table_name, columns, unique=False)


def _drop_index_if_exists(index_name: str, table_name: str) -> None:
    if not _index_exists(table_name, index_name):
        return
    op.drop_index(index_name, table_name=table_name)


# revision identifiers, used by Alembic.
revision: str = 'bf5cfbb6a13b'
down_revision: Union[str, Sequence[str], None] = 'c1f96c3b2c41'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    _create_index_if_missing("ix_appt_contact", "appointments", ["contact_id"])
    _create_index_if_missing(
        "ix_appt_dept_start", "appointments", ["department_id", "scheduled_start"]
    )
    _create_index_if_missing(
        "ix_appt_reminder",
        "appointments",
        ["status", "reminder_sent", "scheduled_start"],
    )
    _create_index_if_missing(
        "ix_appt_status_start", "appointments", ["status", "scheduled_start"]
    )
    _create_index_if_missing(
        "ix_audit_action_created", "audit_logs", ["action", "created_at"]
    )
    _create_index_if_missing(
        "ix_audit_resource", "audit_logs", ["resource_type", "resource_id"]
    )
    _create_index_if_missing("ix_audit_user", "audit_logs", ["user_id", "created_at"])
    _create_index_if_missing("ix_calls_contact", "calls", ["contact_id"])
    _create_index_if_missing(
        "ix_calls_dept_started", "calls", ["department_id", "started_at"]
    )
    _create_index_if_missing("ix_calls_language", "calls", ["detected_language"])
    _create_index_if_missing("ix_calls_resolution", "calls", ["resolution_status"])
    _create_index_if_missing("ix_calls_status", "calls", ["status"])
    _create_index_if_missing(
        "ix_conv_turns_call_seq", "conversation_turns", ["call_id", "sequence"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    _drop_index_if_exists("ix_conv_turns_call_seq", "conversation_turns")
    _drop_index_if_exists("ix_calls_status", "calls")
    _drop_index_if_exists("ix_calls_resolution", "calls")
    _drop_index_if_exists("ix_calls_language", "calls")
    _drop_index_if_exists("ix_calls_dept_started", "calls")
    _drop_index_if_exists("ix_calls_contact", "calls")
    _drop_index_if_exists("ix_audit_user", "audit_logs")
    _drop_index_if_exists("ix_audit_resource", "audit_logs")
    _drop_index_if_exists("ix_audit_action_created", "audit_logs")
    _drop_index_if_exists("ix_appt_status_start", "appointments")
    _drop_index_if_exists("ix_appt_reminder", "appointments")
    _drop_index_if_exists("ix_appt_dept_start", "appointments")
    _drop_index_if_exists("ix_appt_contact", "appointments")
