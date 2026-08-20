"""Measured encounter bands, and the ways a measurement can lie."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pokemon_red_completion.encounters import (
    MINIMUM_TRUSTED_SAMPLES,
    TRAINER_BATTLE_STATE,
    WILD_BATTLE_STATE,
    EncounterBand,
    EncounterLogError,
    encounter_log_path,
    grinding_areas,
    is_wild_encounter,
    load_measured_bands,
    read_encounter_log,
    summarize_encounters,
)
from pokemon_red_completion.observation import MapId, RawGameState
from pokemon_red_completion.party import (
    MoveObservation,
    PartyMemberObservation,
    StatusCondition,
)
from pokemon_red_completion.red_team_training import MEASURED_TRAINING_VENUES
from pokemon_red_completion.team_training import (
    BalancedTeamPolicy,
    choose_grinding_area,
    is_matchup_acceptable,
)

MANSION = 0xA5
DIGLETTS_CAVE = 0xAE


def row(**changes: object) -> dict[str, object]:
    entry: dict[str, object] = {
        "map_id": MANSION,
        "enemy_species": 0x21,
        "enemy_level": 30,
        "battle_state": WILD_BATTLE_STATE,
    }
    entry.update(changes)
    return entry


def raw(**changes: object) -> RawGameState:
    values: dict[str, object] = {
        "game_started": True,
        "map_id": MANSION,
        "player_x": 1,
        "player_y": 1,
        "party_count": 6,
        "battle_state": WILD_BATTLE_STATE,
        "enemy_species_id": 0x21,
        "enemy_level": 30,
    }
    values.update(changes)
    return RawGameState(**values)  # type: ignore[arg-type]


def trainee(level: int) -> PartyMemberObservation:
    """A healthy trainee with a usable move.

    The move matters: a member with no power points reads as unsafe, and an
    unsafe member is refused every matchup regardless of level. A fixture
    without one makes venue tests pass by never reaching the comparison.
    """

    return PartyMemberObservation(
        slot=1,
        species_id=0x3B,
        level=level,
        hp=80,
        max_hp=80,
        status=StatusCondition.HEALTHY,
        moves=(MoveObservation(move_id=0x21, current_pp=30),),
        experience=0,
    )


# -- what counts as a measurement -------------------------------------------


def test_trainer_battles_are_not_wild_encounters() -> None:
    """They share the battle flag and nothing else that matters here.

    Counting them fills an area's band with whatever its trainers happen to
    carry, which is not what the area fields when you walk in the grass.
    """

    assert is_wild_encounter(raw()) is True
    assert is_wild_encounter(raw(battle_state=TRAINER_BATTLE_STATE)) is False


def test_the_battle_start_transition_is_not_an_encounter() -> None:
    """Battle memory lags the battle flag.

    Reads taken in that gap report species zero at level zero, and five of
    them once produced a band for Pallet Town, which has no wild encounters
    at all.
    """

    assert is_wild_encounter(raw(enemy_species_id=0, enemy_level=0)) is False
    assert is_wild_encounter(raw(enemy_level=0)) is False
    assert is_wild_encounter(raw(enemy_species_id=None, enemy_level=None)) is False


def test_recording_is_off_unless_asked_for(monkeypatch: pytest.MonkeyPatch) -> None:
    """A reader should not write files nobody requested."""

    monkeypatch.delenv("POKEMON_RED_ENCOUNTER_LOG", raising=False)
    assert encounter_log_path() is None
    monkeypatch.setenv("POKEMON_RED_ENCOUNTER_LOG", "/somewhere/log.jsonl")
    assert encounter_log_path() == Path("/somewhere/log.jsonl")


# -- summarising -------------------------------------------------------------


def test_a_rare_high_encounter_does_not_define_the_band() -> None:
    """The finding that motivates the whole shape of this module.

    Diglett's Cave fields Diglett in the teens and one Dugtrio near thirty.
    Reduced to a single minimum and maximum it reads as unusable for the very
    trainee it suits.
    """

    entries = [row(map_id=DIGLETTS_CAVE, enemy_level=18) for _ in range(29)]
    entries.append(row(map_id=DIGLETTS_CAVE, enemy_level=31, enemy_species=0x76))

    (band,) = summarize_encounters(entries)

    assert band.samples == 30
    assert band.typical_maximum_level == 18
    assert band.observed_maximum_level == 31
    assert band.has_rare_ceiling


def test_a_band_records_how_well_it_was_measured() -> None:
    """Four samples and four hundred must not look the same on the page."""

    thin = summarize_encounters([row() for _ in range(4)])[0]
    thick = summarize_encounters([row() for _ in range(MINIMUM_TRUSTED_SAMPLES)])[0]

    assert thin.samples == 4 and not thin.is_trusted
    assert thick.is_trusted
    assert thin.as_record()["trusted"] is False


def test_summarising_drops_the_rows_that_are_not_encounters() -> None:
    entries = [
        row(),
        row(battle_state=TRAINER_BATTLE_STATE, enemy_level=50),
        row(map_id=0x00, enemy_species=0, enemy_level=0),
    ]

    bands = summarize_encounters(entries)

    assert [band.map_id for band in bands] == [MANSION]
    assert bands[0].samples == 1
    assert bands[0].observed_maximum_level == 30, "the trainer's level 50 must not leak in"


def test_a_band_cannot_be_built_out_of_order() -> None:
    with pytest.raises(EncounterLogError, match="not ordered"):
        EncounterBand(
            map_id=MANSION,
            samples=5,
            minimum_level=30,
            typical_maximum_level=28,
            observed_maximum_level=39,
            species_ids=(0x21,),
        )


# -- reading and writing -----------------------------------------------------


def test_a_missing_log_says_what_to_do(tmp_path: Path) -> None:
    with pytest.raises(EncounterLogError, match="POKEMON_RED_ENCOUNTER_LOG"):
        list(read_encounter_log(tmp_path / "absent.jsonl"))


def test_a_corrupt_log_names_the_line(tmp_path: Path) -> None:
    log = tmp_path / "log.jsonl"
    log.write_text(json.dumps(row()) + "\nnot json\n", encoding="utf-8")

    with pytest.raises(EncounterLogError, match="line 2"):
        list(read_encounter_log(log))


def test_measurements_survive_a_round_trip(tmp_path: Path) -> None:
    bands = summarize_encounters([row() for _ in range(MINIMUM_TRUSTED_SAMPLES)])
    evidence = tmp_path / "bands.json"
    evidence.write_text(
        json.dumps({"bands": [band.as_record() for band in bands]}), encoding="utf-8"
    )

    assert load_measured_bands(evidence) == bands


# -- becoming a venue --------------------------------------------------------


def test_an_undermeasured_area_never_becomes_a_venue() -> None:
    """Dropped, not downgraded.

    Offering a four-sample band anyway is how a guess acquires the authority
    of a measurement, which is the failure this whole module exists to avoid.
    """

    thin = summarize_encounters([row(map_id=DIGLETTS_CAVE) for _ in range(4)])
    assert grinding_areas(thin, {DIGLETTS_CAVE: "digletts_cave"}) == ()


def test_a_measured_venue_carries_its_evidence() -> None:
    bands = summarize_encounters([row() for _ in range(MINIMUM_TRUSTED_SAMPLES)])

    (area,) = grinding_areas(bands, {MANSION: "pokemon_mansion_1f"}, healer_map_ids=[MANSION])

    assert area.area_id == "pokemon_mansion_1f"
    assert area.has_nearby_healer
    assert area.is_measured and area.measured_samples == MINIMUM_TRUSTED_SAMPLES


def test_the_rare_ceiling_no_longer_disqualifies_a_good_venue() -> None:
    """Diglett's Cave, end to end, for the trainee it was rejecting."""

    entries = [row(map_id=DIGLETTS_CAVE, enemy_level=18) for _ in range(29)]
    entries.append(row(map_id=DIGLETTS_CAVE, enemy_level=31, enemy_species=0x76))
    areas = grinding_areas(
        summarize_encounters(entries),
        {DIGLETTS_CAVE: "digletts_cave"},
        healer_map_ids=[DIGLETTS_CAVE],
    )
    policy = BalancedTeamPolicy(minimum_level=55, max_enemy_level_delta=4)

    chosen = choose_grinding_area(areas, trainee(20), policy)

    assert chosen is not None, "a level-20 trainee should be able to train at 15-21"
    assert chosen.worst_case_encounter_level == 31, "and should still be told about the Dugtrio"


