from __future__ import annotations

from dataclasses import replace

import pytest

from pokemon_red_completion.observation import (
    RawGameState,
    RedBoxCollectionState,
    RedCurrentBoxState,
    RedPokedexState,
)
from pokemon_red_completion.red_party_development_pp_materialization import (
    RED_PP_MATERIALIZATION_BOUNDS,
    RED_PP_MATERIALIZATION_EXECUTION_CONTRACT,
    RedPartyDevelopmentPpMaterializationError,
    red_pp_protected_state_sha256,
)


def _raw() -> RawGameState:
    return RawGameState(
        game_started=True,
        map_id=22,
        player_x=10,
        player_y=10,
        party_count=6,
        battle_state=0,
        badge_bits=0xFF,
        bag_item_ids=(1, 2),
        bag_items=((1, 4), (2, 1)),
        event_flags=b"\x01\x02",
        party_species_ids=(28, 59, 64, 104, 132, 43),
        party_levels=(50, 30, 30, 30, 30, 30),
        party_hp=(156, 90, 91, 92, 93, 94),
        party_max_hp=(156, 90, 91, 92, 93, 94),
        party_status=(0, 0, 0, 0, 0, 0),
        party_moves=(
            (44, 39, 58, 57),
            (1, 2, 3, 4),
            (5, 6, 7, 8),
            (9, 10, 11, 12),
            (13, 14, 15, 16),
            (17, 18, 19, 20),
        ),
        party_pp=(
            (25, 30, 10, 15),
            (10, 10, 10, 10),
            (10, 10, 10, 10),
            (10, 10, 10, 10),
            (10, 10, 10, 10),
            (10, 10, 10, 10),
        ),
        player_money=123_456,
    )


def _pokedex() -> RedPokedexState:
    return RedPokedexState(
        owned_species=frozenset({1, 9}),
        seen_species=frozenset({1, 9, 21, 23, 96}),
    )


def _boxes() -> RedBoxCollectionState:
    return RedBoxCollectionState(
        boxes=tuple(
            RedCurrentBoxState(
                index,
                (28,) if index == 0 else (),
                (50,) if index == 0 else (),
            )
            for index in range(12)
        ),
        current_box_index=0,
        storage_initialized=True,
    )


def _digest(
    raw: RawGameState,
    *,
    pokedex: RedPokedexState | None = None,
    boxes: RedBoxCollectionState | None = None,
    experience: tuple[int, ...] = (121_062, 8_858, 10_666, 33_750, 15_625, 27_000),
) -> str:
    return red_pp_protected_state_sha256(
        raw,
        pokedex or _pokedex(),
        boxes or _boxes(),
        experience,
        target_party_slot=1,
    )


def test_pp_protected_digest_allows_only_target_battle_progress() -> None:
    raw = _raw()
    changed_pp = ((20, 30, 10, 15), *(raw.party_pp or ())[1:])
    progressed = replace(
        raw,
        map_id=171,
        player_x=3,
        player_y=7,
        party_levels=(51, *(raw.party_levels or ())[1:]),
        party_hp=(140, *(raw.party_hp or ())[1:]),
        party_max_hp=(159, *(raw.party_max_hp or ())[1:]),
        party_pp=changed_pp,
    )
    progressed_experience = (125_200, 8_858, 10_666, 33_750, 15_625, 27_000)

    assert _digest(progressed, experience=progressed_experience) == _digest(raw)


