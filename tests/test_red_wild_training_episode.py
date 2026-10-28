"""Wild knockout scope must not inherit trainer roster assumptions."""

from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_red_trainer_practice_episode import Session, _prepared

from pokemon_red_completion import red_trainer_practice_episode as ep
from pokemon_red_completion.battle_actions import BattleAction
from pokemon_red_completion.battle_outcome_learning import BattleTurnOutcome
from pokemon_red_completion.battle_scenario_capture import (
    build_battle_scenario_capture_payload,
    open_battle_scenario_capture,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition


def _wild_capture(tmp_path, battle=1, partition=ScenarioPartition.DEVELOPMENT):
    state = tmp_path / "wild.state"
    manifest = tmp_path / "wild.json"
    state.write_bytes(b"synthetic wild state")
    manifest.write_bytes(
        build_battle_scenario_capture_payload(
            capture_id="wild-unit",
            root_lineage_id="wild-unit-root",
            partition=partition,
            state_bytes=state.read_bytes(),
            initial_observation_sha256="b" * 64,
            source_commit="c" * 40,
            expected_map=120,
            expected_battle_state=battle,
        )
    )
    return open_battle_scenario_capture(state, manifest)


@pytest.mark.parametrize("enemy_hp,result,won", [(0, 0, True), (8, 0, False), (0, 2, False)])
@pytest.mark.parametrize("limit", [1, 3])
def test_wild_actual_knockout_not_escape(tmp_path, monkeypatch, enemy_hp, result, won, limit):
    capture = _wild_capture(tmp_path)
    session = Session()
    session.raw = replace(session.raw, battle_state=1)
    session.read_enemy_party_roster_hp = lambda: pytest.fail("wild must not read trainer roster")
    snapshot = SimpleNamespace(to_dict=lambda: {"features": {"battle": {"kind": "wild"}}})
    monkeypatch.setattr(ep, "PokemonRedStateReader", lambda s: s)
    monkeypatch.setattr(
        ep.PokemonRedObservationEncoder,
        "from_state_reader",
        lambda r: SimpleNamespace(snapshot_from_raw=lambda raw: snapshot),
    )
    monkeypatch.setattr(ep, "prepare_red_battle_scenario", lambda *a, **k: _prepared())

    def execute(reader, actions, **kwargs):
        assert kwargs["expected_battle_state"] == 1
        assert kwargs["selected_slot"] == 2
        session.raw = replace(session.raw, battle_state=0, enemy_hp=enemy_hp, battle_result=result)
        return object()

    monkeypatch.setattr(ep, "execute_bounded_battle_move_turn", execute)
    monkeypatch.setattr(
        ep,
        "project_red_battle_turn_outcome",
        lambda e: BattleTurnOutcome(True, 1.0, 0.0, True, False, True, 2, 500, 0),
    )
    policy = SimpleNamespace(policy_id="model", choose_main=lambda *a: BattleAction.move(2))
    outcome = ep.run_red_trainer_practice_episode(
        capture,
        session_factory=lambda: session,
        policy=policy,
        wild_training=True,
        max_decisions=limit,
    )
    assert outcome.battle_won is won
    assert len(outcome.decisions) == 1
    assert outcome.final_enemy_roster_hp == (enemy_hp,)


@pytest.mark.parametrize(
    "battle,partition,optin",
    [
        (1, ScenarioPartition.DEVELOPMENT, False),
        (2, ScenarioPartition.DEVELOPMENT, True),
        (1, ScenarioPartition.TRAIN, True),
        (1, ScenarioPartition.DEVELOPMENT, 1),
    ],
)
def test_wild_scope_is_explicit_before_session(tmp_path, battle, partition, optin):
    capture = _wild_capture(tmp_path, battle, partition)
    with pytest.raises(ep.RedTrainerPracticeEpisodeError):
        ep.run_red_trainer_practice_episode(
            capture,
            session_factory=lambda: pytest.fail("no session may open"),
            policy=SimpleNamespace(policy_id="model"),
            wild_training=optin,
        )