def test_a_chosen_venue_is_one_the_battle_loop_will_actually_fight_in() -> None:
    """Venue selection and matchup acceptance must apply the same rule.

    They did not.  Acceptance uses ``level - minimum_direct_level_advantage``
    whenever that is set, and selection used ``level + max_enemy_level_delta``,
    which under the Mansion policy is dead code.  Selection would therefore
    approve an area the loop refuses every encounter in — the training deadlock
    again, one level further up, and reached only after walking there.

    The invariant is about the *weakest* encounter an area fields, not its
    strongest: a venue worth training in is one where some meaningful share can
    be fought, and the rest fled. An area whose easiest encounter is already out
    of reach is one where nothing can be fought at all.
    """

    entries = [row(map_id=DIGLETTS_CAVE, enemy_level=18) for _ in range(MINIMUM_TRUSTED_SAMPLES)]
    areas = grinding_areas(
        summarize_encounters(entries),
        {DIGLETTS_CAVE: "digletts_cave"},
        healer_map_ids=[DIGLETTS_CAVE],
    )
    binding = BalancedTeamPolicy(
        minimum_level=55, max_enemy_level_delta=0, minimum_direct_level_advantage=15
    )

    for level in range(16, 60):
        chosen = choose_grinding_area(areas, trainee(level), binding)
        if chosen is None:
            continue
        assert is_matchup_acceptable(trainee(level), chosen.minimum_encounter_level, binding), (
            f"level {level} was sent to {chosen.area_id}, "
            f"whose weakest encounter is {chosen.minimum_encounter_level} "
            "and it may not engage even that"
        )


