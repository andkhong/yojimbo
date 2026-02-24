from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


_MIGRATION_PATH = (
    Path(__file__).resolve().parent.parent
    / "alembic"
    / "versions"
    / "9a7e1c2d4f10_add_sms_and_timeslot_indexes.py"
)
_MIGRATION_SPEC = spec_from_file_location("migration_9a7e1c2d4f10", _MIGRATION_PATH)
assert _MIGRATION_SPEC and _MIGRATION_SPEC.loader
migration = module_from_spec(_MIGRATION_SPEC)
_MIGRATION_SPEC.loader.exec_module(migration)


class _Inspector:
    def __init__(self, indexes_by_table):
        self.indexes_by_table = indexes_by_table

    def get_indexes(self, table_name):
        return [{"name": name} for name in self.indexes_by_table.get(table_name, [])]


def test_upgrade_creates_only_missing_indexes(monkeypatch):
    existing = {
        "sms_messages": ["ix_sms_created"],
        "time_slots": [],
    }
    created = []

    monkeypatch.setattr(migration.op, "get_bind", lambda: object())
    monkeypatch.setattr(migration.sa, "inspect", lambda _: _Inspector(existing))
    monkeypatch.setattr(
        migration.op,
        "create_index",
        lambda index_name, table_name, columns, unique=False: created.append(
            (index_name, table_name, tuple(columns), unique)
        ),
    )

    migration.upgrade()

    assert created == [
        ("ix_sms_contact_created", "sms_messages", ("contact_id", "created_at"), False),
        ("ix_sms_dept_created", "sms_messages", ("department_id", "created_at"), False),
        (
            "ix_time_slots_lookup",
            "time_slots",
            ("department_id", "day_of_week", "is_active", "start_time"),
            False,
        ),
    ]


def test_downgrade_drops_only_existing_indexes(monkeypatch):
    existing = {
        "sms_messages": ["ix_sms_contact_created", "ix_sms_created"],
        "time_slots": [],
    }
    dropped = []

    monkeypatch.setattr(migration.op, "get_bind", lambda: object())
    monkeypatch.setattr(migration.sa, "inspect", lambda _: _Inspector(existing))
    monkeypatch.setattr(
        migration.op,
        "drop_index",
        lambda index_name, table_name: dropped.append((index_name, table_name)),
    )

    migration.downgrade()

    assert dropped == [
        ("ix_sms_contact_created", "sms_messages"),
        ("ix_sms_created", "sms_messages"),
    ]
