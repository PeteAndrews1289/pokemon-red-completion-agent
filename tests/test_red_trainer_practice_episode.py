from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import replace
from types import SimpleNamespace

import pytest

from pokemon_red_completion import red_trainer_practice_episode as episode
from pokemon_red_completion.battle_actions import BattleAction
from pokemon_red_completion.battle_outcome_learning import BattleTurnOutcome
from pokemon_red_completion.battle_scenario_capture import (
    build_battle_scenario_capture_payload,
    open_battle_scenario_capture,
)
from pokemon_red_completion.battle_semantics import (
    FEATURE_NAMES,
    FEATURE_SCHEMA_ID,
    BattleFeatureBatch,
)
from pokemon_red_completion.observation import BattleMenuPhase, RawGameState
from pokemon_red_completion.red_battle_scenario import PreparedRedBattleScenario
from pokemon_red_completion.scenario_lab import ScenarioPartition


def _capture(tmp_path):
    state = b"private synthetic trainer state"
    state_path = tmp_path / "trainer.state"
    manifest_path = tmp_path / "trainer.state.json"
    state_path.write_bytes(state)
    manifest_path.write_bytes(
        build_battle_scenario_capture_payload(
            capture_id="trainer-unit",
            root_lineage_id="train-root-unit",
            partition=ScenarioPartition.TRAIN,
            state_bytes=state,
            initial_observation_sha256="b" * 64,
            source_commit="c" * 40,
            expected_map=120,
            expected_battle_state=2,
        )
    )
    return open_battle_scenario_capture(state_path, manifest_path)


def _prepared():
    vector = tuple(0.0 for _ in FEATURE_NAMES)
    return PreparedRedBattleScenario(
        initial_observation_sha256="b" * 64,
        features=BattleFeatureBatch(
            feature_names=FEATURE_NAMES,
            candidate_vectors=(vector, vector),
            legal_mask=(True, True),
            current_pp=(10.0, 10.0),
            slot_indices=(0, 1),
            schema_id=FEATURE_SCHEMA_ID,
        ),
    )


class Session(AbstractContextManager):
    def __init__(self):
        self.raw = RawGameState(
            game_started=True,
            map_id=120,
            player_x=2,
            player_y=2,
            party_count=2,
            battle_state=2,
            party_hp=(40, 35),
            active_party_index=0,
            active_party_hp=40,
            enemy_hp=10,
        )
        self.loaded = False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def load_state_bytes(self, _payload):
        self.loaded = True

    def read(self):
        return self.raw

    def read_battle_menu_state(self, _raw):
        return SimpleNamespace(phase=BattleMenuPhase.MAIN)

    def trainer_switch_prompt_visible(self, _raw):
        return False

    def read_enemy_party_roster_hp(self):
        return (0,)


