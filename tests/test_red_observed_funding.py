"""Changed terrain must alter execution paths without rewriting saved menus."""

from dataclasses import replace
from types import SimpleNamespace

import pytest

from pokemon_red_completion import red_regional_trainer_funding as regional
from pokemon_red_completion import red_routed_trainer_funding as funding
from pokemon_red_completion.gen1_trainer_parties import TrainerPartyMember, TrainerPartyQuote
from pokemon_red_completion.gen1_trainer_sight import TrainerFacing, TrainerSightZone
from pokemon_red_completion.global_router import MacroGraph
from pokemon_red_completion.local_router import LocalEdge, LocalGraph
from pokemon_red_completion.observation import CurrentMapBlocks, RawGameState
from pokemon_red_completion.route_executor import TraversalSnapshot


@pytest.fixture
def setup(monkeypatch):
    raw = RawGameState(
        game_started=True,
        map_id=22,
        player_y=1,
        player_x=0,
        battle_state=0,
        party_count=1,
        event_flags=bytes(319),
    )
    blocks = CurrentMapBlocks(22, ((0, 0, 0), (0, 0, 0)))
    start = TraversalSnapshot(22, (1, 0), ready=True, mode="land")
    trainer = TrainerSightZone(22, 1, 201, 9, (1, 4), TrainerFacing.RIGHT, 1, 17, False, True)
    quote = TrainerPartyQuote(201, 9, (TrainerPartyMember(108, 23, 21),), 15, 315)
    graph = LocalGraph(
        {
            (y, x): tuple(
                LocalEdge((y + dy, x + dx), action)
                for dy, dx, action in (
                    (-1, 0, "up"),
                    (1, 0, "down"),
                    (0, -1, "left"),
                    (0, 1, "right"),
                )
                if 0 <= y + dy < 3 and 0 <= x + dx < 5
            )
            for y in range(3)
            for x in range(5)
        }
    )
    live_graph = LocalGraph(
        {
            at: tuple(e for e in es if e.target != (1, 2))
            for at, es in graph.edges.items()
            if at != (1, 2)
        }
    )
    live = SimpleNamespace(macro_graph=MacroGraph({22: ()}), local_graphs={22: live_graph})
    overlays = []

    def overlay(value):
        assert value == blocks
        overlays.append(value)
        return live

    world = SimpleNamespace(
        rom=b"test",
        macro_graph=live.macro_graph,
        local_graphs={22: graph},
        with_current_blocks=overlay,
    )
    reader = SimpleNamespace(
        read=lambda: raw,
        read_current_map_blocks=lambda: blocks,
        read_current_map_objects=lambda: (),
        read_pending_trainer_battle_identity=lambda: None,
    )
    router = SimpleNamespace(
        world=world,
        runtime=SimpleNamespace(reader=reader),
        regional_trainer_funding=True,
        trainer_pending_recovery=False,
    )
    monkeypatch.setattr(funding, "trainer_headers", lambda *_a, **_k: (object(),))
    monkeypatch.setattr(funding, "map_object_events", lambda *_: ())
    monkeypatch.setattr(funding, "trainer_sight_zones", lambda *_: (trainer,))
    monkeypatch.setattr(funding, "Gen1TrainerSightProjector", lambda *_a, **_k: object())
    monkeypatch.setattr(
        funding, "Gen1TraversalObserver", lambda *_: SimpleNamespace(observe=lambda: start)
    )
    monkeypatch.setattr(regional, "trainer_party_quote", lambda *_: quote)
    return router, raw, blocks, live, overlays


def test_closed_shortcut_uses_alternate_path_to_same_trainer_and_keeps_menu(setup):
    router, _, _, _, overlays = setup
    (quoted,) = funding._candidates(router)
    assert (1, 2) in [s.expected_at for s in quoted.approach.steps]
    actual = funding._observed_funding_target(router, quoted)
    assert overlays
    assert actual.trainer == quoted.trainer and actual.quote == quoted.quote
    assert (1, 2) not in [s.expected_at for s in actual.approach.steps]
    assert any(s.expected_at[0] != 1 for s in actual.approach.steps)
    assert funding._candidates(router) == (quoted,)


def test_no_observed_route_does_not_fall_back_to_static(setup):
    router, _, _, live, _ = setup
    (quoted,) = funding._candidates(router)
    live.local_graphs[22] = LocalGraph({(1, 0): ()})
    with pytest.raises(funding.RedTrainerFundingError, match="no unique"):
        funding._observed_funding_target(router, quoted)


def test_versioned_menu_omits_unreachable_funding_but_legacy_stays_reproducible(setup):
    router, _, _, live, _ = setup
    legacy = funding._candidates(router)
    assert len(legacy) == 1
    live.local_graphs[22] = LocalGraph({(1, 0): ()})
    router.observed_trainer_funding = True
    assert funding._candidates(router) == ()
    router.observed_trainer_funding = False
    assert funding._candidates(router) == legacy


def test_versioned_menu_quotes_actual_detour(setup):
    router, *_ = setup
    router.observed_trainer_funding = True
    (offered,) = funding._candidates(router)
    assert (1, 2) not in [s.expected_at for s in offered.approach.steps]


def test_versioned_menu_rejects_wrong_observed_map(setup):
    router, _, blocks, _, _ = setup
    router.observed_trainer_funding = True
    router.runtime.reader.read_current_map_blocks = lambda: replace(blocks, map_id=23)
    with pytest.raises(funding.RedTrainerFundingError, match="active field"):
        funding._candidates(router)


@pytest.mark.parametrize("damage", ["map", "battle", "changed_raw", "changed_blocks", "malformed"])
def test_bad_or_changing_observation_fails_closed(setup, damage):
    router, raw, blocks, _, _ = setup
    (quoted,) = funding._candidates(router)
    reader = router.runtime.reader
    if damage == "map":
        reader.read_current_map_blocks = lambda: replace(blocks, map_id=23)
    elif damage == "battle":
        reader.read = lambda: replace(raw, battle_state=1)
    elif damage == "changed_raw":
        values = iter([raw, raw, replace(raw, player_x=1)])
        reader.read = lambda: next(values)
    elif damage == "changed_blocks":
        values = iter([blocks, replace(blocks, rows=((1, 0, 0), (0, 0, 0)))])
        reader.read_current_map_blocks = lambda: next(values)
    else:

        def invalid(_):
            raise ValueError("invalid observed geometry")

        router.world.with_current_blocks = invalid
    with pytest.raises((funding.RedTrainerFundingError, ValueError)):
        funding._observed_funding_target(router, quoted)


@pytest.mark.parametrize("damage", ["trainer", "quote"])
def test_requalification_cannot_change_quoted_trainer_or_reward(setup, monkeypatch, damage):
    router, *_ = setup
    (quoted,) = funding._candidates(router)
    altered = (
        replace(quoted, trainer=replace(quoted.trainer, sprite_index=2))
        if damage == "trainer"
        else replace(quoted, quote=replace(quoted.quote, base_money=20))
    )
    monkeypatch.setattr(funding, "_candidates", lambda *_a, **_k: (altered,))
    with pytest.raises(funding.RedTrainerFundingError, match="no unique"):
        funding._observed_funding_target(router, quoted)
