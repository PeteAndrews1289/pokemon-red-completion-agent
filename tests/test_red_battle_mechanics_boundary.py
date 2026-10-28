from copy import deepcopy
from types import SimpleNamespace

import pytest
from test_red_trainer_practice_features import _observation
from test_red_trainer_practice_outcome_policy import _IndexedHead

from pokemon_red_completion.battle_actions import BattleActionKind
from pokemon_red_completion.battle_semantics import BattleFeatureProjector
from pokemon_red_completion.red_battle_catalog import (
    PokemonRedBattleCatalog,
    pokemon_red_species_ref,
)
from pokemon_red_completion.red_battle_mechanics_boundary import immunity_choices
from pokemon_red_completion.red_trainer_practice_outcome_policy import (
    RedTrainerPracticeOutcomePolicy,
)


def fixture(moves=(33, 55), *, foe_type="ghost", reserve_move=33):
    obs = _observation()
    catalog = PokemonRedBattleCatalog()
    foe = next(
        s
        for s in catalog.species_ids
        if foe_type in catalog.resolve_species(pokemon_red_species_ref(s)).types
    )
    obs["features"]["battle"]["opponent_species_ref"] = pokemon_red_species_ref(foe)
    party = obs["features"]["party"]
    party["lead"]["moves"] = [
        dict(slot_index=i, move_ref=f"pokemon.red.gb.us.rev0:move:{m:03d}", pp=10)
        for i, m in enumerate(moves)
    ]
    for member in party["members"][1:]:
        member["moves"] = [
            dict(slot_index=0, move_ref=f"pokemon.red.gb.us.rev0:move:{reserve_move:03d}", pp=10)
        ]
    return obs, catalog


def prepare(obs, catalog):
    batch = BattleFeatureProjector(catalog).project(obs)
    prepared = SimpleNamespace(features=batch, supported_candidate_mask=batch.legal_mask)
    legal = tuple(
        s + 1 for s, allowed in zip(batch.slot_indices, batch.legal_mask, strict=True) if allowed
    )
    return prepared, legal


def test_immunity_screen_precedes_damage_reference_and_is_opt_in():
    obs, catalog = fixture()
    prepared, _ = prepare(obs, catalog)
    control = _IndexedHead(0)
    control.schema_id = "unit-control"
    actor = SimpleNamespace(
        move=_IndexedHead(0),
        damage_reference=_IndexedHead(0),
        switch=_IndexedHead(0),
        control=control,
    )
    old = RedTrainerPracticeOutcomePolicy("test", "battle", actor)
    new = RedTrainerPracticeOutcomePolicy("test", "battle", actor, mechanics_aware_choices=True)
    assert old.choose_main(obs, prepared).move_slot == 1
    assert new.choose_main(obs, prepared).move_slot == 2
    assert new.last_decision_diagnostics["mechanics_boundary"]["removed_move_slots"] == [1]


@pytest.mark.parametrize("productive", [False, True])
def test_diagnostic_stay_is_disclosed_and_does_not_change_move_head(productive):
    obs, catalog = fixture((33, 55) if productive else (33,), reserve_move=55)
    prepared, _ = prepare(obs, catalog)
    control = _IndexedHead(1)
    control.schema_id = "unit-control"
    actor = SimpleNamespace(move=_IndexedHead(0), switch=_IndexedHead(0), control=control)
    policy = RedTrainerPracticeOutcomePolicy(
        "diagnostic",
        "battle",
        actor,
        mechanics_aware_choices=True,
        diagnostic_stay_when_productive=True,
    )
    action = policy.choose_main(obs, prepared)
    assert policy.model is actor
    if productive:
        assert action.kind is BattleActionKind.SELECT_MOVE and action.move_slot == 2
        assert policy.last_decision_diagnostics["diagnostic_control"] == {
            "schema": "pokemon.red.diagnostic-stay.v1",
            "supplied_not_learned": True,
            "productive_attack_available": True,
            "forced_attack": True,
            "overrode_learned_switch": True,
        }
    else:
        assert action.kind is BattleActionKind.SWITCH
        assert policy.last_decision_diagnostics["forced_by_mechanics"] is True


@pytest.mark.parametrize("value,mechanics", [(1, True), (True, False)])
def test_diagnostic_stay_rejects_implicit_enablement(value, mechanics):
    with pytest.raises(ValueError, match="diagnostic stay"):
        RedTrainerPracticeOutcomePolicy(
            "diagnostic",
            "battle",
            object(),
            mechanics_aware_choices=mechanics,
            diagnostic_stay_when_productive=value,
        )


@pytest.mark.parametrize("forced", [True, False])
def test_diagnostic_stay_does_not_override_replacement_choices(forced):
    import numpy as np

    obs, _ = fixture()
    control = _IndexedHead(1)
    control.schema_id = "unit-control"
    control.probabilities = lambda rows: np.array([0.0, 1.0])
    model = SimpleNamespace(move=_IndexedHead(0), switch=_IndexedHead(0), control=control)
    actors = [
        RedTrainerPracticeOutcomePolicy(
            "same",
            "battle",
            model,
            mechanics_aware_choices=True,
            diagnostic_stay_when_productive=diagnostic,
        )
        for diagnostic in (False, True)
    ]
    choices = [a.choose_switch(obs, (2,), forced=forced, may_decline=not forced) for a in actors]
    assert choices == [2, 2]
    assert actors[0].last_decision_diagnostics == actors[1].last_decision_diagnostics


