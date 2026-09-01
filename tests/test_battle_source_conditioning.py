from __future__ import annotations

from dataclasses import replace

import pytest

from pokemon_red_completion.battle_source_conditioning import (
    BATTLE_RESOURCE_CONDITIONING_V1,
    BattlePartyIdentity,
    BattlePartyMemberIdentity,
    BattleSourceConditioningContract,
    BattleSourceConditioningError,
)


def _identity() -> BattlePartyIdentity:
    return BattlePartyIdentity(
        (
            BattlePartyMemberIdentity(
                species_ref="shared:species:starter",
                level=20,
                move_refs=("shared:move:water", "shared:move:normal"),
            ),
        )
    )


def test_resource_conditioning_preserves_ordered_party_identity() -> None:
    identity = _identity()

    BATTLE_RESOURCE_CONDITIONING_V1.require_identity_preserved(identity, identity)

    changed_level = BattlePartyIdentity((replace(identity.members[0], level=21),))
    with pytest.raises(BattleSourceConditioningError, match="changed"):
        BATTLE_RESOURCE_CONDITIONING_V1.require_identity_preserved(
            identity,
            changed_level,
        )


def test_resource_conditioning_cannot_admit_a_forced_single_action() -> None:
    with pytest.raises(BattleSourceConditioningError, match="forced singleton"):
        BattleSourceConditioningContract(minimum_supported_actions=1)


@pytest.mark.parametrize(
    "change",
    (
        {"preserves_party_order": False},
        {"preserves_species": False},
        {"preserves_levels": False},
        {"preserves_moves": False},
        {"permits_pp_restoration": False},
    ),
)
def test_resource_conditioning_identity_boundary_cannot_be_weakened(
    change: dict[str, bool],
) -> None:
    with pytest.raises(BattleSourceConditioningError, match="cannot weaken"):
        BattleSourceConditioningContract(**change)
