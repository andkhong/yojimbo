"""add_sms_and_timeslot_indexes

Revision ID: 9a7e1c2d4f10
Revises: bf5cfbb6a13b
Create Date: 2026-02-23 19:45:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9a7e1c2d4f10"
down_revision: Union[str, Sequence[str], None] = "bf5cfbb6a13b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _index_exists(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(index.get("name") == index_name for index in inspector.get_indexes(table_name))


def upgrade() -> None:
    """Upgrade schema."""
    if not _index_exists("sms_messages", "ix_sms_created"):
        op.create_index("ix_sms_created", "sms_messages", ["created_at"], unique=False)

    if not _index_exists("sms_messages", "ix_sms_contact_created"):
        op.create_index(
            "ix_sms_contact_created", "sms_messages", ["contact_id", "created_at"], unique=False
        )

    if not _index_exists("sms_messages", "ix_sms_dept_created"):
        op.create_index(
            "ix_sms_dept_created", "sms_messages", ["department_id", "created_at"], unique=False
        )

    if not _index_exists("time_slots", "ix_time_slots_lookup"):
        op.create_index(
            "ix_time_slots_lookup",
            "time_slots",
            ["department_id", "day_of_week", "is_active", "start_time"],
            unique=False,
        )


def downgrade() -> None:
    """Downgrade schema."""
    if _index_exists("time_slots", "ix_time_slots_lookup"):
        op.drop_index("ix_time_slots_lookup", table_name="time_slots")

    if _index_exists("sms_messages", "ix_sms_dept_created"):
        op.drop_index("ix_sms_dept_created", table_name="sms_messages")

    if _index_exists("sms_messages", "ix_sms_contact_created"):
        op.drop_index("ix_sms_contact_created", table_name="sms_messages")

    if _index_exists("sms_messages", "ix_sms_created"):
        op.drop_index("ix_sms_created", table_name="sms_messages")
