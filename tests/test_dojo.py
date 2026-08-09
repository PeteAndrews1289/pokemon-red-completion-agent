from __future__ import annotations

from pokemon_red_completion.battle_runtime import BattleResourcePolicy
from pokemon_red_completion.dojo import (
    DOJO_BATTLE_IDENTITIES,
    DOJO_BATTLE_PARTIES,
    DOJO_CHECKPOINT_COUNT,
    DOJO_TRAINER_EVENTS,
    HITMONLEE,
    DojoBattleEvidence,
    DojoChapterReport,
    DojoCheckpoint,
    DojoTurn,
    _encounter_party,
    _turn_evidence_satisfied,
    _turns_match_source_party,
)
from pokemon_red_completion.observation import EventFlag, MapId, RawGameState


def _terminal() -> RawGameState:
    return RawGameState(
        game_started=True,
        map_id=MapId.SAFFRON_POKECENTER,
        player_x=3,
        player_y=3,
        party_count=6,
        battle_state=0,
        party_species_ids=(0x1C, 0x40, 0x76, 0x84, 0x68, HITMONLEE),
        first_party_level=50,
        first_party_hp=150,
        first_party_max_hp=150,
    )


def test_dojo_source_pins_map_events_and_parties() -> None:
    assert BattleResourcePolicy.NO_ADDITIONAL_CONSTRAINT == "none"
    assert MapId.FIGHTING_DOJO == 0xB1
    assert tuple(int(event) for event in DOJO_TRAINER_EVENTS) == (
        0x355,
        0x353,
        0x354,
        0x352,
        0x351,
    )
    assert EventFlag.DEFEATED_FIGHTING_DOJO == 0x350
    assert EventFlag.GOT_HITMONLEE == 0x356
    assert EventFlag.GOT_HITMONCHAN == 0x357
    assert DOJO_BATTLE_IDENTITIES == (
        (0xE0, 0xE0, 5),
        (0xE0, 0xE0, 3),
        (0xE0, 0xE0, 4),
        (0xE0, 0xE0, 2),
        (0xE0, 0xE0, 1),
    )
    assert DOJO_BATTLE_PARTIES == (
        ((0x6A, 31), (0x39, 31), (0x75, 31)),
        ((0x6A, 32), (0x29, 32)),
        ((0x75, 36),),
        ((0x39, 31), (0x39, 31), (0x75, 31)),
        ((0x2B, 37), (0x2C, 37)),
    )


def test_dojo_encounter_party_collapses_repeated_turns_only() -> None:
    turns = (
        DojoTurn(0x39, 31, 4),
        DojoTurn(0x39, 31, 4),
        DojoTurn(0x75, 31, 4),
    )
    assert _encounter_party(turns) == ((0x39, 31), (0x75, 31))
    assert _turns_match_source_party(
        turns,
        ((0x39, 31), (0x39, 31), (0x75, 31)),
    )
    assert not _turn_evidence_satisfied(
        (),
        ((0x39, 31),),
        learned_policy_active=False,
    )
    assert _turn_evidence_satisfied(
        (),
        ((0x39, 31),),
        learned_policy_active=True,
    )
    assert not _turn_evidence_satisfied(
        (DojoTurn(0x75, 31, 4),),
        ((0x39, 31),),
        learned_policy_active=True,
    )


def test_dojo_report_qualifies_full_six_member_gift_boundary() -> None:
    terminal = _terminal()
    records = tuple(
        DojoCheckpoint(f"checkpoint_{index}", f"Checkpoint {index}", terminal)
        for index in range(DOJO_CHECKPOINT_COUNT)
    )
    battles = tuple(
        DojoBattleEvidence(
            identity,
            party,
            tuple(DojoTurn(species, level, 4) for species, level in party),
            int(event),
            "teacher_callback",
        )
        for identity, party, event in zip(
            DOJO_BATTLE_IDENTITIES,
            DOJO_BATTLE_PARTIES,
            DOJO_TRAINER_EVENTS,
            strict=True,
        )
    )
    report = DojoChapterReport(
        records=records,
        final_raw=terminal,
        battles=battles,
        events_before=(False,) * 5,
        events_after=(True,) * 5,
        party_before=(0x1C, 0x40, 0x76, 0x84, 0x68),
        party_after=(0x1C, 0x40, 0x76, 0x84, 0x68, HITMONLEE),
        party_levels=(50, 50, 50, 50, 50, 30),
        party_hp=(150, 120, 110, 105, 180, 80),
        party_max_hp=(150, 120, 110, 105, 180, 80),
        party_status=(0, 0, 0, 0, 0, 0),
        got_hitmonlee=True,
        got_hitmonchan=False,
        dojo_defeated=True,
        frames_executed=10_000,
        actions_executed=300,
        input_ready=True,
        controller_released=True,
    )

    assert report.passed
    assert report.public_dict()["objective"] == "recruit_hitmonlee"
