from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

import pokemon_red_completion.red_league_funding as league
from pokemon_red_completion.gen1_trainer_parties import (
    TrainerPartyMember,
    TrainerPartyQuote,
)
from pokemon_red_completion.observation import Badge, EventFlag, RawGameState
from pokemon_red_completion.party import (
    PartyMemberObservation,
    PartyObservation,
    StatusCondition,
)
from pokemon_red_completion.route_executor import TraversalSnapshot


def _quote(number: int, payout: int) -> TrainerPartyQuote:
    return TrainerPartyQuote(
        201,
        number,
        (TrainerPartyMember(28, 9, 50 + number),),
        10,
        payout,
    )


def _party() -> PartyObservation:
    return PartyObservation(
        (
            PartyMemberObservation(
                slot=1,
                species_id=28,
                level=75,
                hp=250,
                max_hp=250,
                status=StatusCondition.HEALTHY,
                moves=(),
                experience=None,
            ),
        )
    )


@pytest.fixture
def qualified(monkeypatch):
    room_quotes = iter((_quote(1, 100), _quote(2, 200), _quote(3, 300), _quote(4, 400)))
    monkeypatch.setattr(league, "_room_quote", lambda *args: next(room_quotes))
    monkeypatch.setattr(
        league,
        "champion_script_binding",
        lambda *args: SimpleNamespace(opponent=202, trainer_set=5),
    )
    monkeypatch.setattr(league, "trainer_party_quote", lambda *args, **kwargs: _quote(5, 500))
    monkeypatch.setattr(league, "_require_party_coverage", lambda *args: None)
    monkeypatch.setattr(league, "fly_menu_indices", lambda raw: (0, 9))
    monkeypatch.setattr(league, "red_fly_landings", lambda rom: ((9, (6, 9)),))
    start = TraversalSnapshot(89, (3, 3), True, mode="land", last_outside_map=5)
    monkeypatch.setattr(
        league,
        "Gen1TraversalObserver",
        lambda reader: SimpleNamespace(observe=lambda: start),
    )
    monkeypatch.setattr(league, "_walking_plan", lambda plan: True)
    exit_plan = SimpleNamespace(steps=("out",), terminal_map=5, terminal_at=(11, 14))
    entry_plan = SimpleNamespace(steps=("in", "up"), terminal_map=108, terminal_at=(2, 5))
    world = SimpleNamespace(
        local_graphs={9: SimpleNamespace(edges={(6, 9): ()})},
        object_blockers={9: frozenset()},
        plan_feasible_to_map=lambda start, target: exit_plan if target == 5 else entry_plan,
    )
    raw = RawGameState(
        game_started=True,
        map_id=89,
        player_y=3,
        player_x=3,
        battle_state=0,
        player_money=500,
        badge_bits=int(Badge.THUNDER),
        event_flags=bytes(320),
        party_count=1,
    )
    observation = SimpleNamespace(
        raw=raw,
        input_ready=True,
        game_state=SimpleNamespace(facts=frozenset({"story:victory_road_cleared"})),
        party=_party(),
    )
    reader = SimpleNamespace(
        read_fly_destinations=lambda: (0, 9),
        read_rival_starter=lambda: 153,
    )
    return observation, reader, world


def test_qualification_proves_transport_and_five_cartridge_payouts(qualified):
    observation, reader, world = qualified
    result = league.qualify_red_league_funding(b"rom", observation, reader, world)
    assert result.expected_gross_income == 1_500
    assert [battle.objective_id for battle in result.battles] == [
        "defeat_lorelei",
        "defeat_bruno",
        "defeat_agatha",
        "defeat_lance",
        "defeat_champion",
    ]
    assert result.public_dict() == {
        "schema": "pokemon.red.repeatable-league-funding-qualification.v1",
        "status": "ready_for_bounded_executor",
        "exit_steps": 1,
        "fly_town": 9,
        "entry_steps": 2,
        "battle_count": 5,
        "expected_gross_income": 1_500,
        "battles": [
            {
                "objective_id": f"defeat_{name}",
                "expected_money": money,
                "maximum_opponent_level": level,
            }
            for name, money, level in (
                ("lorelei", 100, 51),
                ("bruno", 200, 52),
                ("agatha", 300, 53),
                ("lance", 400, 54),
                ("champion", 500, 55),
            )
        ],
        "controller_actions": 0,
        "emulator_frames": 0,
        "survival_proven": False,
        "net_profit_proven": False,
        "rematch_executed": False,
    }


@pytest.mark.parametrize("consumed", [EventFlag.BEAT_LORELEI, EventFlag.BEAT_LANCE])
def test_qualification_rejects_a_partially_consumed_league(qualified, consumed):
    observation, reader, world = qualified
    flags = bytearray(observation.raw.event_flags)
    flag = int(consumed)
    flags[flag // 8] |= 1 << (flag % 8)
    observation.raw = replace(observation.raw, event_flags=bytes(flags))
    with pytest.raises(league.RedLeagueFundingError, match="fresh postgame"):
        league.qualify_red_league_funding(b"rom", observation, reader, world)


def test_qualification_rejects_nominal_income_that_would_hit_the_money_cap(qualified):
    observation, reader, world = qualified
    observation.raw = replace(observation.raw, player_money=999_000)
    with pytest.raises(league.RedLeagueFundingError, match="money headroom"):
        league.qualify_red_league_funding(b"rom", observation, reader, world)
