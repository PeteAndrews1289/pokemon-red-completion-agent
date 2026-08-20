from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass

from pokemon_red_completion.battle_outcome_learning import BattleTurnOutcome
from pokemon_red_completion.battle_runtime import BattleTurnExecution
from pokemon_red_completion.battle_scenario_capture import (
    build_battle_scenario_capture_payload,
    open_battle_scenario_capture,
)
from pokemon_red_completion.battle_semantics import (
    FEATURE_NAMES,
    FEATURE_SCHEMA_ID,
    BattleFeatureBatch,
)
from pokemon_red_completion.observation import RawGameState
from pokemon_red_completion.red_battle_outcome_runtime import (
    collect_red_battle_outcome_example,
)
from pokemon_red_completion.red_battle_scenario import PreparedRedBattleScenario
from pokemon_red_completion.scenario_lab import ScenarioPartition


def _prepared() -> PreparedRedBattleScenario:
    vector = tuple(0.0 for _ in FEATURE_NAMES)
    return PreparedRedBattleScenario(
        initial_observation_sha256="b" * 64,
        features=BattleFeatureBatch(
            feature_names=FEATURE_NAMES,
            candidate_vectors=(vector, vector, vector),
            legal_mask=(True, False, True),
            current_pp=(10.0, 0.0, 5.0),
            slot_indices=(0, 1, 2),
            schema_id=FEATURE_SCHEMA_ID,
        ),
    )


def _raw() -> RawGameState:
    return RawGameState(True, 165, 5, 20, 1, 1)


@dataclass
class Session(AbstractContextManager["Session"]):
    loaded: list[bytes]

    def __enter__(self) -> Session:
        return self

    def __exit__(self, *args: object) -> None:
        del args

    def load_state_bytes(self, payload: bytes) -> None:
        self.loaded.append(payload)

    def press(self, button: str) -> None:
        del button

    def release(self, button: str) -> None:
        del button

    def tick(self, frames: int) -> None:
        del frames

    def read_u8(self, address: int) -> int:
        del address
        return 0


def test_counterfactual_collection_resets_exact_state_for_each_supported_move(
    tmp_path,
    monkeypatch,
) -> None:
    state = b"authenticated private state"
    state_path = tmp_path / "battle.state"
    manifest_path = tmp_path / "battle.state.json"
    state_path.write_bytes(state)
    manifest_path.write_bytes(
        build_battle_scenario_capture_payload(
            capture_id="battle-001",
            root_lineage_id="train-root-a",
            partition=ScenarioPartition.TRAIN,
            state_bytes=state,
            initial_observation_sha256="b" * 64,
            source_commit="c" * 40,
            expected_map=165,
            expected_battle_state=1,
        )
    )
    capture = open_battle_scenario_capture(state_path, manifest_path)
    loaded: list[bytes] = []
    selected_slots: list[int] = []
    retained: list[tuple[int, BattleTurnOutcome]] = []

    monkeypatch.setattr(
        "pokemon_red_completion.red_battle_outcome_runtime._prepare_loaded_boundary",
        lambda capture, reader: _prepared(),
    )

    def execute(reader, executor, **kwargs):  # type: ignore[no-untyped-def]
        del reader, executor
        selected_slots.append(kwargs["selected_slot"])
        return BattleTurnExecution(
            _raw(),
            _raw(),
            kwargs["selected_slot"],
            1,
            3_000,
            True,
            2_048,
        )

    monkeypatch.setattr(
        "pokemon_red_completion.red_battle_outcome_runtime."
        "execute_bounded_battle_move_turn",
        execute,
    )

    def outcome(execution: BattleTurnExecution) -> BattleTurnOutcome:
        return BattleTurnOutcome(
            move_executed=True,
            opponent_damage_fraction=0.2 * execution.selected_slot,
            player_damage_fraction=0.0,
            opponent_fainted=False,
            player_fainted=False,
            battle_exited=False,
            actions_executed=1,
            frames_executed=3_000,
            pre_attack_frames=2_048,
        )

    monkeypatch.setattr(
        "pokemon_red_completion.red_battle_outcome_runtime."
        "project_red_battle_turn_outcome",
        outcome,
    )

    collection = collect_red_battle_outcome_example(
        capture,
        session_factory=lambda: Session(loaded),
        outcome_sink=lambda candidate_index, result: retained.append(
            (candidate_index, result)
        ),
    )

    assert loaded == [state, state, state]
    assert selected_slots == [1, 3]
    assert [candidate_index for candidate_index, _ in retained] == [0, 2]
    assert tuple(result for _, result in retained) == (
        collection.outcomes[0],
        collection.outcomes[2],
    )
    assert collection.outcomes[1] is None
    assert collection.example.best_candidate_indices == (2,)
    assert collection.public_dict()["teacher_queries"] == 0
    assert collection.public_dict()["full_game_replays"] == 0
    assert collection.public_dict()["counterfactual_pre_attack_frames"] == 2_048
