"""Model-owned zero-PP attacks must not masquerade as forced mechanics."""

from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_red_forced_struggle import Native
from test_red_trainer_practice_episode import Session, _capture, _depleted_prepared
from test_red_trainer_practice_fit import _target
from test_red_trainer_practice_outcome_policy import _IndexedHead

from pokemon_red_completion import red_trainer_practice_episode as episode
from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.battle_actions import BattleAction, BattleActionKind
from pokemon_red_completion.battle_control_features import control_class_ref
from pokemon_red_completion.battle_runtime import BattleRuntimeError
from pokemon_red_completion.battle_semantics import BattleFeatureProjector
from pokemon_red_completion.red_battle_catalog import PokemonRedBattleCatalog
from pokemon_red_completion.red_forced_struggle import (
    ForcedStruggleExecution,
    execute_forced_struggle_turn,
    execute_model_struggle_turn,
    forced_struggle_available,
    model_struggle_available,
)
from pokemon_red_completion.red_trainer_practice_admission import _valid_forced_struggle
from pokemon_red_completion.red_trainer_practice_outcome_policy import (
    RedTrainerPracticeOutcomePolicy,
    TrainerOutcomePolicyError,
    _semantic_struggle_available,
)
from pokemon_red_completion.red_trainer_proposed_control import PROPOSED_CONTROL_SCHEMA
from pokemon_red_completion.scenario_lab import ScenarioPartition


def depleted_observation():
    observation = deepcopy(_target()["observation"])
    party = observation["features"]["party"]
    for member in [party["lead"], *party["members"]]:
        for move in member["moves"]:
            move["pp"] = 0
    return observation


def policy(choice=0, *, proposed=False, enabled=True):
    control = _IndexedHead(choice)
    control.schema_id = PROPOSED_CONTROL_SCHEMA if proposed else "unit-legacy-control"
    model = SimpleNamespace(control=control, switch=_IndexedHead(0), move=_IndexedHead(0))
    return RedTrainerPracticeOutcomePolicy(
        "unit",
        "unit-battle",
        model,
        mechanics_aware_choices=True,
        pp_depleted_switch_screen=True,
        allow_model_struggle=enabled,
    )


def prepared(observation):
    batch = BattleFeatureProjector(PokemonRedBattleCatalog()).project(observation)
    return SimpleNamespace(features=batch, supported_candidate_mask=batch.legal_mask)


def test_struggle_has_its_own_canonical_action_and_attack_history_class():
    action = BattleAction.struggle()
    assert action.kind is BattleActionKind.STRUGGLE
    assert action.move_slot is None and action.party_slot is None
    assert action.semantic_ref == "pokemon.core:battle:struggle"
    assert BattleAction.from_dict(action.public_dict()) == action
    assert control_class_ref(action) == control_class_ref(BattleAction.move(1))
    with pytest.raises(ValueError):
        BattleAction(BattleActionKind.STRUGGLE, move_slot=1)


@pytest.mark.parametrize("proposed", [False, True])
@pytest.mark.parametrize("choice", [0, 1])
def test_control_head_really_chooses_struggle_or_reserve_without_observation_edits(
    proposed, choice
):
    observation = depleted_observation()
    original = deepcopy(observation)
    actor = policy(choice, proposed=proposed)
    action = actor.choose_main(observation, prepared(observation))
    assert action.kind is (BattleActionKind.STRUGGLE if choice == 0 else BattleActionKind.SWITCH)
    if choice:
        assert action.party_slot == 2
    assert observation == original
    diagnostics = actor.last_decision_diagnostics
    assert diagnostics["control_choice"] == ("struggle" if choice == 0 else "switch")
    assert diagnostics["control_probabilities"] == ([1.0, 0.0] if choice == 0 else [0.0, 1.0])
    proposal = diagnostics["struggle_proposal"]
    assert proposal["projection_pp"] == [0.0]
    assert proposal["ordinary_move_legal_mask"] == [False]
    assert not proposal["observation_modified"] and not proposal["supplied_action"]
    assert all(pp == 0 for pp in proposal["source_visible_pp"])
    assert actor.history.history.action_counts[0 if choice == 0 else 5] == 1


def test_existing_post_switch_attack_obligation_now_has_a_real_zero_pp_attack():
    observation = depleted_observation()
    actor = policy(1)
    assert actor.choose_main(observation, prepared(observation)).kind is BattleActionKind.SWITCH
    assert actor.choose_main(observation, prepared(observation)).kind is BattleActionKind.STRUGGLE
    assert actor.last_decision_diagnostics["switch_masked_until_attack"]
    assert actor._unanswered_voluntary_switch_opponent is None


def test_disabled_opt_in_preserves_old_switch_only_behavior():
    observation = depleted_observation()
    actor = policy(enabled=False)
    assert actor.choose_main(observation, prepared(observation)).kind is BattleActionKind.SWITCH
    assert "struggle_proposal" not in actor.last_decision_diagnostics


@pytest.mark.parametrize("value", [1, "yes", None])
def test_model_struggle_flag_must_be_explicit_boolean(value):
    with pytest.raises(TrainerOutcomePolicyError, match="Struggle"):
        policy(enabled=value)