@pytest.mark.parametrize("opening_idle_frames", (0, 4))
def test_episode_executes_exact_model_move_and_records_terminal(
    tmp_path, monkeypatch, opening_idle_frames
):
    capture = _capture(tmp_path)
    session = Session()
    ticks = []
    session.tick = ticks.append
    if opening_idle_frames:
        monkeypatch.setattr(episode, "canonical_sha256", lambda _value: "b" * 64)
    snapshot = SimpleNamespace(to_dict=lambda: {"features": {"battle": {"kind": "trainer"}}})
    monkeypatch.setattr(episode, "PokemonRedStateReader", lambda loaded: loaded)
    monkeypatch.setattr(
        episode.PokemonRedObservationEncoder,
        "from_state_reader",
        lambda _reader: SimpleNamespace(snapshot_from_raw=lambda _raw: snapshot),
    )
    monkeypatch.setattr(
        episode, "prepare_red_battle_scenario", lambda *_args, **_kwargs: _prepared()
    )
    chosen: list[int] = []

    def execute(_reader, _actions, **kwargs):
        chosen.append(kwargs["selected_slot"])
        session.raw = RawGameState(True, 120, 2, 2, 2, 0, party_hp=(40, 35))
        return object()

    monkeypatch.setattr(episode, "execute_bounded_battle_move_turn", execute)
    monkeypatch.setattr(
        episode,
        "project_red_battle_turn_outcome",
        lambda _execution: BattleTurnOutcome(True, 1.0, 0.0, True, False, True, 2, 500, 0),
    )

    class Policy:
        policy_id = "test-model"

        def choose_main(self, _observation, _prepared):
            return BattleAction.move(2)

        def choose_switch(self, *_args, **_kwargs):
            raise AssertionError("no switch requested")

    events = []
    result = episode.run_red_trainer_practice_episode(
        capture,
        session_factory=lambda: session,
        policy=Policy(),
        event_sink=events.append,
        opening_idle_frames=opening_idle_frames,
    )
    assert session.loaded
    assert ticks == ([opening_idle_frames] if opening_idle_frames else [])
    assert result.opening_idle_frames == opening_idle_frames
    assert chosen == [2]
    assert result.battle_won
    assert result.stop_reason == "battle_won"
    assert result.decisions[0]["kind"] == "attack"
    assert result.decisions[0]["observation"] == {"features": {"battle": {"kind": "trainer"}}}
    assert result.public_dict()["schema"] == "pokemon.red.trainer-practice-model-episode.v4"
    assert result.final_observation == {"features": {"battle": {"kind": "trainer"}}}
    assert result.public_dict()["teacher_queries"] == 0
    assert [event["event"] for event in events] == [
        *(["opening_timing_started", "opening_timing_completed"] if opening_idle_frames else []),
        "episode_started",
        "decision_started",
        "model_input_prepared",
        "choice_recorded",
        "decision_completed",
    ]
    assert result.decisions[0]["legal_move_slots"] == [1, 2]
    assert result.decisions[0]["state_before"]["party_hp"] == [40, 35]
    assert result.decisions[0]["state_after"]["party_hp"] == [40, 35]
    assert result.public_dict()["action_counts"]["attack"] == 1
    assert result.public_dict()["elapsed_ns"] > 0


def test_terminal_party_defeat_is_retained_as_a_loss(tmp_path):
    capture = _capture(tmp_path)
    final = RawGameState(True, 120, 2, 2, 2, 0, party_hp=(0, 0))
    receipt = episode._receipt(
        capture, "unit-policy", (), final, (25,), {"features": {"battle": None}}
    )
    assert receipt.stop_reason == "party_defeated"
    assert receipt.battle_won is False


def test_episode_rejects_impossible_level_up_hp_before_outcome_label(tmp_path, monkeypatch):
    capture = _capture(tmp_path)
    session = Session()
    session.raw = replace(
        session.raw,
        party_max_hp=(90, 90),
        active_party_max_hp=90,
        party_levels=(30, 32),
        active_party_level=30,
    )
    snapshot = SimpleNamespace(to_dict=lambda: {"features": {"battle": {"kind": "trainer"}}})
    monkeypatch.setattr(episode, "PokemonRedStateReader", lambda loaded: loaded)
    monkeypatch.setattr(
        episode.PokemonRedObservationEncoder,
        "from_state_reader",
        lambda _reader: SimpleNamespace(snapshot_from_raw=lambda _raw: snapshot),
    )
    monkeypatch.setattr(
        episode, "prepare_red_battle_scenario", lambda *_args, **_kwargs: _prepared()
    )
    projected = []

    def execute(_reader, _actions, **_kwargs):
        session.raw = replace(
            session.raw,
            party_hp=(65535, 35),
            active_party_hp=65535,
            active_party_level=31,
        )
        return object()

    monkeypatch.setattr(episode, "execute_bounded_battle_move_turn", execute)
    monkeypatch.setattr(
        episode, "project_red_battle_turn_outcome", lambda _execution: projected.append(True)
    )

    class Policy:
        policy_id = "test-invalid-hp-model"

        def choose_main(self, _observation, _prepared):
            return BattleAction.move(2)

        def choose_switch(self, *_args, **_kwargs):
            raise AssertionError("no switch requested")

    events = []
    with pytest.raises(episode.RedTrainerPracticeEpisodeError, match="HP exceeds"):
        episode.run_red_trainer_practice_episode(
            capture, session_factory=lambda: session, policy=Policy(), event_sink=events.append
        )
    assert projected == []
    assert events[-1]["event"] == "choice_recorded"


