from dataclasses import replace
from types import SimpleNamespace

import pytest

from pokemon_red_completion.battle_runtime import BattleIntent, BattleRuntimeTiming
from pokemon_red_completion.observation import EventFlag, MapId, PokemonRedStateReader, RamAddress
from pokemon_red_completion.red_league_funding import (
    RedLeagueFundingError,
    projected_fresh_league_events,
)
from pokemon_red_completion.red_learned_league import (
    FrozenLeagueController,
    learned_league_controller,
)
from pokemon_red_completion.red_learned_trainer import FROZEN_K_SHA256, K_QUALIFICATION_SHA256


def flags(*events):
    values = bytearray(320)
    for event in events:
        values[int(event) // 8] |= 1 << (int(event) % 8)
    return bytes(values)


@pytest.mark.parametrize("count", [1, 2, 3, 5])
def test_partial_prefix_requires_actual_reset_latch_and_projects_exact_source_range(count):
    prefix = (
        EventFlag.BEAT_LORELEI,
        EventFlag.BEAT_BRUNO,
        EventFlag.BEAT_AGATHA,
        EventFlag.BEAT_LANCES_ROOM_TRAINER,
        EventFlag.BEAT_LANCE,
    )[:count]
    before = flags(*prefix, 0x917, 0x8E0, 10)
    after, changed = projected_fresh_league_events(before, challenge_started=True)
    assert changed and after == flags(10)
    assert before == flags(*prefix, 0x917, 0x8E0, 10)
    with pytest.raises(RedLeagueFundingError):
        projected_fresh_league_events(before, challenge_started=False)


@pytest.mark.parametrize(
    "prefix",
    [
        (EventFlag.BEAT_BRUNO,),
        (EventFlag.BEAT_LANCE,),
        (EventFlag.BEAT_LORELEI, EventFlag.BEAT_CHAMPION_RIVAL),
    ],
)
def test_inconsistent_or_completed_prefix_never_becomes_fresh(prefix):
    with pytest.raises(RedLeagueFundingError):
        projected_fresh_league_events(flags(*prefix), challenge_started=True)


def test_all_clear_lobby_only_clears_boulder_without_latch():
    assert projected_fresh_league_events(flags(10, 0x917), challenge_started=False) == (
        flags(10),
        True,
    )
    assert projected_fresh_league_events(flags(10), challenge_started=False) == (flags(10), False)
    with pytest.raises(RedLeagueFundingError):
        projected_fresh_league_events(flags(), challenge_started=1)


@pytest.mark.parametrize("byte", [0, 1, 2, 3, 255])
def test_reset_latch_is_semantic_read_only(byte):
    memory = SimpleNamespace(read_u8=lambda at: byte if at == RamAddress.ELITE_FOUR_FLAGS else 0)
    assert PokemonRedStateReader(memory).read_league_challenge_started() is bool(byte & 2)


@pytest.mark.parametrize(
    "objective,map_id,plan",
    [
        ("defeat_lorelei", MapId.LORELEIS_ROOM, "cartridge-trainer-story"),
        ("defeat_champion", MapId.CHAMPIONS_ROOM, "cartridge-final-story"),
    ],
)
@pytest.mark.parametrize("recovery", [False, True])
def test_league_adapter_forwards_guards_and_executor_without_teacher(
    objective, map_id, plan, recovery,
):
    raw = object()
    calls = []
    executor = object()

    def guard(state):
        calls.append(state)

    def play(reader, actions, **kwargs):
        assert type(kwargs["expected_map"]) is int
        assert actions is executor and kwargs["decision_guard"] is guard
        assert kwargs["authority"] == "frozen-k-league-development"
        assert kwargs["require_win"] and not kwargs["resume"]
        assert kwargs["allow_immune_switch_recovery"] is recovery
        return SimpleNamespace(decisions=({"kind": "attack"}, {"kind": "voluntary_switch"}))

    battler = SimpleNamespace(
        model_sha256=FROZEN_K_SHA256, qualification_sha256=K_QUALIFICATION_SHA256, _play=play
    )
    controller = FrozenLeagueController(
        battler, "league-profit-recovery-v1" if recovery else "strict-no-faint-v1", recovery,
    )

    def teacher(*args):
        pytest.fail("teacher called")

    assert (
        controller.run(
            SimpleNamespace(read=lambda: raw),
            executor,
            teacher,
            expected_map=map_id,
            intent=BattleIntent(objective, plan),
            timing=BattleRuntimeTiming(),
            label="test",
            consume_battle_start_schedule=False,
            move_decision_guard=guard,
            battle_exit_guard=guard,
        )
        is raw
    )
    assert calls == [raw] and controller.moves_selected == 1 and len(controller.switches) == 1
    assert controller.heals_claimed == 0


def test_unknown_or_unbound_actor_rejected_without_execution():
    assert learned_league_controller(SimpleNamespace()) is None
    with pytest.raises(ValueError):
        learned_league_controller(SimpleNamespace(league_battle_controller=object()))
    bad = FrozenLeagueController(
        SimpleNamespace(model_sha256="bad", qualification_sha256=K_QUALIFICATION_SHA256)
    )
    with pytest.raises(ValueError):
        learned_league_controller(SimpleNamespace(league_battle_controller=bad))


@pytest.mark.parametrize("contract,enabled", [
    ("strict-no-faint-v1", True), ("league-profit-recovery-v1", 1),
    ("league-profit-recovery-v1", None),
])
def test_immune_recovery_requires_typed_explicit_contract(contract, enabled):
    battler = SimpleNamespace(
        model_sha256=FROZEN_K_SHA256, qualification_sha256=K_QUALIFICATION_SHA256,
    )
    with pytest.raises(ValueError, match="explicit"):
        FrozenLeagueController(battler, contract, enabled).require_identity()


def test_learned_qualification_has_no_sales_or_item_controller(qualified):  # noqa: F811
    from pokemon_red_completion.red_league_funding import qualify_red_league_funding

    observation, reader, world = qualified
    reader.read_league_challenge_started = lambda: False
    observation.raw = replace(observation.raw, player_money=573, bag_items=())
    result = qualify_red_league_funding(
        b"rom", observation, reader, world, learned_development=True
    )
    assert result.supply.sales == () and result.supply.purchase_cost == 0
    assert all(
        q.recovery_controller == "frozen-k-development"
        and q.maximum_full_restores == 0
        and q.maximum_critical_exposures == 0
        for q in result.battles
    )


from test_red_league_funding import qualified  # noqa: E402,F401


@pytest.mark.parametrize("hp", [(50, 0), (0, 10), (1, 0, 0, 0, 0, 0)])
def test_recovery_contract_allows_fainted_reserves_but_default_remains_strict(hp):
    raw = SimpleNamespace(party_hp=hp, party_count=len(hp))
    FrozenLeagueController(None, "league-profit-recovery-v1").require_party_hp(raw)
    with pytest.raises(ValueError):
        FrozenLeagueController(None).require_party_hp(raw)


@pytest.mark.parametrize(
    "hp,count",
    [((0, 0), 2), ((-1, 50), 2), ((True, 50), 2), ((50,), 2), (None, 2), ((1,), True), ((), 0)],
)
def test_recovery_contract_still_rejects_loss_or_invalid_hp(hp, count):
    with pytest.raises(ValueError):
        FrozenLeagueController(None, "league-profit-recovery-v1").require_party_hp(
            SimpleNamespace(party_hp=hp, party_count=count)
        )
