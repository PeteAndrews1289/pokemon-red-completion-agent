from __future__ import annotations

from dataclasses import replace

import pytest

from pokemon_red_completion.observation import RawGameState
from pokemon_red_completion.red_repeatable_battle_scenario_source import (
    adapt_repeatable_red_battle_source,
    red_party_menu_semantic_sha256,
)
from pokemon_red_completion.repeatable_battle_scenario_factory import (
    RepeatableBattleScenarioFactoryError,
    RepeatableBattleSourceKind,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition


def _raw(*, battle_state: int = 0) -> RawGameState:
    return RawGameState(
        game_started=True,
        map_id=171,
        player_x=3,
        player_y=3,
        party_count=3,
        battle_state=battle_state,
        party_species_ids=(28, 64, 59),
        party_levels=(60, 55, 55),
        party_hp=(189, 139, 37),
        party_max_hp=(189, 139, 37),
        party_status=(0, 0, 0),
        party_moves=((56, 70, 58, 57), (163, 28, 15, 19), (10, 45, 91, 0)),
        party_pp=((5, 15, 10, 15), (20, 15, 30, 15), (35, 40, 10, 0)),
        active_party_index=0 if battle_state else None,
    )


def _adapt(
    raw: RawGameState,
    *,
    kind: RepeatableBattleSourceKind = RepeatableBattleSourceKind.FIELD,
):
    return adapt_repeatable_red_battle_source(
        raw,
        source_id="red-source-a",
        source_lineage_id="clean-power-lineage-a",
        partition=ScenarioPartition.TRAIN,
        state_sha256="a" * 64,
        source_commit="b" * 40,
        source_kind=kind,
        active_party_index=0 if kind is RepeatableBattleSourceKind.TRAINER_BATTLE else None,
        reachable_venue_ids=(
            ()
            if kind is RepeatableBattleSourceKind.TRAINER_BATTLE
            else ("route_11", "digletts_cave", "pokemon_mansion_1f")
        ),
    )


def test_field_adapter_exposes_six_identity_free_menu_and_venue_facts() -> None:
    observation = _adapt(_raw())

    assert observation.source_kind is RepeatableBattleSourceKind.FIELD
    assert observation.active_party_index is None
    assert observation.reachable_venue_ids == (
        "digletts_cave",
        "pokemon_mansion_1f",
        "route_11",
    )
    assert [item.party_index for item in observation.party_options] == [0, 1, 2]
    assert len({item.menu_semantic_sha256 for item in observation.party_options}) == 3
    assert all(item.supported_move_count >= 2 for item in observation.party_options)
    encoded = str(observation.private_dict())
    assert "Pokemon Red" not in encoded
    assert "/" not in encoded


def test_trainer_adapter_retains_kind_and_active_party_without_a_venue() -> None:
    observation = _adapt(
        _raw(battle_state=2),
        kind=RepeatableBattleSourceKind.TRAINER_BATTLE,
    )

    assert observation.source_kind is RepeatableBattleSourceKind.TRAINER_BATTLE
    assert observation.active_party_index == 0
    assert observation.reachable_venue_ids == ()


def test_menu_identity_is_order_neutral_but_sensitive_to_pp() -> None:
    first = red_party_menu_semantic_sha256(
        species_id=28,
        move_ids=(56, 70, 58, 57),
        current_pp=(5, 15, 10, 15),
    )
    reordered = red_party_menu_semantic_sha256(
        species_id=28,
        move_ids=(57, 56, 70, 58),
        current_pp=(15, 5, 15, 10),
    )
    depleted = red_party_menu_semantic_sha256(
        species_id=28,
        move_ids=(56, 70, 58, 57),
        current_pp=(4, 15, 10, 15),
    )

    assert first == reordered
    assert first != depleted


def test_fainted_and_single_attack_members_do_not_become_options() -> None:
    raw = replace(
        _raw(),
        party_hp=(189, 0, 37),
        party_moves=((56, 70, 58, 57), (163, 28, 15, 19), (10, 0, 0, 0)),
        party_pp=((5, 15, 10, 15), (20, 15, 30, 15), (35, 0, 0, 0)),
    )

    observation = _adapt(raw)

    assert [item.party_index for item in observation.party_options] == [0]


def test_adapter_rejects_kind_or_party_array_drift() -> None:
    with pytest.raises(RepeatableBattleScenarioFactoryError, match="source kind differs"):
        _adapt(_raw(battle_state=2))

    with pytest.raises(RepeatableBattleScenarioFactoryError, match="party arrays"):
        _adapt(replace(_raw(), party_pp=((1, 2, 3, 4),)))


def test_adapter_rejects_party_hp_above_maximum() -> None:
    with pytest.raises(RepeatableBattleScenarioFactoryError, match="exceeds"):
        _adapt(replace(_raw(), party_hp=(190, 139, 37)))


def test_adapter_rejects_short_member_move_array() -> None:
    with pytest.raises(RepeatableBattleScenarioFactoryError, match="four slots"):
        _adapt(
            replace(
                _raw(),
                party_moves=((56, 70, 58), (163, 28, 15, 19), (10, 45, 91, 0)),
            )
        )
