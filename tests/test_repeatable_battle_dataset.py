from __future__ import annotations

from pokemon_red_completion.battle_outcome_learning import (
    BattleOutcomeExample,
    BattleTurnOutcome,
)
from pokemon_red_completion.battle_semantics import FEATURE_NAMES, BattleFeatureBatch
from pokemon_red_completion.repeatable_battle_dataset import (
    parse_repeatable_battle_outcome_record,
    repeatable_battle_outcome_record,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition


def _example() -> BattleOutcomeExample:
    rows = (
        tuple(0.0 for _ in FEATURE_NAMES),
        tuple(1.0 for _ in FEATURE_NAMES),
    )
    return BattleOutcomeExample(
        root_lineage_id="repeatable-root-01",
        initial_state_sha256="1" * 64,
        partition=ScenarioPartition.TRAIN,
        features=BattleFeatureBatch(
            feature_names=FEATURE_NAMES,
            candidate_vectors=rows,
            legal_mask=(True, True),
            current_pp=(10.0, 10.0),
            slot_indices=(0, 1),
        ),
        outcomes=(
            BattleTurnOutcome(True, 0.5, 0.0, False, False, False, 1, 3, 1),
            BattleTurnOutcome(True, 1.0, 0.0, True, False, False, 1, 3, 1),
        ),
    )


def test_repeatable_battle_record_round_trips() -> None:
    example = _example()
    record = repeatable_battle_outcome_record(
        example,
        capture_id="capture-01",
        manifest_sha256="2" * 64,
    )

    restored = parse_repeatable_battle_outcome_record(record)

    assert restored == example
    assert record["private_path_fields"] == 0
    assert record["sealed_evidence"] is False


def test_repeatable_battle_record_rejects_changed_winner() -> None:
    record = repeatable_battle_outcome_record(
        _example(),
        capture_id="capture-01",
        manifest_sha256="2" * 64,
    )
    record["best_candidate_indices"] = [0]

    try:
        parse_repeatable_battle_outcome_record(record)
    except ValueError as error:
        assert "best candidates" in str(error)
    else:  # pragma: no cover - assertion path
        raise AssertionError("changed outcome summary was accepted")