def test_measured_venues_match_the_evidence() -> None:
    """The constant claims to be transcribed from a file. Check that it is.

    A hand-copied band drifting from its measurement is exactly how "30-32"
    outlived the 155 samples that said 28-39.
    """

    evidence = Path("docs/evidence/encounter-bands-2026-08-07.json")
    trusted = {
        band.map_id: band for band in load_measured_bands(evidence) if band.is_trusted
    }
    by_area = {area.area_id: area for area in MEASURED_TRAINING_VENUES}

    assert len(by_area) == len(trusted), (
        f"{len(by_area)} venues declared against {len(trusted)} trusted bands in {evidence}"
    )
    for band in trusted.values():
        name = MapId(band.map_id).name.lower()
        area = by_area[name]
        assert area.minimum_encounter_level == band.minimum_level
        assert area.maximum_encounter_level == band.typical_maximum_level
        assert area.rare_maximum_encounter_level == band.observed_maximum_level
        assert area.measured_samples == band.samples


def test_a_venue_above_the_trainee_is_still_refused() -> None:
    """Relaxing the ceiling must not mean accepting the Mansion at level 20."""

    bands = summarize_encounters([row(enemy_level=34) for _ in range(MINIMUM_TRUSTED_SAMPLES)])
    areas = grinding_areas(bands, {MANSION: "pokemon_mansion_1f"}, healer_map_ids=[MANSION])
    policy = BalancedTeamPolicy(minimum_level=55, max_enemy_level_delta=4)

    assert choose_grinding_area(areas, trainee(20), policy) is None
