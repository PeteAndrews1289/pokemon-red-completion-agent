import pytest

from pokemon_red_completion.field_recovery import FieldRecoveryError, plan_party_recovery
from pokemon_red_completion.observation import ItemId


def test_party_recovery_targets_each_affected_member() -> None:
    assert plan_party_recovery(
        (200, 130, 120, 250, 125, 91),
        (200, 130, 120, 250, 125, 140),
        (0, 0, 0, 0, 0, 0),
    ) == ((5, ItemId.HYPER_POTION),)
    assert plan_party_recovery(
        (190, 130),
        (200, 130),
        (0x08, 0x40),
    ) == (
        (0, ItemId.FULL_RESTORE),
        (1, ItemId.FULL_HEAL),
    )


def test_party_recovery_rejects_incomplete_or_fainted_state() -> None:
    with pytest.raises(FieldRecoveryError, match="incomplete"):
        plan_party_recovery((200,), (200,), ())
    with pytest.raises(FieldRecoveryError, match="invalid recovery HP"):
        plan_party_recovery((0,), (200,), (0,))
