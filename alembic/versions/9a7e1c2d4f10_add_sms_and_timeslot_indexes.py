"""add_sms_and_timeslot_indexes

Revision ID: 9a7e1c2d4f10
Revises: bf5cfbb6a13b
Create Date: 2026-02-23 19:45:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "9a7e1c2d4f10"
down_revision: Union[str, Sequence[str], None] = "bf5cfbb6a13b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _index_exists(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(idx["name"] == index_name for idx in inspector.get_indexes(table_name))


def _create_index_if_missing(index_name: str, table_name: str, columns: list[str]) -> None:
    if not _index_exists(table_name, index_name):
        op.create_index(index_name, table_name, columns, unique=False)


def _drop_index_if_exists(index_name: str, table_name: str) -> None:
    if _index_exists(table_name, index_name):
        op.drop_index(index_name, table_name=table_name)


def upgrade() -> None:
    """Upgrade schema."""
    _create_index_if_missing("ix_sms_created", "sms_messages", ["created_at"])
    _create_index_if_missing("ix_sms_contact_created", "sms_messages", ["contact_id", "created_at"])
    _create_index_if_missing("ix_sms_dept_created", "sms_messages", ["department_id", "created_at"])
    _create_index_if_missing(
        "ix_time_slots_lookup",
        "time_slots",
        ["department_id", "day_of_week", "is_active", "start_time"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    _drop_index_if_exists("ix_time_slots_lookup", "time_slots")
    _drop_index_if_exists("ix_sms_dept_created", "sms_messages")
    _drop_index_if_exists("ix_sms_contact_created", "sms_messages")
    _drop_index_if_exists("ix_sms_created", "sms_messages")