@pytest.mark.parametrize("field", ["mechanics_aware_choices", "pp_depleted_switch_screen"])
def test_opt_in_cannot_escape_the_existing_mechanics_scope(field):
    actor = policy()
    with pytest.raises(TrainerOutcomePolicyError, match="Struggle"):
        replace(actor, **{field: False})


@pytest.mark.parametrize("pp", [1, True, None, -1])
def test_semantic_offer_rejects_positive_disabled_or_invalid_pp(pp):
    observation = depleted_observation()
    observation["features"]["party"]["lead"]["moves"][0]["pp"] = pp
    observation["features"]["battle"]["player_disabled_move_slot"] = 1
    assert not _semantic_struggle_available(observation)


def test_living_reserve_is_legal_for_selected_but_never_forced_struggle(monkeypatch):
    from pokemon_red_completion import battle_runtime

    monkeypatch.setattr(battle_runtime, "_preserve_moves_at_learning_prompt", lambda *a, **k: False)

    class WithReserve(Native):
        def execute(self, action):
            result = super().execute(action)
            if action.kind is MacroActionKind.CANCEL:
                self.raw = replace(self.raw, party_hp=(self.raw.battler_hp, 80))
            return result

    native = WithReserve()
    native.raw = replace(native.raw, party_hp=(100, 80))
    assert model_struggle_available(native.raw) and not forced_struggle_available(native.raw)
    with pytest.raises(BattleRuntimeError):
        execute_forced_struggle_turn(native, native, expected_map=120)
    assert native.actions == []
    result = execute_model_struggle_turn(native, native, expected_map=120)
    assert result.public_dict()["authority"] == "learner"
    assert result.public_dict()["schema"] == "pokemon.red.model-struggle-turn.v1"
    assert result.final_state.party_hp == (90, 80)
    assert result.final_state.battler_pp == (0, 0, 0, 0)
    assert sum(a.kind is MacroActionKind.CONFIRM for a in native.actions) == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"active_party_pp": (1, 0, 0, 0)},
        {"active_party_pp": (1, 0, 0, 0), "player_disabled_move_slot": 1},
        {"active_party_pp": None},
        {"active_party_hp": 0},
        {"battle_state": 1},
    ],
)
def test_selected_struggle_still_refuses_invalid_boundary_before_inputs(changes):
    native = Native()
    native.raw = replace(native.raw, party_hp=(100, 80), **changes)
    with pytest.raises(BattleRuntimeError):
        execute_model_struggle_turn(native, native, expected_map=120)
    assert native.actions == []


@pytest.mark.parametrize(
    "partition,enabled,pp,accepted",
    [
        (ScenarioPartition.DEVELOPMENT, True, 0, True),
        (ScenarioPartition.TRAIN, True, 0, False),
        (ScenarioPartition.DEVELOPMENT, False, 0, False),
        (ScenarioPartition.DEVELOPMENT, True, 1, False),
    ],
)
def test_episode_retains_actor_choice_and_refuses_training_or_unscoped_execution(
    tmp_path, monkeypatch, partition, enabled, pp, accepted
):
    capture = _capture(tmp_path, partition=partition)
    session = Session()
    session.raw = replace(session.raw, active_party_pp=(pp, 0, 0, 0), enemy_party_hp=(10,))
    session.frame_count = 0
    snapshot = SimpleNamespace(to_dict=lambda: {"features": {"battle": {"kind": "trainer"}}})
    monkeypatch.setattr(episode, "PokemonRedStateReader", lambda loaded: loaded)
    monkeypatch.setattr(
        episode.PokemonRedObservationEncoder,
        "from_state_reader",
        lambda _reader: SimpleNamespace(snapshot_from_raw=lambda _raw: snapshot),
    )
    monkeypatch.setattr(
        episode, "prepare_red_battle_scenario", lambda *a, **k: _depleted_prepared()
    )
    monkeypatch.setattr(episode, "canonical_sha256", lambda _value: "b" * 64)
    calls = []

    def execute(reader, actions, **kwargs):
        calls.append("native")
        before = reader.raw
        reader.raw = replace(before, enemy_hp=0, enemy_party_hp=(0,), battle_state=0)
        reader.frame_count += 122
        return ForcedStruggleExecution(before, reader.raw, 2, 122, (0,), authority="learner")

    monkeypatch.setattr(episode, "execute_model_struggle_turn", execute)

    class Actor:
        policy_id = "local-model"

        def choose_main(self, *args):
            return BattleAction.struggle()

    kwargs = dict(
        capture=capture,
        session_factory=lambda: session,
        policy=Actor(),
        allow_forced_struggle=enabled,
    )
    if not accepted:
        with pytest.raises(episode.RedTrainerPracticeEpisodeError, match="Struggle"):
            episode.run_red_trainer_practice_episode(**kwargs)
        assert not calls and session.frame_count == 0
        return
    result = episode.run_red_trainer_practice_episode(**kwargs)
    report = result.public_dict()
    assert result.battle_won and report["player_turn_count"] == 1
    assert report["action_counts"]["model_struggle"] == 1
    assert report["metrics"]["opponent_faints"] == 1
    decision = result.decisions[0]
    assert decision["authority"] == "learner" and decision["legal_party_slots"] == [2]
    assert decision["semantic_action"] == BattleAction.struggle().public_dict()
    assert not _valid_forced_struggle(decision)
