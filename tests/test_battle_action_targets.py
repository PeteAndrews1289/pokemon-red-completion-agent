import pytest

from pokemon_red_completion.battle_action_targets import (
    BattleActionTargetError,
    RecoveryNeed,
    SwitchTargetBasis,
    authorize_recovery_target,
    authorize_switch_target,
    resolve_battle_action_target,
)
from pokemon_red_completion.battle_actions import BattleAction, BattleBoostStat
from pokemon_red_completion.battle_runtime import (
    BattleRecoveryCapability,
    BattleSwitchCapability,
)
from pokemon_red_completion.red_battle_catalog import (
    RED_BATTLE_CATALOG,
    pokemon_red_move_ref,
    pokemon_red_species_ref,
)


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


@pytest.mark.parametrize(
    ("stat", "resource_key"),
    (
        (BattleBoostStat.ACCURACY, "accuracy_boost_count"),
        (BattleBoostStat.ATTACK, "attack_boost_count"),
        (BattleBoostStat.SPECIAL, "special_boost_count"),
    ),
)
def test_boost_requires_matching_observed_inventory(
    stat: BattleBoostStat,
    resource_key: str,
) -> None:
    observation = _observation()
    features = observation["features"]
    assert isinstance(features, dict)
    features["resources"] = {resource_key: 1}

    assert resolve_battle_action_target(
        BattleAction.boost(stat),
        observation,
    ).action == BattleAction.boost(stat)

    features["resources"] = {resource_key: 0}
    with pytest.raises(BattleActionTargetError, match="not observably available"):
        resolve_battle_action_target(BattleAction.boost(stat), observation)


def test_switch_selects_healthiest_living_reserve_without_game_identity() -> None:
    resolved = resolve_battle_action_target(BattleAction.switch(), _observation())
    assert resolved.party_slot == 3
    assert resolved.switch_basis is SwitchTargetBasis.READINESS


def test_switch_honors_an_explicit_legal_target() -> None:
    resolved = resolve_battle_action_target(BattleAction.switch(2), _observation())
    assert resolved.party_slot == 2
    assert resolved.switch_basis is SwitchTargetBasis.EXPLICIT


def test_switch_selects_and_preserves_the_best_semantic_matchup() -> None:
    observation = {
        "features": {
            "party": {
                "active_index": 0,
                "members": [
                    {
                        "species_ref": pokemon_red_species_ref(0x1C),
                        "hp": 100,
                        "max_hp": 100,
                        "level": 63,
                        "status": None,
                        "moves": [
                            {"move_ref": pokemon_red_move_ref(0x39), "pp": 15}
                        ],
                    },
                    {
                        "species_ref": pokemon_red_species_ref(0x68),
                        "hp": 100,
                        "max_hp": 100,
                        "level": 55,
                        "status": None,
                        "moves": [
                            {"move_ref": pokemon_red_move_ref(0x57), "pp": 10}
                        ],
                    },
                    {
                        "species_ref": pokemon_red_species_ref(0x84),
                        "hp": 100,
                        "max_hp": 100,
                        "level": 55,
                        "status": None,
                        "moves": [
                            {"move_ref": pokemon_red_move_ref(0x22), "pp": 15}
                        ],
                    },
                ],
            },
            "battle": {
                "opponent_species_ref": pokemon_red_species_ref(0x78),
                "opponent_level": 54,
            },
        }
    }

    resolved = resolve_battle_action_target(
        BattleAction.switch(),
        observation,
        catalog=RED_BATTLE_CATALOG,
    )
    authorized = authorize_switch_target(
        resolved,
        frozenset({BattleSwitchCapability.TEMPORARY_ROLE_PIVOT}),
        observation=observation,
    )

    assert resolved.party_slot == 2
    assert resolved.switch_basis is SwitchTargetBasis.MATCHUP
    assert authorized == resolved


def test_switch_target_requires_a_declared_executor_capability() -> None:
    resolved = resolve_battle_action_target(BattleAction.switch(), _observation())

    with pytest.raises(BattleActionTargetError, match="not declared"):
        authorize_switch_target(resolved, frozenset())

    assert authorize_switch_target(
        resolved,
        frozenset({BattleSwitchCapability.DIRECT}),
    ) == resolved


def test_switch_roles_choose_portable_executor_targets() -> None:
    observation = _observation(
        members=(
            (30, 100, 20, None),
            (50, 100, 25, None),
            (80, 100, 12, None),
        )
    )
    resolved = resolve_battle_action_target(BattleAction.switch(), observation)

    reset = authorize_switch_target(
        resolved,
        frozenset({BattleSwitchCapability.RESET_STAT_STAGES}),
        observation=observation,
    )
    protected = authorize_switch_target(
        resolved,
        frozenset({BattleSwitchCapability.PROTECTED_RECOVERY}),
        observation=observation,
    )

    assert reset.party_slot == 2
    assert protected.party_slot == 2


def test_temporary_role_pivot_selects_workhorse_then_returns_to_route_lead() -> None:
    observation = _observation(
        members=(
            (38, 56, 20, None),
            (72, 90, 33, None),
            (33, 33, 18, None),
        )
    )
    outward = authorize_switch_target(
        resolve_battle_action_target(BattleAction.switch(), observation),
        frozenset({BattleSwitchCapability.TEMPORARY_ROLE_PIVOT}),
        observation=observation,
    )
    return_observation = _observation(
        active=1,
        members=(
            (38, 56, 20, None),
            (72, 90, 33, None),
            (33, 33, 18, None),
        ),
    )
    returned = authorize_switch_target(
        resolve_battle_action_target(BattleAction.switch(), return_observation),
        frozenset({BattleSwitchCapability.TEMPORARY_ROLE_PIVOT}),
        observation=return_observation,
    )

    assert outward.party_slot == 2
    assert returned.party_slot == 1


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


def test_available_boost_stays_targetless() -> None:
    observation = _observation()
    features = observation["features"]
    assert isinstance(features, dict)
    features["resources"] = {"special_boost_count": 1}
    resolved = resolve_battle_action_target(
        BattleAction.boost(BattleBoostStat.SPECIAL),
        observation,
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
