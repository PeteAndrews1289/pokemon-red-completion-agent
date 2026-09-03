from __future__ import annotations

import json
from dataclasses import replace

import pytest

from pokemon_red_completion.repeatable_battle_scenario_factory import (
    RepeatableBattlePartyOption,
    RepeatableBattleScenarioCoverage,
    RepeatableBattleScenarioFactoryError,
    RepeatableBattleScenarioKind,
    RepeatableBattleSourceKind,
    RepeatableBattleSourceObservation,
    build_repeatable_battle_scenario_plan,
    parse_repeatable_battle_scenario_plan,
    require_repeatable_battle_scenario_coverage,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition


def _option(index: int, digest: str) -> RepeatableBattlePartyOption:
    return RepeatableBattlePartyOption(index, digest * 64, 3, 1.0)


def _source(
    ordinal: int,
    partition: ScenarioPartition,
    *,
    kind: RepeatableBattleSourceKind = RepeatableBattleSourceKind.FIELD,
) -> RepeatableBattleSourceObservation:
    stem = f"{partition.value}-{ordinal}"
    return RepeatableBattleSourceObservation(
        source_id=f"source-{stem}",
        source_lineage_id=f"lineage-{stem}",
        partition=partition,
        state_sha256=f"{ordinal + (0 if partition is ScenarioPartition.TRAIN else 8):x}" * 64,
        source_commit="a" * 40,
        expected_map=171,
        source_kind=kind,
        active_party_index=0 if kind is RepeatableBattleSourceKind.TRAINER_BATTLE else None,
        reachable_venue_ids=(
            ()
            if kind is RepeatableBattleSourceKind.TRAINER_BATTLE
            else ("digletts_cave", "pokemon_mansion_1f", "route_11")
        ),
        party_options=(
            _option(0, "a" if ordinal % 2 else "b"),
            _option(1, "c" if ordinal % 2 else "d"),
            _option(2, "e" if ordinal % 2 else "f"),
        ),
    )


def _sources() -> tuple[RepeatableBattleSourceObservation, ...]:
    return (
        _source(1, ScenarioPartition.TRAIN),
        _source(2, ScenarioPartition.TRAIN),
        _source(3, ScenarioPartition.TRAIN, kind=RepeatableBattleSourceKind.TRAINER_BATTLE),
        _source(4, ScenarioPartition.DEVELOPMENT),
        _source(5, ScenarioPartition.DEVELOPMENT),
        _source(
            6,
            ScenarioPartition.DEVELOPMENT,
            kind=RepeatableBattleSourceKind.TRAINER_BATTLE,
        ),
    )


def test_plan_is_deterministic_balanced_and_partition_safe() -> None:
    first = build_repeatable_battle_scenario_plan(
        _sources(), seed=1289, training_scenarios=18, development_scenarios=12
    )
    second = build_repeatable_battle_scenario_plan(
        _sources(), seed=1289, training_scenarios=18, development_scenarios=12
    )

    assert first == second
    assert first.sha256 == second.sha256
    assert len(first.assignments) == 30
    train = first.coverage(ScenarioPartition.TRAIN)
    development = first.coverage(ScenarioPartition.DEVELOPMENT)
    assert train.source_lineages == 3
    assert development.source_lineages == 3
    assert train.party_menus >= 4
    assert development.party_menus >= 4
    assert train.venues == development.venues == 3
    assert train.battle_kinds == development.battle_kinds == 2
    assert train.semantic_setups == train.scenarios
    assert development.semantic_setups == development.scenarios
    assert not (
        {item.source_lineage_id for item in first.partition_assignments(ScenarioPartition.TRAIN)}
        & {
            item.source_lineage_id
            for item in first.partition_assignments(ScenarioPartition.DEVELOPMENT)
        }
    )
    assert first.public_dict()["controller_actions"] == 0
    assert first.public_dict()["outcomes"] == 0


def test_timing_variants_remain_one_upstream_lineage() -> None:
    plan = build_repeatable_battle_scenario_plan(
        _sources(), seed=9, training_scenarios=24, development_scenarios=8
    )
    rows = plan.partition_assignments(ScenarioPartition.TRAIN)
    same_source = [item for item in rows if item.source_id == "source-train-1"]

    assert len(same_source) > 1
    assert len({item.pre_encounter_wait_frames for item in same_source}) > 1
    assert {item.source_lineage_id for item in same_source} == {"lineage-train-1"}
    assert len({item.semantic_setup_sha256 for item in same_source}) == len(same_source)


def test_trainer_source_creates_trainer_scenarios_without_wild_venue() -> None:
    plan = build_repeatable_battle_scenario_plan(
        _sources(), seed=4, training_scenarios=30, development_scenarios=6
    )
    trainer = next(
        item
        for item in plan.partition_assignments(ScenarioPartition.TRAIN)
        if item.scenario_kind is RepeatableBattleScenarioKind.TRAINER
    )

    assert trainer.venue_id is None
    assert trainer.source_id == "source-train-3"


def test_plan_rejects_a_lineage_crossing_partitions() -> None:
    sources = list(_sources())
    sources[-1] = replace(sources[-1], source_lineage_id="lineage-train-1")

    with pytest.raises(RepeatableBattleScenarioFactoryError, match="lineage crosses"):
        build_repeatable_battle_scenario_plan(
            tuple(sources), seed=1, training_scenarios=6, development_scenarios=6
        )


def test_plan_rejects_requested_capacity_larger_than_supply() -> None:
    with pytest.raises(RepeatableBattleScenarioFactoryError, match="capacity"):
        build_repeatable_battle_scenario_plan(
            _sources(),
            seed=1,
            training_scenarios=1_000,
            development_scenarios=6,
            wait_frame_offsets=(0,),
        )


def test_coverage_gate_names_the_short_partition_dimensions() -> None:
    plan = build_repeatable_battle_scenario_plan(
        _sources(), seed=1289, training_scenarios=12, development_scenarios=8
    )
    minimum = RepeatableBattleScenarioCoverage(8, 2, 2, 4, 8, 2, 2)
    require_repeatable_battle_scenario_coverage(
        plan,
        train_minimum=minimum,
        development_minimum=minimum,
    )

    impossible = replace(minimum, source_lineages=4, party_menus=20)
    with pytest.raises(
        RepeatableBattleScenarioFactoryError,
        match="development.*source_lineages, party_menus",
    ):
        require_repeatable_battle_scenario_coverage(
            plan,
            train_minimum=minimum,
            development_minimum=impossible,
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("hp_ratio", float("nan"), "HP ratio"),
        ("supported_move_count", True, "two through four"),
        ("party_index", 6, "party index"),
    ),
)
def test_party_options_reject_permissive_or_out_of_range_values(
    field: str, value: object, message: str
) -> None:
    with pytest.raises(RepeatableBattleScenarioFactoryError, match=message):
        replace(_option(0, "a"), **{field: value})


