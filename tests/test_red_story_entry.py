"""Independent, ROM-free probes of the real legacy story admission boundary."""

from dataclasses import replace
from types import SimpleNamespace

import pytest

from pokemon_red_completion.domain import GameMode, GameState
from pokemon_red_completion.lorelei import (
    LoreleiChapterError,
    lorelei_input_boundary_failures,
    run_lorelei_chapter,
)
from pokemon_red_completion.observation import RawGameState
from pokemon_red_completion.red_objective_skills import DefeatLoreleiObjectiveSkill


def _qualified_raw() -> RawGameState:
    # Literal observations, not values copied from the predicate's constants.
    return RawGameState(
        game_started=True,
        map_id=0xAE,
        player_x=2,
        player_y=5,
        party_count=6,
        battle_state=0,
        party_species_ids=(0x1C, 0x40, 0x76, 0x84, 0x68, 0x2B),
        first_party_moves=(0x42, 0x46, 0x3A, 0x39),
        bag_items=((0x10, 7), (0x34, 6), (0x12, 11), (0x2E, 3), (0x44, 8)),
        event_flags=bytes(320),
    )


def _semantic() -> GameState:
    return GameState(
        GameMode.OVERWORLD,
        frozenset({"story:victory_road_cleared"}),
        "indigo_plateau_lobby",
    )


class _NoInput:
    frame_count = 0

    def execute(self, *args, **kwargs):
        pytest.fail("an unqualified story attempt sent controller input")


def test_legacy_contract_and_real_skill_accept_observed_boundary() -> None:
    raw = _qualified_raw()
    assert lorelei_input_boundary_failures(raw) == ()
    skill = DefeatLoreleiObjectiveSkill(
        _NoInput(),
        SimpleNamespace(read=lambda: raw),
        _NoInput(),  # type: ignore[arg-type]
    )
    assert skill.availability(_semantic()).executable


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("map_id", 36, "legacy_entry_map"),
        ("player_x", 3, "legacy_entry_position"),
        ("player_y", 6, "legacy_entry_position"),
        ("battle_state", 2, "overworld"),
        ("battle_state", None, "overworld"),
        ("party_species_ids", (141, 104, 28, 118, 132, 48), "legacy_party_core"),
        ("first_party_moves", (49, 113, 120, 129), "legacy_lead_moves"),
        ("bag_items", None, "inventory_unobserved"),
        ("event_flags", None, "story_event_unobserved"),
        ("event_flags", bytes(284), "story_event_unobserved"),
        ("event_flags", bytes(284) + bytes([2]) + bytes(35), "already_completed"),
    ],
)
def test_each_mismatch_blocks_availability_and_execution_before_input(field, value, reason):
    raw = replace(_qualified_raw(), **{field: value})
    reader = SimpleNamespace(read=lambda: raw)
    skill = DefeatLoreleiObjectiveSkill(_NoInput(), reader, _NoInput())  # type: ignore[arg-type]
    admission = skill.availability(_semantic())
    assert not admission.executable
    assert reason in admission.reason
    with pytest.raises(LoreleiChapterError, match=reason):
        run_lorelei_chapter(_NoInput(), reader, _NoInput())  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("item", "reason"),
    [
        (0x10, "legacy_full_restores"),
        (0x34, "legacy_full_heals"),
        (0x12, "legacy_hyper_potions"),
        (0x2E, "legacy_x_accuracy"),
        (0x44, "legacy_x_special"),
    ],
)
@pytest.mark.parametrize("delta", [-1, 1])
def test_exact_stock_is_a_legacy_restriction_not_a_minimum(item, reason, delta):
    raw = _qualified_raw()
    raw = replace(
        raw,
        bag_items=tuple((i, count + delta if i == item else count) for i, count in raw.bag_items),
    )
    assert lorelei_input_boundary_failures(raw) == (reason,)


def test_ambiguous_inventory_fails_closed():
    raw = _qualified_raw()
    assert "inventory_ambiguous" in lorelei_input_boundary_failures(
        replace(raw, bag_items=raw.bag_items + ((0x10, 7),))
    )


def test_stale_offer_is_rechecked_by_executor():
    raw = _qualified_raw()
    reader = SimpleNamespace(read=lambda: raw)
    skill = DefeatLoreleiObjectiveSkill(_NoInput(), reader, _NoInput())  # type: ignore[arg-type]
    assert skill.availability(_semantic()).executable
    raw = replace(raw, player_x=9)
    with pytest.raises(LoreleiChapterError, match="legacy_entry_position"):
        skill.execute()


def test_semantically_illegal_story_does_not_read_or_offer():
    skill = DefeatLoreleiObjectiveSkill(_NoInput(), object(), _NoInput())  # type: ignore[arg-type]
    for state in (
        replace(_semantic(), mode=GameMode.BATTLE),
        replace(_semantic(), facts=frozenset()),
        _semantic().with_facts("league:lorelei_defeated"),
    ):
        assert not skill.availability(state).executable


def test_retained_collection_party_is_not_legacy_lorelei_ready_even_after_travel():
    raw = replace(
        _qualified_raw(),
        party_species_ids=(141, 104, 28, 118, 132, 48),
        first_party_moves=(113, 103, 49, 120),
        bag_items=((16, 4), (52, 6), (46, 3), (68, 8)),
    )
    assert lorelei_input_boundary_failures(raw) == (
        "legacy_party_core",
        "legacy_lead_moves",
        "legacy_full_restores",
        "legacy_hyper_potions",
    )
