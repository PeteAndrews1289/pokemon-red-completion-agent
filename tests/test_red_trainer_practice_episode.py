from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass, replace
from types import SimpleNamespace

import pytest

from pokemon_red_completion import red_trainer_practice_episode as episode
from pokemon_red_completion.battle_actions import BattleAction
from pokemon_red_completion.battle_outcome_learning import BattleTurnOutcome
from pokemon_red_completion.battle_scenario_capture import (
    OBSERVATION_SCHEMA_V2,
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


def _capture(tmp_path, *, wild=False, status=False, partition=None):
    state = b"private synthetic trainer state"
    state_path = tmp_path / "trainer.state"
    manifest_path = tmp_path / "trainer.state.json"
    state_path.write_bytes(state)
    manifest_path.write_bytes(
        build_battle_scenario_capture_payload(
            capture_id="trainer-unit",
            root_lineage_id="train-root-unit",
            partition=partition or (
                ScenarioPartition.DEVELOPMENT if wild else ScenarioPartition.TRAIN),
            state_bytes=state,
            initial_observation_sha256="b" * 64,
            source_commit="c" * 40,
            expected_map=120,
            expected_battle_state=1 if wild else 2,
            **({"observation_schema": OBSERVATION_SCHEMA_V2} if status else {}),
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


def _depleted_prepared():
    vector = tuple(0.0 for _ in FEATURE_NAMES)
    return PreparedRedBattleScenario(
        initial_observation_sha256="b" * 64,
        allow_no_attack=True,
        features=BattleFeatureBatch(
            feature_names=FEATURE_NAMES,
            candidate_vectors=(vector,),
            legal_mask=(False,),
            current_pp=(0.0,),
            slot_indices=(0,),
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


@pytest.mark.parametrize("train_diagnostic", [False, True])
def test_wild_switch_double_ko_finishes_without_forced_switch_query(
    tmp_path, monkeypatch, train_diagnostic
):
    from pokemon_red_completion.actions import MacroActionKind

    capture = _capture(tmp_path, wild=True,
                       partition=ScenarioPartition.TRAIN if train_diagnostic else None)
    session = Session()
    session.raw = replace(session.raw, battle_state=1, battle_result=0)
    snapshot = SimpleNamespace(to_dict=lambda: {"features": {"battle": {"kind": "wild"}}})
    monkeypatch.setattr(episode, "PokemonRedStateReader", lambda loaded: loaded)
    monkeypatch.setattr(
        episode.PokemonRedObservationEncoder,
        "from_state_reader",
        lambda _reader: SimpleNamespace(snapshot_from_raw=lambda _raw: snapshot),
    )
    monkeypatch.setattr(episode, "prepare_red_battle_scenario", lambda *_a, **_k: _prepared())

    def switch(_actions, _reader, _session, index, **_kwargs):
        assert index == 1
        session.raw = replace(
            session.raw, active_party_index=1, active_party_hp=0, party_hp=(40, 0), enemy_hp=0
        )

    monkeypatch.setattr(episode, "switch_active_battler", switch)

    class Actions:
        def execute(self, action):
            if action.kind is MacroActionKind.CONFIRM:
                session.raw = replace(session.raw, battle_state=0)

    class Policy:
        policy_id = "test-wild-switch"

        def choose_main(self, *_args):
            return BattleAction.switch(2)

        def choose_switch(self, *_args, **_kwargs):
            raise AssertionError("terminal double KO must not request replacement")

    result = episode.run_red_trainer_practice_episode(
        capture,
        session_factory=lambda: session,
        policy=Policy(),
        action_executor=Actions(),
        wild_training=True,
        train_wild_diagnostic=train_diagnostic,
    )
    assert result.battle_won and result.final_battle_state == 0
    assert [d["kind"] for d in result.decisions] == ["voluntary_switch"]


@pytest.mark.parametrize("stale_roster", [False, True])
def test_trainer_final_switch_double_ko_finishes_without_replacement_choice(tmp_path, monkeypatch, stale_roster):
    from pokemon_red_completion.actions import MacroActionKind

    capture = _capture(tmp_path)
    session = Session()
    roster = [0, 57] if stale_roster else [0]
    session.read_enemy_party_roster_hp = lambda: tuple(roster)
    snapshot = SimpleNamespace(to_dict=lambda: {"features": {"battle": {"kind": "trainer"}}})
    monkeypatch.setattr(episode, "PokemonRedStateReader", lambda loaded: loaded)
    monkeypatch.setattr(episode.PokemonRedObservationEncoder, "from_state_reader",
        lambda _reader: SimpleNamespace(snapshot_from_raw=lambda _raw: snapshot))
    monkeypatch.setattr(episode, "prepare_red_battle_scenario", lambda *_a, **_k: _prepared())

    def switch(_actions, _reader, _session, index, **_kwargs):
        assert index == 1
        session.raw = replace(session.raw, active_party_index=1, active_party_hp=0,
            party_hp=(40, 0), enemy_hp=0, enemy_party_position=len(roster)-1)

    monkeypatch.setattr(episode, "switch_active_battler", switch)

    class Actions:
        def execute(self, action):
            if action.kind is MacroActionKind.CONFIRM:
                roster[:] = [0] * len(roster)
                session.raw = replace(session.raw, battle_state=0)

    class Policy:
        policy_id = "test-trainer-double-ko"

        def choose_main(self, *_args):
            return BattleAction.switch(2)

        def choose_switch(self, *_args, **_kwargs):
            raise AssertionError("finished trainer fight has no replacement decision")

    result = episode.run_red_trainer_practice_episode(capture, session_factory=lambda: session,
        policy=Policy(), action_executor=Actions())
    assert result.battle_won and result.final_battle_state == 0
    assert [d["kind"] for d in result.decisions] == ["voluntary_switch"]


def test_depleted_party_stops_before_unsupported_struggle_without_policy_choice(
    tmp_path, monkeypatch
):
    capture = _capture(tmp_path)
    session = Session()
    session.raw = replace(session.raw, party_hp=(40, 0))
    snapshot = SimpleNamespace(to_dict=lambda: {"features": {"battle": {"kind": "trainer"}}})
    monkeypatch.setattr(episode, "PokemonRedStateReader", lambda loaded: loaded)
    monkeypatch.setattr(
        episode.PokemonRedObservationEncoder,
        "from_state_reader",
        lambda _reader: SimpleNamespace(snapshot_from_raw=lambda _raw: snapshot),
    )
    monkeypatch.setattr(
        episode, "prepare_red_battle_scenario", lambda *_args, **_kwargs: _depleted_prepared()
    )

    class Policy:
        policy_id = "test-model"

        def choose_main(self, *_args):
            raise AssertionError("unsupported Struggle must not masquerade as a model choice")

    events = []
    result = episode.run_red_trainer_practice_episode(
        capture, session_factory=lambda: session, policy=Policy(), event_sink=events.append
    )
    assert result.stop_reason == "unsupported_struggle_boundary"
    assert not result.battle_won
    assert result.decisions == ()
    assert [event["event"] for event in events] == [
        "episode_started",
        "unsupported_action_boundary",
    ]


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


def test_opening_wait_uses_the_same_action_executor_as_battle_actions(tmp_path, monkeypatch):
    capture = _capture(tmp_path)
    session = Session()
    session.tick = lambda _frames: None
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

    class Actions:
        def __init__(self):
            self.macros = []

        def execute(self, action):
            self.macros.append(action)
            return SimpleNamespace(frames=action.repeat)

    actions = Actions()

    class Policy:
        policy_id = "test-model"

        def choose_main(self, *_args):
            return BattleAction.move(1)

    from pokemon_red_completion.executor import (
        ControllerActionBudgetExhausted,
        ControllerActionLimiter,
    )

    limited = ControllerActionLimiter(actions, maximum_actions=1)
    monkeypatch.setattr(
        episode,
        "execute_bounded_battle_move_turn",
        lambda _reader, action_executor, **_kwargs: action_executor.execute(
            episode.MacroAction(episode.MacroActionKind.CONFIRM)
        ),
    )
    with pytest.raises(ControllerActionBudgetExhausted):
        episode.run_red_trainer_practice_episode(
            capture,
            session_factory=lambda: session,
            policy=Policy(),
            opening_idle_frames=4,
            action_executor=limited,
        )

    assert [macro.kind for macro in actions.macros] == [episode.MacroActionKind.WAIT]
    assert limited.attempted_actions == 1


def test_decision_guard_expires_before_policy_choice(tmp_path, monkeypatch):
    capture = _capture(tmp_path)
    session = Session()
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

    class Policy:
        policy_id = "test-model"

        def choose_main(self, *_args):
            raise AssertionError("expired decision must not reach inference")

    with pytest.raises(RuntimeError, match="deadline before choice"):
        episode.run_red_trainer_practice_episode(
            capture,
            session_factory=lambda: session,
            policy=Policy(),
            decision_guard=lambda _raw: (_ for _ in ()).throw(
                RuntimeError("deadline before choice")
            ),
        )


@pytest.mark.parametrize("mode", ("main", "switch_prompt", "forced_switch"))
def test_decision_guard_is_rechecked_after_pre_policy_logging(tmp_path, monkeypatch, mode):
    capture = _capture(tmp_path)
    session = Session()
    if mode == "forced_switch":
        session.raw = replace(session.raw, party_hp=(0, 35), active_party_hp=0)
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
    if mode == "switch_prompt":
        session.trainer_switch_prompt_visible = lambda _raw: True

    class Policy:
        policy_id = "test-model"

        def choose_main(self, *_args):
            raise AssertionError("deadline after preparation must not enter main policy")

        def choose_switch(self, *_args, **_kwargs):
            raise AssertionError("deadline after logging must not enter switch policy")

    calls = 0

    def guard(_raw):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("deadline after pre-policy work")

    with pytest.raises(RuntimeError, match="deadline after pre-policy work"):
        episode.run_red_trainer_practice_episode(
            capture,
            session_factory=lambda: session,
            policy=Policy(),
            decision_guard=guard,
        )
    assert calls == 2


def test_opening_wait_without_supplied_executor_keeps_absolute_frame_count(tmp_path, monkeypatch):
    capture = _capture(tmp_path)
    session = Session()
    ticks = []
    session.tick = ticks.append
    monkeypatch.setattr(episode, "PokemonRedStateReader", lambda loaded: loaded)
    monkeypatch.setattr(episode, "canonical_sha256", lambda _value: "b" * 64)
    snapshot = SimpleNamespace(to_dict=lambda: {"features": {"battle": {"kind": "trainer"}}})
    monkeypatch.setattr(
        episode.PokemonRedObservationEncoder,
        "from_state_reader",
        lambda _reader: SimpleNamespace(snapshot_from_raw=lambda _raw: snapshot),
    )
    monkeypatch.setattr(
        episode, "prepare_red_battle_scenario", lambda *_args, **_kwargs: _prepared()
    )

    class BoundaryReached(Exception):
        pass

    with pytest.raises(BoundaryReached):
        episode.run_red_trainer_practice_episode(
            capture,
            session_factory=lambda: session,
            policy=SimpleNamespace(policy_id="test-model"),
            opening_idle_frames=4,
            controller_timing=episode.ControllerTiming(wait_frames=3),
            decision_guard=lambda _raw: (_ for _ in ()).throw(BoundaryReached()),
        )
    assert ticks == [4]


def test_action_expiry_after_inference_prevents_dispatch(tmp_path, monkeypatch):
    capture = _capture(tmp_path)
    session = Session()
    expired = False
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

    class Actions:
        calls = 0

        def execute(self, _action):
            self.calls += 1

    actions = Actions()

    class Policy:
        policy_id = "test-model"

        def choose_main(self, *_args):
            nonlocal expired
            expired = True
            return BattleAction.move(1)

    def admit():
        if expired:
            raise RuntimeError("deadline during inference")

    from pokemon_red_completion.executor import ControllerActionLimiter

    limited = ControllerActionLimiter(actions, maximum_actions=2, admit_action=admit)
    monkeypatch.setattr(
        episode,
        "execute_bounded_battle_move_turn",
        lambda _reader, action_executor, **_kwargs: action_executor.execute(
            episode.MacroAction(episode.MacroActionKind.CONFIRM)
        ),
    )
    with pytest.raises(RuntimeError, match="deadline during inference"):
        episode.run_red_trainer_practice_episode(
            capture,
            session_factory=lambda: session,
            policy=Policy(),
            action_executor=limited,
        )

    assert limited.attempted_actions == 0
    assert actions.calls == 0


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


@pytest.mark.parametrize("living_guard", [False, True])
def test_episode_records_party_defeat_without_asking_for_impossible_switch(tmp_path, monkeypatch, living_guard):
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

    def guard(_raw):
        raise ValueError("no living member: another decision must not be attempted")
    result = episode.run_red_trainer_practice_episode(
        capture, session_factory=lambda: session, policy=Policy(),
        decision_guard=guard if living_guard else None,
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


@pytest.mark.parametrize("status", [False, True])
@pytest.mark.parametrize("context", [False, True])
@pytest.mark.parametrize("mode", ["forced_switch", "switch_prompt", "voluntary_switch"])
def test_episode_accepts_authenticated_forced_switch_as_first_boundary(
    tmp_path, monkeypatch, status, context, mode
):
    capture = _capture(tmp_path, status=status or context)
    session = Session()
    if mode == "forced_switch":
        session.raw = replace(session.raw, party_hp=(0, 35), active_party_hp=0)
    if mode == "switch_prompt":
        monkeypatch.setattr(session, "trainer_switch_prompt_visible", lambda _raw: True)
    monkeypatch.setattr(episode, "PokemonRedStateReader", lambda loaded: loaded)

    @dataclass(frozen=True)
    class Encoder:
        include_status_context: bool = False

        def snapshot_from_raw(self, _raw):
            return SimpleNamespace(
                to_dict=lambda: {"forced": True, "status": self.include_status_context}
            )

    monkeypatch.setattr(
        episode.PokemonRedObservationEncoder,
        "from_state_reader",
        lambda _reader, **_kwargs: Encoder(),
    )
    monkeypatch.setattr(
        episode, "canonical_sha256", lambda value: ("c" if value.get("status") else "b") * 64
    )
    def prepare(*_args, **kwargs):
        assert kwargs.get("allow_status_moves", False) is status or (
            "allow_status_moves" not in kwargs
        )
        return _prepared()

    monkeypatch.setattr(episode, "prepare_red_battle_scenario", prepare)

    def switch(_actions, _reader, _session, target, **_kwargs):
        assert target == 1
        session.raw = replace(session.raw, active_party_index=1, active_party_hp=35)

    monkeypatch.setattr(episode, "switch_active_battler", switch)
    monkeypatch.setattr(
        episode,
        "resolve_trainer_switch_prompt",
        lambda a, r, s, **kw: switch(a, r, s, kw["target_index"]),
    )

    class Policy:
        policy_id = "forced-unit-model"

        def choose_main(self, *_args):
            assert mode == "voluntary_switch"
            assert _args[0]["status"] is (status or context)
            return BattleAction.switch(2)

        def choose_switch(self, _observation, legal_slots, *, forced, may_decline):
            assert _observation["status"] is (status or context)
            assert forced == (mode == "forced_switch")
            assert may_decline == (mode == "switch_prompt") and legal_slots == (2,)
            return 2

    result = episode.run_red_trainer_practice_episode(
        capture,
        session_factory=lambda: session,
        policy=Policy(),
        max_decisions=1,
        allow_status_moves=status,
        include_status_context=context,
    )
    assert result.decisions[0]["kind"] == mode
    assert result.decisions[0]["party_slot"] == 2
    assert result.final_observation["status"] is (status or context)
    assert result.decisions[0]["after_observation_sha256"] == (
        "c" if status or context else "b"
    ) * 64


@pytest.mark.parametrize("context", [None, 1, "true"])
def test_status_context_requires_explicit_boolean(tmp_path, context):
    capture = _capture(tmp_path, status=True)
    with pytest.raises(episode.RedTrainerPracticeEpisodeError, match="observation opt-in"):
        episode.run_red_trainer_practice_episode(
            capture, session_factory=Session, policy=SimpleNamespace(policy_id="test"),
            include_status_context=context,
        )


def test_status_context_rejects_legacy_capture_before_opening(tmp_path):
    capture = _capture(tmp_path)
    def forbidden():
        raise AssertionError("must reject before opening")
    with pytest.raises(episode.RedTrainerPracticeEpisodeError, match="rich battle"):
        episode.run_red_trainer_practice_episode(
            capture, session_factory=forbidden, policy=SimpleNamespace(policy_id="test"),
            include_status_context=True,
        )


def test_live_runner_forwards_observation_without_status_permission(monkeypatch):
    seen = {}
    sentinel = object()
    monkeypatch.setattr(episode, "_BorrowedTrainerSession", lambda session: session)

    def run(capture, **kwargs):
        seen.update(kwargs)
        return sentinel

    monkeypatch.setattr(episode, "run_red_trainer_practice_episode", run)
    assert episode.run_live_red_trainer_practice_episode(
        object(), session=object(), policy=object(),
        include_status_context=True, allow_status_moves=False,
    ) is sentinel
    assert seen["include_status_context"] is True
    assert seen["allow_status_moves"] is False


@pytest.mark.parametrize("enabled", [False, True])
def test_live_runner_forwards_explicit_forced_struggle_to_existing_core(monkeypatch, enabled):
    seen = {}
    monkeypatch.setattr(episode, "_BorrowedTrainerSession", lambda session: session)
    monkeypatch.setattr(episode, "run_red_trainer_practice_episode",
                        lambda capture, **kwargs: seen.update(kwargs))
    episode.run_live_red_trainer_practice_episode(
        object(), session=object(), policy=object(), allow_forced_struggle=enabled
    )
    assert seen["allow_forced_struggle"] is enabled


@pytest.mark.parametrize("target_slot", (4, 5, 6))
def test_episode_preserves_one_based_late_slot_through_forced_execution(
    tmp_path, monkeypatch, target_slot
):
    capture = _capture(tmp_path)
    session = Session()
    party_hp = tuple(35 if index == target_slot - 1 else 0 for index in range(6))
    session.raw = replace(
        session.raw,
        party_count=6,
        party_hp=party_hp,
        active_party_index=0,
        active_party_hp=0,
    )
    monkeypatch.setattr(episode, "PokemonRedStateReader", lambda loaded: loaded)
    monkeypatch.setattr(
        episode.PokemonRedObservationEncoder,
        "from_state_reader",
        lambda _reader: SimpleNamespace(
            snapshot_from_raw=lambda _raw: SimpleNamespace(to_dict=lambda: {"six": True})
        ),
    )
    monkeypatch.setattr(episode, "canonical_sha256", lambda _value: "b" * 64)
    monkeypatch.setattr(
        episode,
        "prepare_red_battle_scenario",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("not an attack menu")),
    )
    executed = []

    def switch(_actions, _reader, _session, target_index, **_kwargs):
        executed.append(target_index)
        session.raw = replace(
            session.raw,
            active_party_index=target_index,
            active_party_hp=party_hp[target_index],
        )

    monkeypatch.setattr(episode, "switch_active_battler", switch)

    class Policy:
        policy_id = "late-forced-unit-model"

        def choose_main(self, *_args):
            raise AssertionError("forced switch must come first")

        def choose_switch(self, _observation, legal_slots, *, forced, may_decline):
            assert forced and not may_decline and legal_slots == (target_slot,)
            return target_slot

    result = episode.run_red_trainer_practice_episode(
        capture, session_factory=lambda: session, policy=Policy(), max_decisions=1
    )
    assert executed == [target_slot - 1]
    assert result.decisions[0]["party_slot"] == target_slot
    assert result.decisions[0]["legal_party_slots"] == [target_slot]


@pytest.mark.parametrize("partition", [ScenarioPartition.TRAIN, ScenarioPartition.DEVELOPMENT])
def test_opt_in_forced_struggle_counts_turn_without_querying_model(tmp_path, monkeypatch, partition):
    from pokemon_red_completion.red_forced_struggle import ForcedStruggleExecution

    capture = _capture(tmp_path, partition=partition)
    session = Session()
    session.raw = replace(session.raw, party_hp=(40, 0), active_party_pp=(0, 0, 0, 0))
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

    def execute(reader, actions, **kwargs):
        before = reader.raw
        reader.raw = replace(before, active_party_hp=0, party_hp=(0, 0))
        reader.frame_count += 122
        return ForcedStruggleExecution(before, reader.raw, 2, 122)

    monkeypatch.setattr(episode, "execute_forced_struggle_turn", execute)

    class NoPolicy:
        policy_id = "no-model-query"

        def choose_main(self, *a):
            raise AssertionError("forced mechanic is not learned choice")

        def choose_switch(self, *a, **k):
            raise AssertionError("no reserves")

    events = []
    result = episode.run_red_trainer_practice_episode(
        capture,
        session_factory=lambda: session,
        policy=NoPolicy(),
        event_sink=events.append,
        allow_forced_struggle=True,
    )
    document = result.public_dict()
    assert result.stop_reason == "party_defeated"
    assert document["player_turn_count"] == document["action_counts"]["forced_struggle"] == 1
    assert document["action_counts"]["attack"] == document["policy_elapsed_ns"] == 0
    assert document["metrics"]["party_faints"] == 1
    assert events[0]["allow_forced_struggle"] is True
    choice = next(e for e in events if e["event"] == "choice_recorded")
    assert choice["authority"] == "forced_mechanic"


@pytest.mark.parametrize("option", [True, 1, "yes"])
def test_struggle_cannot_be_enabled_for_wild_or_nonboolean_opt_in(tmp_path, option):
    capture = _capture(tmp_path, wild=True)
    with pytest.raises(episode.RedTrainerPracticeEpisodeError, match="Struggle"):
        episode.run_red_trainer_practice_episode(
            capture,
            session_factory=lambda: None,
            policy=None,
            wild_training=True,
            allow_forced_struggle=option,
        )