@pytest.mark.parametrize(
    "mutation",
    (
        "badges",
        "bag",
        "bag_ids",
        "money",
        "events",
        "target_species",
        "target_status",
        "target_moves",
        "non_target_species",
        "non_target_level",
        "non_target_hp",
        "non_target_max_hp",
        "non_target_status",
        "non_target_moves",
        "non_target_pp",
        "non_target_experience",
        "pokedex",
        "pokedex_owned",
        "boxes",
        "current_box",
        "storage_initialized",
    ),
)
def test_pp_protected_digest_distinguishes_every_forbidden_change(
    mutation: str,
) -> None:
    raw = _raw()
    pokedex = _pokedex()
    boxes = _boxes()
    experience = (121_062, 8_858, 10_666, 33_750, 15_625, 27_000)
    expected = _digest(raw, pokedex=pokedex, boxes=boxes, experience=experience)

    if mutation == "badges":
        raw = replace(raw, badge_bits=0xFE)
    elif mutation == "bag":
        raw = replace(raw, bag_items=((1, 3), (2, 1)))
    elif mutation == "bag_ids":
        raw = replace(raw, bag_item_ids=(1, 3))
    elif mutation == "money":
        raw = replace(raw, player_money=123_457)
    elif mutation == "events":
        raw = replace(raw, event_flags=b"\x01\x03")
    elif mutation == "target_species":
        raw = replace(raw, party_species_ids=(29, *(raw.party_species_ids or ())[1:]))
    elif mutation == "target_status":
        raw = replace(raw, party_status=(8, *(raw.party_status or ())[1:]))
    elif mutation == "target_moves":
        raw = replace(
            raw,
            party_moves=((45, 39, 58, 57), *(raw.party_moves or ())[1:]),
        )
    elif mutation == "non_target_species":
        raw = replace(
            raw,
            party_species_ids=(
                (raw.party_species_ids or ())[0],
                60,
                *(raw.party_species_ids or ())[2:],
            ),
        )
    elif mutation == "non_target_level":
        raw = replace(
            raw,
            party_levels=((raw.party_levels or ())[0], 31, *(raw.party_levels or ())[2:]),
        )
    elif mutation == "non_target_hp":
        raw = replace(raw, party_hp=((raw.party_hp or ())[0], 89, *(raw.party_hp or ())[2:]))
    elif mutation == "non_target_max_hp":
        raw = replace(
            raw,
            party_max_hp=((raw.party_max_hp or ())[0], 91, *(raw.party_max_hp or ())[2:]),
        )
    elif mutation == "non_target_status":
        raw = replace(
            raw,
            party_status=((raw.party_status or ())[0], 8, *(raw.party_status or ())[2:]),
        )
    elif mutation == "non_target_moves":
        rows = raw.party_moves or ()
        raw = replace(raw, party_moves=(rows[0], (2, 2, 3, 4), *rows[2:]))
    elif mutation == "non_target_pp":
        rows = raw.party_pp or ()
        raw = replace(raw, party_pp=(rows[0], (9, 10, 10, 10), *rows[2:]))
    elif mutation == "non_target_experience":
        experience = (experience[0], experience[1] + 1, *experience[2:])
    elif mutation == "pokedex":
        pokedex = RedPokedexState(
            owned_species=pokedex.owned_species,
            seen_species=pokedex.seen_species | {25},
        )
    elif mutation == "pokedex_owned":
        pokedex = RedPokedexState(
            owned_species=pokedex.owned_species | {21},
            seen_species=pokedex.seen_species,
        )
    elif mutation == "boxes":
        box_rows = list(boxes.boxes)
        box_rows[0] = RedCurrentBoxState(0, (28, 59), (50, 20))
        boxes = replace(boxes, boxes=tuple(box_rows))
    elif mutation == "current_box":
        boxes = replace(boxes, current_box_index=1)
    elif mutation == "storage_initialized":
        boxes = replace(boxes, storage_initialized=False)
    else:  # pragma: no cover - parametrization owns this branch
        raise AssertionError(mutation)

    assert (
        _digest(
            raw,
            pokedex=pokedex,
            boxes=boxes,
            experience=experience,
        )
        != expected
    )


def test_pp_protected_digest_requires_complete_experience_evidence() -> None:
    with pytest.raises(
        RedPartyDevelopmentPpMaterializationError,
        match="party vectors disagree",
    ):
        _digest(_raw(), experience=(121_062,))


def test_pp_materialization_bounds_and_source_requirements_are_frozen() -> None:
    assert RED_PP_MATERIALIZATION_BOUNDS.maximum_completed_battles == 27
    source_requirements = RED_PP_MATERIALIZATION_EXECUTION_CONTRACT["source_requirements"]
    assert isinstance(source_requirements, list)
    assert "experience_sharing_item_absent" in source_requirements
    assert RED_PP_MATERIALIZATION_EXECUTION_CONTRACT["retry_after_any_controller_input"] is False