def test_private_plan_round_trip_is_canonical_and_digest_bound() -> None:
    plan = build_repeatable_battle_scenario_plan(
        _sources(), seed=1289, training_scenarios=12, development_scenarios=8
    )
    payload = _payload(plan.private_dict())

    assert parse_repeatable_battle_scenario_plan(payload) == plan

    changed = plan.private_dict()
    changed["assignments"][0]["semantic_setup_sha256"] = "0" * 64  # type: ignore[index]
    with pytest.raises(RepeatableBattleScenarioFactoryError, match="digest differs"):
        parse_repeatable_battle_scenario_plan(_payload(changed))


def test_private_plan_parser_rejects_noncanonical_or_extra_fields() -> None:
    plan = build_repeatable_battle_scenario_plan(
        _sources(), seed=1289, training_scenarios=12, development_scenarios=8
    )
    pretty = (json.dumps(plan.private_dict(), indent=2) + "\n").encode("ascii")
    with pytest.raises(RepeatableBattleScenarioFactoryError, match="not canonical"):
        parse_repeatable_battle_scenario_plan(pretty)

    extra = plan.private_dict()
    extra["unexpected"] = True
    with pytest.raises(RepeatableBattleScenarioFactoryError, match="fields"):
        parse_repeatable_battle_scenario_plan(_payload(extra))


def _payload(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode("ascii")