def test_episode_rejects_unsupported_model_action_before_execution(tmp_path, monkeypatch):
    capture = _capture(tmp_path)
    session = Session()
    monkeypatch.setattr(episode, "PokemonRedStateReader", lambda loaded: loaded)
    monkeypatch.setattr(
        episode.PokemonRedObservationEncoder,
        "from_state_reader",
        lambda _reader: SimpleNamespace(
            snapshot_from_raw=lambda _raw: SimpleNamespace(to_dict=lambda: {})
        ),
    )
    monkeypatch.setattr(
        episode, "prepare_red_battle_scenario", lambda *_args, **_kwargs: _prepared()
    )

    class Policy:
        policy_id = "invalid-model"

        def choose_main(self, _observation, _prepared):
            return BattleAction.move(3)

        def choose_switch(self, *_args, **_kwargs):
            raise AssertionError("no switch requested")

    events = []
    with pytest.raises(episode.RedTrainerPracticeEpisodeError, match="unsupported move"):
        episode.run_red_trainer_practice_episode(
            capture, session_factory=lambda: session, policy=Policy(), event_sink=events.append
        )
    assert events[-1]["event"] == "choice_recorded"
    assert events[-1]["selected_action"]["move_slot"] == 3


def test_episode_records_party_defeat_without_asking_for_impossible_switch(tmp_path, monkeypatch):
    capture = _capture(tmp_path)
    session = Session()
    session.raw = RawGameState(
        True, 120, 2, 2, 2, 2, party_hp=(0, 0), active_party_index=0, active_party_hp=0
    )
    monkeypatch.setattr(episode, "PokemonRedStateReader", lambda loaded: loaded)
    monkeypatch.setattr(
        episode.PokemonRedObservationEncoder,
        "from_state_reader",
        lambda _reader: SimpleNamespace(
            snapshot_from_raw=lambda _raw: SimpleNamespace(to_dict=lambda: {})
        ),
    )
    monkeypatch.setattr(
        episode, "prepare_red_battle_scenario", lambda *_args, **_kwargs: _prepared()
    )

    class Policy:
        policy_id = "defeated-model"

        def choose_main(self, *_args):
            raise AssertionError("defeated party has no attack")

        def choose_switch(self, *_args, **_kwargs):
            raise AssertionError("defeated party has no switch")

    result = episode.run_red_trainer_practice_episode(
        capture, session_factory=lambda: session, policy=Policy()
    )
    assert not result.battle_won
    assert result.stop_reason == "party_defeated"
    assert result.decisions == ()


def test_episode_accepts_authenticated_trainer_prompt_as_first_boundary(tmp_path, monkeypatch):
    capture = _capture(tmp_path)
    session = Session()
    monkeypatch.setattr(episode, "PokemonRedStateReader", lambda loaded: loaded)
    monkeypatch.setattr(
        episode.PokemonRedObservationEncoder,
        "from_state_reader",
        lambda _reader: SimpleNamespace(
            snapshot_from_raw=lambda _raw: SimpleNamespace(to_dict=lambda: {"prompt": True})
        ),
    )
    monkeypatch.setattr(episode, "canonical_sha256", lambda _value: "b" * 64)
    monkeypatch.setattr(session, "trainer_switch_prompt_visible", lambda raw: raw.battle_state == 2)

    def resolve(_actions, _reader, _session, **_kwargs):
        session.raw = RawGameState(True, 120, 2, 2, 2, 0, party_hp=(40, 35))

    monkeypatch.setattr(episode, "resolve_trainer_switch_prompt", resolve)

    class Policy:
        policy_id = "prompt-unit-model"

        def choose_main(self, *_args):
            raise AssertionError("prompt must come first")

        def choose_switch(self, _observation, _legal_slots, *, forced, may_decline):
            assert not forced and may_decline
            return None

    result = episode.run_red_trainer_practice_episode(
        capture, session_factory=lambda: session, policy=Policy()
    )
    assert result.decisions[0]["kind"] == "switch_prompt"
    assert result.decisions[0]["party_slot"] is None
