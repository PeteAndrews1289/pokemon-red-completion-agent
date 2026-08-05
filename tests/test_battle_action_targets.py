import pytest

from pokemon_red_completion.battle_action_targets import (
    BattleActionTargetError,
    RecoveryNeed,
    authorize_recovery_target,
    resolve_battle_action_target,
)
from pokemon_red_completion.battle_actions import BattleAction, BattleBoostStat
from pokemon_red_completion.battle_runtime import BattleRecoveryCapability


def _observation(
    *,
    active: int = 0,
    members: tuple[tuple[int, int, int, str | None], ...] = (
        (30, 100, 20, None),
        (80, 100, 25, None),
        (40, 40, 18, None),
    ),
) -> dict[str, object]:
    return {
        "features": {
            "party": {
                "active_index": active,
                "members": [
                    {"hp": hp, "max_hp": max_hp, "level": level, "status": status}
                    for hp, max_hp, level, status in members
                ],
            }
        }
    }


def test_recovery_resolves_active_party_target_and_effect_role() -> None:
    hp = resolve_battle_action_target(BattleAction.recovery(), _observation())
    status = resolve_battle_action_target(
        BattleAction.recovery(),
        _observation(members=((100, 100, 20, "sleep"),)),
    )
    both = resolve_battle_action_target(
        BattleAction.recovery(),
        _observation(members=((30, 100, 20, "paralysis"),)),
    )

    assert (hp.party_slot, hp.recovery_need) == (1, RecoveryNeed.HP)
    assert (status.party_slot, status.recovery_need) == (1, RecoveryNeed.STATUS)
    assert (both.party_slot, both.recovery_need) == (1, RecoveryNeed.HP_AND_STATUS)
    assert status.status == "sleep"
    assert both.status == "paralysis"


def test_recovery_can_infer_active_slot_from_legacy_lead_observation() -> None:
    resolved = resolve_battle_action_target(
        BattleAction.recovery(),
        {
            "features": {
                "party": {
                    "lead": {
                        "species_ref": "pokemon:test:two",
                        "level": 20,
                        "hp": 10,
                        "max_hp": 50,
                        "status": None,
                    },
                    "species_refs": ["pokemon:test:one", "pokemon:test:two"],
                }
            }
        },
    )
    assert resolved.party_slot == 2
    assert resolved.recovery_need is RecoveryNeed.HP


def test_switch_selects_healthiest_living_reserve_without_game_identity() -> None:
    resolved = resolve_battle_action_target(BattleAction.switch(), _observation())
    assert resolved.party_slot == 3


def test_switch_honors_an_explicit_legal_target() -> None:
    resolved = resolve_battle_action_target(BattleAction.switch(2), _observation())
    assert resolved.party_slot == 2


@pytest.mark.parametrize(
    "action,observation",
    (
        (BattleAction.recovery(), _observation(members=((100, 100, 20, None),))),
        (BattleAction.switch(), _observation(members=((30, 100, 20, None),))),
        (
            BattleAction.switch(2),
            _observation(members=((30, 100, 20, None), (0, 100, 25, None))),
        ),
    ),
)
def test_target_resolution_rejects_actions_without_legal_effect(
    action: BattleAction,
    observation: dict[str, object],
) -> None:
    with pytest.raises(BattleActionTargetError):
        resolve_battle_action_target(action, observation)


def test_targetless_action_stays_targetless() -> None:
    resolved = resolve_battle_action_target(
        BattleAction.boost(BattleBoostStat.SPECIAL),
        {},
    )
    assert resolved.party_slot is None
    assert resolved.recovery_need is None


def test_recovery_authorization_selects_only_declared_effect() -> None:
    combined = resolve_battle_action_target(
        BattleAction.recovery(),
        _observation(members=((30, 100, 20, "poison"),)),
    )
    hp_only = authorize_recovery_target(
        combined,
        frozenset({BattleRecoveryCapability.RESTORE_HP}),
    )
    assert hp_only.recovery_need is RecoveryNeed.HP
    assert hp_only.status is None
    with pytest.raises(BattleActionTargetError, match="not declared"):
        authorize_recovery_target(
            combined,
            frozenset({BattleRecoveryCapability.CURE_SLEEP}),
        )


def test_recovery_authorization_prefers_specific_status_before_hp() -> None:
    combined = resolve_battle_action_target(
        BattleAction.recovery(),
        _observation(members=((30, 100, 20, "paralysis"),)),
    )
    status = authorize_recovery_target(
        combined,
        frozenset(
            {
                BattleRecoveryCapability.RESTORE_HP,
                BattleRecoveryCapability.CURE_PARALYSIS,
            }
        ),
    )
    assert status.recovery_need is RecoveryNeed.STATUS
    assert status.status == "paralysis"
