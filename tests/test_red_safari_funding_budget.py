"""ROM-free tests for paid Safari admission funding budget and quoting."""

from collections.abc import Collection
from dataclasses import replace
from types import SimpleNamespace

import pytest

import pokemon_red_completion.red_safari_acquisition as safari_acq
from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.gen1_terrain import Terrain
from pokemon_red_completion.gen1_traversal import TraversalRules, surf_local_graph
from pokemon_red_completion.local_router import LocalEdge, LocalGraph
from pokemon_red_completion.observation import (
    Badge,
    MapId,
    OverworldMovementMode,
    RawGameState,
    RedSafariSessionState,
)
from pokemon_red_completion.red_live_safari import (
    discover_reachable_red_safari_areas,
)
from pokemon_red_completion.red_safari_funding_budget import (
    RedSafariFundingBudget,
    RedSafariFundingQuote,
    quote_red_safari_funding,
    red_safari_funding_budget,
)


def _real_safari_fixture(
    monkeypatch,
    *,
    cash: object = 198,
    map_id: int = int(MapId.CELADON_CITY),
    badge_bits: int = int(Badge.THUNDER),
    fly_fuchsia: bool = True,
    has_fly_move: bool = True,
    living_fly: bool = True,
    with_terrain: bool = True,
    with_graph: bool = True,
    with_grass: bool = True,
    with_north: bool = False,
    free_storage_slots: int = 2,
    registered: Collection[int] = (30,),
    battle_state: int = 0,
    dialogue_visible: bool = False,
    pending_trainer: object = None,
    movement_mode: OverworldMovementMode = OverworldMovementMode.WALKING,
    input_ready: bool = True,
):
    """Synthetic supported origin and world using real terrain and graphs."""
    monkeypatch.setattr(safari_acq, "internal_to_dex", lambda _rom: {10: 111, 11: 30, 12: 112})
    tables = {
        int(MapId.SAFARI_ZONE_CENTER): [(25, 10)] * 3 + [(25, 11)] * 7,
    }
    if with_north:
        tables[int(MapId.SAFARI_ZONE_NORTH)] = [(25, 12)] * 3 + [(25, 11)] * 7
    monkeypatch.setattr(safari_acq, "wild_tables", lambda _rom, **_kwargs: tables)

    height, width = 45, 45
    grass_c = [[False] * width for _ in range(height)]
    if with_grass:
        grass_c[23][15] = True
    walkable = tuple(tuple(True for _ in range(width)) for _ in range(height))
    terrain_c = Terrain(
        map_id=int(MapId.SAFARI_ZONE_CENTER),
        tileset=0,
        walkable=walkable,
        grass=tuple(tuple(r) for r in grass_c),
        water=tuple(tuple(False for _ in range(width)) for _ in range(height)),
        tiles=tuple(tuple(0 for _ in range(width)) for _ in range(height)),
    )
    edges_c = {
        (25, 15): (
            LocalEdge((24, 15), "up", required_mode="land", action_kind=MacroActionKind.MOVE),
        ),
        (24, 15): (
            LocalEdge((23, 15), "up", required_mode="land", action_kind=MacroActionKind.MOVE),
            LocalEdge((25, 15), "down", required_mode="land", action_kind=MacroActionKind.MOVE),
        ),
        (23, 15): (
            LocalEdge((24, 15), "down", required_mode="land", action_kind=MacroActionKind.MOVE),
        ),
    }
    graph_c = LocalGraph(edges_c)

    terrain_dict = {int(MapId.SAFARI_ZONE_CENTER): terrain_c} if with_terrain else {}
    graphs_dict = {int(MapId.SAFARI_ZONE_CENTER): graph_c} if with_graph else {}
    blockers_dict = {int(MapId.SAFARI_ZONE_CENTER): frozenset()}
    warps_dict = {int(MapId.SAFARI_ZONE_CENTER): ()}

    if with_north:
        grass_n = [[False] * width for _ in range(height)]
        if with_grass:
            grass_n[29][39] = True
        terrain_n = Terrain(
            map_id=int(MapId.SAFARI_ZONE_NORTH),
            tileset=0,
            walkable=walkable,
            grass=tuple(tuple(r) for r in grass_n),
            water=tuple(tuple(False for _ in range(width)) for _ in range(height)),
            tiles=tuple(tuple(0 for _ in range(width)) for _ in range(height)),
        )
        edges_n = {
            (31, 39): (
                LocalEdge((30, 39), "up", required_mode="land", action_kind=MacroActionKind.MOVE),
            ),
            (30, 39): (
                LocalEdge((29, 39), "up", required_mode="land", action_kind=MacroActionKind.MOVE),
                LocalEdge((31, 39), "down", required_mode="land", action_kind=MacroActionKind.MOVE),
            ),
            (29, 39): (
                LocalEdge((30, 39), "down", required_mode="land", action_kind=MacroActionKind.MOVE),
            ),
        }
        graph_n = LocalGraph(edges_n)
        if with_terrain:
            terrain_dict[int(MapId.SAFARI_ZONE_NORTH)] = terrain_n
        if with_graph:
            graphs_dict[int(MapId.SAFARI_ZONE_NORTH)] = graph_n
        blockers_dict[int(MapId.SAFARI_ZONE_NORTH)] = frozenset()
        warps_dict[int(MapId.SAFARI_ZONE_NORTH)] = ()

    world = SimpleNamespace(
        rom=b"rom",
        terrain=terrain_dict,
        local_graphs=graphs_dict,
        object_blockers=blockers_dict,
        macro_graph=SimpleNamespace(warp_locations=warps_dict),
    )

    moves = ((0x13, 0, 0, 0),) if has_fly_move else ((1, 0, 0, 0),)
    raw = RawGameState(
        game_started=True,
        map_id=map_id,
        player_x=10,
        player_y=10,
        party_count=1,
        battle_state=battle_state,
        player_money=cash,  # type: ignore[arg-type]
        badge_bits=badge_bits,
        party_hp=(50 if living_fly else 0,),
        party_moves=moves,
    )

    class MutableReader:
        def __init__(self, raw_state: RawGameState):
            self.raw = raw_state

        def read(self) -> RawGameState:
            return self.raw

        def read_input_readiness(self) -> SimpleNamespace:
            return SimpleNamespace(ready=input_ready)

        def read_overworld_movement_mode(self) -> OverworldMovementMode:
            return movement_mode

        def read_bottom_dialogue_box_visible(self) -> bool:
            return dialogue_visible

        def read_pending_trainer_battle_identity(self) -> object:
            return pending_trainer

        def read_fly_destinations(self) -> tuple[int, ...]:
            return (int(MapId.FUCHSIA_CITY),) if fly_fuchsia else ()

        def read_safari_session_state(self) -> RedSafariSessionState:
            flags = self.raw.event_flags or b""
            in_safari = False
            game_over = False
            if len(flags) > 73:
                in_safari = bool(flags[73] & (1 << 7))
                game_over = bool(flags[73] & (1 << 6))
            return RedSafariSessionState(
                safari_balls=0,
                safari_steps=0,
                in_safari_zone=in_safari,
                safari_game_over=game_over,
            )

    return world, MutableReader(raw), frozenset(registered), free_storage_slots


