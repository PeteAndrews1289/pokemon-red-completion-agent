from __future__ import annotations

from dataclasses import dataclass, replace
from types import SimpleNamespace

import pytest

import pokemon_red_completion.red_league_funding as league
from pokemon_red_completion.gen1_trainer_parties import (
    TrainerPartyMember,
    TrainerPartyQuote,
)
from pokemon_red_completion.observation import Badge, EventFlag, ItemId, RawGameState
from pokemon_red_completion.party import (
    MoveObservation,
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


@dataclass(frozen=True)
class _World:
    local_graphs: object
    object_blockers: object
    macro_graph: str
    exit_plan: object
    entry_plan: object
    supply_plan: object

    def plan_feasible_to_map(self, start, target, **kwargs):
        if target == 5:
            assert self.macro_graph == "raw"
            return self.exit_plan
        if target == 174:
            assert start.at == (6, 9)
            return self.supply_plan
        assert target == 245 and self.macro_graph == "scripted-lorelei-arrival"
        assert start.at == (5, 2)
        return self.entry_plan


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
    monkeypatch.setattr(league, "_minimum_attack_allocation", lambda *args: (50, 26))
    monkeypatch.setattr(league, "fly_menu_indices", lambda raw: (0, 9))
    monkeypatch.setattr(league, "red_fly_landings", lambda rom: ((9, (6, 9)),))
    monkeypatch.setattr(league, "trainer_room_arrival", lambda *args: "lorelei-arrival")
    monkeypatch.setattr(
        league,
        "with_scripted_trainer_arrival",
        lambda graph, arrival: "scripted-lorelei-arrival",
    )
    start = TraversalSnapshot(89, (3, 3), True, mode="land", last_outside_map=5)
    monkeypatch.setattr(
        league,
        "Gen1TraversalObserver",
        lambda reader: SimpleNamespace(observe=lambda: start),
    )
    monkeypatch.setattr(league, "_walking_plan", lambda plan: True)
    exit_plan = SimpleNamespace(steps=("out",), terminal_map=5, terminal_at=(11, 14))
    entry_plan = SimpleNamespace(steps=("in", "up"), terminal_map=108, terminal_at=(2, 5))
    supply_plan = SimpleNamespace(steps=("shop",), terminal_map=174, terminal_at=(5, 2))
    world = _World(
        {9: SimpleNamespace(edges={(6, 9): ()})},
        {9: frozenset(), 174: frozenset()},
        "raw",
        exit_plan,
        entry_plan,
        supply_plan,
    )
    raw = RawGameState(
        game_started=True,
        map_id=89,
        player_y=3,
        player_x=3,
        battle_state=0,
        player_money=3_000,
        bag_items=((16, 1),),
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
        "schema": "pokemon.red.repeatable-league-funding-qualification.v2",
        "status": "ready_for_bounded_executor",
        "exit_steps": 1,
        "fly_town": 9,
        "supply_steps": 1,
        "supply_sales": [],
        "sale_proceeds": 0,
        "full_restores_purchased": 0,
        "purchase_cost": 0,
        "entry_steps": 2,
        "battle_count": 5,
        "expected_gross_income": 1_500,
        "expected_net_income": 1_500,
        "supported_attack_pp": 50,
        "opponent_attack_demands": 26,
        "minimum_one_attack_allocation": True,
        "battles": [
            {
                "objective_id": f"defeat_{name}",
                "expected_money": money,
                "maximum_opponent_level": level,
                "recovery_controller": (
                    "damage-bounded-zero-item" if name in {"lorelei", "bruno", "agatha"}
                    else "critical-inclusive" if name == "lance"
                    else "ordinary-bounded-healing"
                ),
                "maximum_full_restores": 1 if name == "champion" else 0,
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
        "cumulative_recovery_reserved": 1,
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


def test_supply_sells_only_whole_renewable_stacks_to_fund_one_restore():
    route = SimpleNamespace(steps=("shop",))
    plan = league._plan_supply(
        553,
        (
            (int(ItemId.HELIX_FOSSIL), 1),
            (int(ItemId.X_ACCURACY), 3),
            (int(ItemId.X_SPECIAL), 8),
            (int(ItemId.X_ATTACK), 1),
        ),
        route,
    )
    assert plan.route is route
    assert [(sale.item, sale.quantity) for sale in plan.sales] == [
        (ItemId.X_SPECIAL, 8),
        (ItemId.X_ACCURACY, 3),
    ]
    assert plan.sale_proceeds == 2_825
    assert plan.purchase_cost == 3_000
    assert 553 + plan.sale_proceeds - plan.purchase_cost == 378


def test_supply_refuses_to_liquidate_finite_completion_assets():
    with pytest.raises(league.RedLeagueFundingError, match="renewable inventory"):
        league._plan_supply(
            553,
            ((int(ItemId.HELIX_FOSSIL), 1), (int(ItemId.TM14_BLIZZARD), 1)),
            SimpleNamespace(steps=("shop",)),
        )


def test_pp_allocation_cannot_reuse_one_effective_pp_for_two_opponents():
    party = PartyObservation((PartyMemberObservation(
        slot=1,
        species_id=84,
        level=75,
        hp=200,
        max_hp=200,
        status=StatusCondition.HEALTHY,
        moves=(MoveObservation(85, 1), MoveObservation(33, 35)),
        experience=None,
    ),))
    quote = TrainerPartyQuote(
        201,
        1,
        (TrainerPartyMember(25, 9, 50), TrainerPartyMember(25, 9, 50)),
        10,
        100,
    )
    with pytest.raises(league.RedLeagueFundingError, match="cannot allocate"):
        league._minimum_attack_allocation(party, (quote,))

    funded = replace(
        party,
        members=(replace(
            party.members[0],
            moves=(MoveObservation(85, 2), MoveObservation(33, 35)),
        ),),
    )
    assert league._minimum_attack_allocation(funded, (quote,)) == (37, 2)
