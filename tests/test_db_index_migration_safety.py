from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_migration_module():
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "bf5cfbb6a13b_add_performance_indexes.py"
    )
    spec = importlib.util.spec_from_file_location("perf_indexes_migration", migration_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_performance_index_upgrade_uses_if_not_exists():
    module = _load_migration_module()

    calls = []

    class _Op:
        @staticmethod
        def create_index(*args, **kwargs):
            calls.append((args, kwargs))

    module.op = _Op()
    module.upgrade()

    assert calls
    assert all(kwargs.get("if_not_exists") is True for _, kwargs in calls)


def test_performance_index_downgrade_uses_if_exists():
    module = _load_migration_module()

    calls = []

    class _Op:
        @staticmethod
        def drop_index(*args, **kwargs):
            calls.append((args, kwargs))

    module.op = _Op()
    module.downgrade()

    assert calls
    assert all(kwargs.get("if_exists") is True for _, kwargs in calls)