def test_budget_dataclass_properties_and_shortfall() -> None:
    budget = RedSafariFundingBudget(available_funds=198)
    assert budget.available_funds == 198
    assert budget.available_cash == 198
    assert budget.admission_cost == 500
    assert budget.cost == 500
    assert budget.target_cash == 500
    assert budget.shortfall == 302

    assert RedSafariFundingQuote is RedSafariFundingBudget
    data = budget.public_dict()
    assert data["schema"] == "pokemon.red.safari-funding-budget.v1"
    assert data["available_funds"] == 198
    assert data["admission_cost"] == 500
    assert data["shortfall"] == 302
    assert data["target_cash"] == 500


@pytest.mark.parametrize(
    ("cash", "expected_shortfall"),
    [(198, 302), (499, 1), (500, 0), (501, 0), (0, 500)],
)
def test_budget_shortfall_progression(cash: int, expected_shortfall: int) -> None:
    budget = RedSafariFundingBudget(available_funds=cash)
    assert budget.shortfall == expected_shortfall


@pytest.mark.parametrize(
    "invalid_funds",
    [-1, -500, True, False, None, "198", 198.5, 1_000_000],
)
def test_budget_dataclass_rejects_invalid_funds(invalid_funds: object) -> None:
    with pytest.raises(ValueError, match="available funds"):
        RedSafariFundingBudget(available_funds=invalid_funds)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "invalid_cost",
    [0, 499, 501, 1000, -500, True, False],
)
def test_budget_dataclass_rejects_invalid_admission_cost(invalid_cost: object) -> None:
    with pytest.raises(ValueError, match="admission cost"):
        RedSafariFundingBudget(available_funds=198, admission_cost=invalid_cost)  # type: ignore[arg-type]


