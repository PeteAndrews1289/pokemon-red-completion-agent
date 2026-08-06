from __future__ import annotations

from dataclasses import fields, replace

import pytest

from pokemon_red_completion.battle_recovery import first_living_reserve
from pokemon_red_completion.hideout import (
    DEFAULT_HIDEOUT_TIMING,
    HIDEOUT_CHECKPOINT_COUNT,
    OPTIONAL_EVENTS,
    REQUIRED_EVENTS,
    HideoutChapterReport,
    HideoutCheckpoint,
    HideoutTiming,
    HideoutTrainerEvidence,
    _lead_needs_recovery,
    _protected_party_can_continue,
)
from pokemon_red_completion.observation import BLASTOISE_SPECIES_ID, MapId, RawGameState


def _raw() -> RawGameState:
    return RawGameState(
        game_started=True,
        map_id=MapId.CELADON_POKECENTER,
        player_x=3,
        player_y=3,
        party_count=3,
        battle_state=0,
        party_species_ids=(0xB3, 0x40, 0x3B),
        first_party_hp=86,
        first_party_max_hp=86,
        first_party_status=0,
    )


def _report() -> HideoutChapterReport:
    raw = _raw()
    sets = (7, 18, 17, 16, 1)
    return HideoutChapterReport(
        records=tuple(
            HideoutCheckpoint(f"gate_{index}", f"Gate {index}", raw)
            for index in range(HIDEOUT_CHECKPOINT_COUNT)
        ),
        trainers=tuple(
            HideoutTrainerEvidence(
                f"trainer {index}",
                0xE5 if trainer_set == 1 else 0xE6,
                0x1D if trainer_set == 1 else 0x1E,
                trainer_set,
                None if trainer_set == 7 else 0x6A0 + index,
                44 if index < 2 else 61,
                1,
            )
            for index, trainer_set in enumerate(sets)
        ),
        final_raw=raw,
        optional_events=(False,) * len(OPTIONAL_EVENTS),
        required_events=(True,) * len(REQUIRED_EVENTS),
        entered_hideout_bug_event=False,
        lift_key_carried=True,
        silph_scope_carried=True,
        super_potions_used=3,
        super_potions_remaining=9,
        party_hp=(86, 52, 37),
        party_max_hp=(86, 52, 37),
        party_status=(0, 0, 0),
        money_before=5_333,
        money_remaining=10_814,
        frames_executed=100,
        actions_executed=50,
        controller_released=True,
    )


def test_hideout_timing_is_positive_and_bounded() -> None:
    assert HideoutTiming() == DEFAULT_HIDEOUT_TIMING
    assert all(
        isinstance(getattr(DEFAULT_HIDEOUT_TIMING, field.name), int)
        and getattr(DEFAULT_HIDEOUT_TIMING, field.name) > 0
        for field in fields(HideoutTiming)
    )


def test_protected_recovery_selects_only_a_living_non_lead_party_member() -> None:
    assert first_living_reserve((40, 52, 37)) == 1
    assert first_living_reserve((40, 0, 37)) == 2
    assert first_living_reserve((40, 0, 0)) is None
    assert first_living_reserve((40,)) is None


def test_hideout_navigation_accepts_a_living_reserve_after_the_lead_faints() -> None:
    raw = replace(
        _raw(),
        first_party_hp=0,
        party_hp=(0, 52, 37),
    )

    assert _protected_party_can_continue(raw)
    assert not _protected_party_can_continue(replace(raw, party_hp=(0, 0, 0)))
    assert _protected_party_can_continue(replace(raw, party_hp=None), (0, 52, 37))
    assert _protected_party_can_continue(
        replace(raw, party_species_ids=(BLASTOISE_SPECIES_ID, 0x40, 0x3B))
    )


@pytest.mark.parametrize(
    ("current_hp", "maximum_hp", "expected"),
    ((93, 93, False), (92, 93, True)),
)
def test_hideout_only_recovers_a_damaged_lead(
    monkeypatch: pytest.MonkeyPatch,
    current_hp: int,
    maximum_hp: int,
    expected: bool,
) -> None:
    monkeypatch.setattr(
        "pokemon_red_completion.hideout._party_hp", lambda _emulator: (current_hp,)
    )
    monkeypatch.setattr(
        "pokemon_red_completion.hideout._party_max_hp", lambda _emulator: (maximum_hp,)
    )

    assert _lead_needs_recovery(object()) is expected  # type: ignore[arg-type]


@pytest.mark.parametrize("invalid", (0, -1, True, 1.5))
def test_hideout_timing_rejects_invalid_bounds(invalid: object) -> None:
    for field in fields(HideoutTiming):
        with pytest.raises(ValueError, match=f"{field.name} must be a positive integer"):
            replace(DEFAULT_HIDEOUT_TIMING, **{field.name: invalid})


def test_hideout_report_requires_source_bug_and_all_terminal_gates() -> None:
    report = _report()
    assert report.passed
    invalid = (
        replace(report, records=report.records[:-1]),
        replace(report, trainers=report.trainers[:-1]),
        replace(report, optional_events=(True,) + report.optional_events[1:]),
        replace(report, required_events=(False,) + report.required_events[1:]),
        replace(report, entered_hideout_bug_event=True),
        replace(report, lift_key_carried=False),
        replace(report, silph_scope_carried=False),
        replace(report, super_potions_remaining=5),
        replace(report, party_hp=(85, 52, 37)),
        replace(report, money_remaining=10_813),
        replace(report, controller_released=False),
    )
    assert all(not candidate.passed for candidate in invalid)


def test_hideout_report_accepts_conserved_surplus_recovery_inventory() -> None:
    report = replace(
        _report(),
        super_potions_used=2,
        super_potions_remaining=10,
    )

    assert report.passed


def test_hideout_public_report_discloses_bug_and_assistance_scope() -> None:
    public = _report().public_dict()
    assert public["status"] == "ok"
    assert public["objectives"] == ["clear_rocket_hideout", "obtain_silph_scope"]
    assert public["optional_trainers_bypassed"] == 8
    assert public["entered_hideout_bug_event"] is False
    assert public["inventory"] == {
        "lift_key_carried": True,
        "silph_scope_carried": True,
        "super_potions_used": 3,
        "super_potions_remaining": 9,
        "money_before": 5_333,
        "money_remaining": 10_814,
    }