@pytest.mark.parametrize(
    "moves,foe_type,expected",
    [
        ((85, 55), "ground", (2,)),
        ((52, 55), "water", (1, 2)),  # Resistance is not immunity; do not select the strongest.
        ((33, 45, 55), "ghost", (2, 3)),  # Growl is not a damaging Normal move.
        ((33, 69), "ghost", (1, 2)),  # Special damage is deliberately not inferred.
    ],
)
def test_type_chart_and_special_move_boundaries(moves, foe_type, expected):
    obs, catalog = fixture(moves, foe_type=foe_type)
    prepared, legal = prepare(obs, catalog)
    assert immunity_choices(obs, prepared, catalog, legal)[0] == expected


@pytest.mark.parametrize("reason", ["pp", "disabled", "unsupported"])
def test_unusable_effective_attack_does_not_remove_last_available_move(reason):
    obs, catalog = fixture()
    if reason == "pp":
        obs["features"]["party"]["lead"]["moves"][1]["pp"] = 0
    if reason == "disabled":
        obs["features"]["battle"]["player_disabled_move_slot"] = 2
    prepared, legal = prepare(obs, catalog)
    if reason == "unsupported":
        legal = (1,)
    assert immunity_choices(obs, prepared, catalog, legal) == ((1,), (), ())


def test_all_immune_escape_preserves_learned_reserve_selection():
    obs, catalog = fixture((33,), reserve_move=55)
    prepared, _ = prepare(obs, catalog)
    control = _IndexedHead(0)
    control.schema_id = "unit-control"
    actor = SimpleNamespace(move=_IndexedHead(0), switch=_IndexedHead(1), control=control)
    policy = RedTrainerPracticeOutcomePolicy("test", "battle", actor, mechanics_aware_choices=True)
    policy._unanswered_voluntary_switch_opponent = 0
    action = policy.choose_main(obs, prepared)
    assert action.kind is BattleActionKind.SWITCH and action.party_slot == 3
    assert policy.last_decision_diagnostics["forced_by_mechanics"]
    assert "forced_by_legality" not in policy.last_decision_diagnostics
    assert policy.last_decision_diagnostics["mechanics_boundary"]["productive_reserve_slots"] == [
        2,
        3,
    ]
    # Once the productive reserve is active, ordinary anti-loop behavior returns.
    after = deepcopy(obs)
    party = after["features"]["party"]
    party["active_index"] = 2
    party["lead"] = party["members"][2]
    prepared, _ = prepare(after, catalog)
    assert policy.choose_main(after, prepared).kind is BattleActionKind.SELECT_MOVE
    assert policy.last_decision_diagnostics["switch_masked_until_attack"]


def test_depleted_or_fainted_reserves_do_not_create_a_false_escape():
    obs, catalog = fixture((33,), reserve_move=55)
    obs["features"]["party"]["members"][1]["hp"] = 0
    obs["features"]["party"]["members"][2]["moves"][0]["pp"] = 0
    prepared, legal = prepare(obs, catalog)
    assert immunity_choices(obs, prepared, catalog, legal) == ((1,), (), ())


def test_status_remains_an_alternative_to_switching():
    obs, catalog = fixture((33, 45), reserve_move=55)
    prepared, legal = prepare(obs, catalog)
    assert immunity_choices(obs, prepared, catalog, legal) == ((2,), (2, 3), (1,))


def test_mechanics_option_rejects_truthy_nonboolean():
    with pytest.raises(ValueError, match="explicit boolean"):
        RedTrainerPracticeOutcomePolicy("test", "battle", None, mechanics_aware_choices=1)


@pytest.mark.parametrize("move", [68, 120])
def test_unsupported_reserve_attacks_do_not_create_a_false_escape(move):
    # Counter and Selfdestruct are not supported by this actor's damage surface.
    from pokemon_red_completion.red_battle_mechanics_boundary import productive_reserve_slots

    obs, catalog = fixture((85,), foe_type="ground", reserve_move=move)
    assert productive_reserve_slots(obs, catalog) == ()


def test_escape_memory_blocks_only_repeated_ineffective_voluntary_returns():
    obs, catalog = fixture((55,), reserve_move=33)
    policy = RedTrainerPracticeOutcomePolicy("test", "battle", None, mechanics_aware_choices=True)
    history = SimpleNamespace(opponent_index=0)
    assert policy._mechanics_switch_slots(obs, (2, 3), history) == (2, 3)
    policy._mechanics_escaped_members.add(2)
    assert policy._mechanics_switch_slots(obs, (2, 3), history) == (3,)
    # Changed capability restores the member, rather than a permanent slot ban.
    obs["features"]["party"]["members"][1]["moves"][0]["move_ref"] = (
        "pokemon.red.gb.us.rev0:move:055"
    )
    assert policy._mechanics_switch_slots(obs, (2, 3), history) == (2, 3)
    obs["features"]["party"]["members"][1]["moves"][0]["move_ref"] = (
        "pokemon.red.gb.us.rev0:move:033"
    )
    assert policy._mechanics_switch_slots(obs, (2, 3), SimpleNamespace(opponent_index=1)) == (2, 3)