def test_red_safari_funding_budget_supported_state(monkeypatch) -> None:
    world, reader, registered, storage = _real_safari_fixture(monkeypatch, cash=198)
    budget = red_safari_funding_budget(
        world.rom,
        registered,
        free_storage_slots=storage,
        world=world,
        reader=reader,
    )
    assert budget is not None
    assert budget.admission_cost == 500
    assert budget.available_funds == 198
    assert budget.shortfall == 302
    assert budget.cost == 500
    assert budget.target_cash == 500


@pytest.mark.parametrize(
    ("cash", "expected_shortfall", "expected_reachable"),
    [(499, 1, False), (500, 0, True), (501, 0, True)],
)
def test_red_safari_funding_budget_threshold_shortfalls_and_reachability(
    monkeypatch, cash: int, expected_shortfall: int, expected_reachable: bool
) -> None:
    world, reader, registered, storage = _real_safari_fixture(monkeypatch, cash=cash)
    budget = red_safari_funding_budget(
        world.rom,
        registered,
        free_storage_slots=storage,
        world=world,
        reader=reader,
    )
    assert budget is not None
    assert budget.shortfall == expected_shortfall

    areas = discover_reachable_red_safari_areas(
        world.rom,
        registered,
        free_storage_slots=storage,
        world=world,
        reader=reader,
    )
    if expected_reachable:
        assert len(areas) == 1
    else:
        assert areas == ()


@pytest.mark.parametrize(
    "bad_cash",
    [None, True, False, -1, -500, "198", 198.5, 1_000_000],
)
def test_red_safari_funding_budget_rejects_malformed_cash(monkeypatch, bad_cash: object) -> None:
    world, reader, registered, storage = _real_safari_fixture(monkeypatch, cash=bad_cash)
    budget = red_safari_funding_budget(
        world.rom,
        registered,
        free_storage_slots=storage,
        world=world,
        reader=reader,
    )
    assert budget is None


def test_multiple_productive_areas_charge_single_admission(monkeypatch) -> None:
    world, reader, registered, storage = _real_safari_fixture(
        monkeypatch, cash=198, with_north=True
    )
    budget = red_safari_funding_budget(
        world.rom,
        registered,
        free_storage_slots=storage,
        world=world,
        reader=reader,
    )
    assert budget is not None
    assert budget.admission_cost == 500
    assert budget.shortfall == 302


def test_quote_red_safari_funding_alias(monkeypatch) -> None:
    world, reader, registered, storage = _real_safari_fixture(monkeypatch, cash=198)
    quote = quote_red_safari_funding(
        world.rom,
        registered,
        free_storage_slots=storage,
        world=world,
        reader=reader,
    )
    assert quote is not None
    assert quote.cost == 500
    assert quote.shortfall == 302


def test_real_path_all_offered_species_registered_no_quote(monkeypatch) -> None:
    world, reader, registered, storage = _real_safari_fixture(
        monkeypatch, registered=(30, 111)
    )
    assert red_safari_funding_budget(
        world.rom,
        registered,
        free_storage_slots=storage,
        world=world,
        reader=reader,
    ) is None


@pytest.mark.parametrize("missing_part", ["terrain", "graph"])
def test_real_path_missing_terrain_or_graph_no_quote(monkeypatch, missing_part: str) -> None:
    world, reader, registered, storage = _real_safari_fixture(
        monkeypatch,
        with_terrain=(missing_part != "terrain"),
        with_graph=(missing_part != "graph"),
    )
    assert red_safari_funding_budget(
        world.rom,
        registered,
        free_storage_slots=storage,
        world=world,
        reader=reader,
    ) is None


def test_real_path_patrol_cannot_be_derived_no_quote(monkeypatch) -> None:
    world, reader, registered, storage = _real_safari_fixture(monkeypatch, with_grass=False)
    assert red_safari_funding_budget(
        world.rom,
        registered,
        free_storage_slots=storage,
        world=world,
        reader=reader,
    ) is None


@pytest.mark.parametrize("storage_slots", [0, -1])
def test_real_path_missing_storage_no_quote(monkeypatch, storage_slots: int) -> None:
    world, reader, registered, _ = _real_safari_fixture(
        monkeypatch, free_storage_slots=storage_slots
    )
    assert red_safari_funding_budget(
        world.rom,
        registered,
        free_storage_slots=storage_slots,
        world=world,
        reader=reader,
    ) is None


