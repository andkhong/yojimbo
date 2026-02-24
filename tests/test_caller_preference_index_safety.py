"""Regression checks for caller preference index declarations."""

from app.models.caller_preference import CallerPreference


def test_caller_preference_phone_number_uses_single_unique_index():
    """Avoid duplicate indexes on caller phone number."""
    phone_indexes = [
        idx
        for idx in CallerPreference.__table__.indexes
        if [col.name for col in idx.columns] == ["phone_number"]
    ]
    assert len(phone_indexes) == 1
    assert phone_indexes[0].unique is True