@pytest.mark.parametrize(
    "invalid_transport_kwargs",
    [
        {"badge_bits": 0},
        {"fly_fuchsia": False},
        {"has_fly_move": False},
        {"living_fly": False},
    ],
)
def test_real_path_missing_transport_no_quote(monkeypatch, invalid_transport_kwargs: dict) -> None:
    world, reader, registered, storage = _real_safari_fixture(
        monkeypatch, **invalid_transport_kwargs
    )
    assert red_safari_funding_budget(
        world.rom,
        registered,
        free_storage_slots=storage,
        world=world,
        reader=reader,
    ) is None


def test_real_path_unsupported_gate_origin_no_quote(monkeypatch) -> None:
    # Safari Gate map 156 (0x9C) without gate terrain/graphs and corridor coordinates fails closed.
    world, reader, registered, storage = _real_safari_fixture(monkeypatch, map_id=156)
    assert red_safari_funding_budget(
        world.rom,
        registered,
        free_storage_slots=storage,
        world=world,
        reader=reader,
    ) is None


def test_real_path_supported_gate_origin_quotes_500_target_and_302_shortfall(monkeypatch) -> None:
    world, reader, registered, storage = _real_safari_fixture(
        monkeypatch,
        cash=198,
        map_id=int(MapId.SAFARI_ZONE_GATE),
    )
    reader.read_safari_zone_gate_script = lambda: 0
    walkable = tuple(tuple(2 <= y <= 5 and x in (3, 4) for x in range(10)) for y in range(10))
    terrain_gate = Terrain(
        map_id=int(MapId.SAFARI_ZONE_GATE),
        tileset=0,
        walkable=walkable,
        grass=tuple(tuple(False for _ in range(10)) for _ in range(10)),
        water=tuple(tuple(False for _ in range(10)) for _ in range(10)),
        tiles=tuple(tuple(0 for _ in range(10)) for _ in range(10)),
    )
    graph_gate = surf_local_graph(terrain_gate, TraversalRules((), (), (), (), ()))
    world.terrain[int(MapId.SAFARI_ZONE_GATE)] = terrain_gate
    world.local_graphs[int(MapId.SAFARI_ZONE_GATE)] = graph_gate
    world.object_blockers[int(MapId.SAFARI_ZONE_GATE)] = frozenset()

    reader.raw = replace(
        reader.raw,
        player_x=3,
        player_y=4,
        event_flags=b"\x00" * 320,
    )

    quote = red_safari_funding_budget(
        world.rom,
        registered,
        free_storage_slots=storage,
        world=world,
        reader=reader,
    )
    assert quote is not None
    assert quote.available_funds == 198
    assert quote.cost == 500
    assert quote.shortfall == 302
    assert quote.target_cash == 500


@pytest.mark.parametrize(
    "invalid_reader_kwargs",
    [
        {"battle_state": 1},
        {"dialogue_visible": True},
        {"pending_trainer": (1, 1)},
        {"movement_mode": OverworldMovementMode.SURFING},
        {"input_ready": False},
        {"map_id": int(MapId.FUCHSIA_CITY)},
        {"map_id": 0x0B},
    ],
)
def test_real_path_preconditions_prevent_quote(monkeypatch, invalid_reader_kwargs: dict) -> None:
    world, reader, registered, storage = _real_safari_fixture(
        monkeypatch, **invalid_reader_kwargs
    )
    assert red_safari_funding_budget(
        world.rom,
        registered,
        free_storage_slots=storage,
        world=world,
        reader=reader,
    ) is None


def test_real_path_dynamic_cash_change_updates_fresh_quote(monkeypatch) -> None:
    world, reader, registered, storage = _real_safari_fixture(monkeypatch, cash=198)
    budget1 = red_safari_funding_budget(
        world.rom, registered, free_storage_slots=storage, world=world, reader=reader
    )
    assert budget1 is not None and budget1.shortfall == 302

    reader.raw = replace(reader.raw, player_money=450)
    budget2 = red_safari_funding_budget(
        world.rom, registered, free_storage_slots=storage, world=world, reader=reader
    )
    assert budget2 is not None and budget2.shortfall == 50


def test_quoting_is_strictly_read_only_and_action_free(monkeypatch) -> None:
    """Quoting performs read-only inspection of reader state and does not execute actions."""
    world, reader, registered, storage = _real_safari_fixture(monkeypatch, cash=198)
    before_raw = reader.read()

    budget = red_safari_funding_budget(
        world.rom,
        registered,
        free_storage_slots=storage,
        world=world,
        reader=reader,
    )
    assert budget is not None
    assert reader.read() == before_raw
