"""Action-free qualification for renewable Red League income.

Ordinary trainer payouts are finite.  A completed Red cartridge can rematch the
Elite Four, so this module proves whether the current save can enter that loop
and computes its cartridge-backed gross payout.  It deliberately sends no input
and does not claim survival, net profit, or a completed rematch executor.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from .gen1_champion_script import champion_script_binding
from .gen1_field_moves import Gen1FieldMoveError, fly_menu_indices
from .gen1_route_runtime import Gen1TraversalObserver
from .gen1_scripted_arrival import trainer_room_arrival, with_scripted_trainer_arrival
from .gen1_trainer_parties import TrainerPartyQuote, trainer_party_quote
from .gen1_trainer_sight import static_trainer_sight_zones, trainer_headers
from .gen1_traversal import map_object_events
from .observation import Badge, EventFlag, ItemId, MapId, PokemonRedStateReader, event_flag_is_set
from .party import PartyObservation
from .red_battle_catalog import (
    RED_BATTLE_CATALOG,
    pokemon_red_move_ref,
    pokemon_red_species_ref,
)
from .red_collection_fly import red_fly_landings
from .red_goal_manager import RedGoalObservation
from .red_resource_goal_router import _walking_plan
from .red_trainer_party import plan_trainer_party, trainer_matchup_candidates
from .route_plan import RoutePlan, RoutePlanningError
from .strategic_navigation_scenario_runtime import StrategicScenarioRouteWorld


class RedLeagueFundingError(ValueError):
    """The live save cannot honestly advertise a renewable League attempt."""


@dataclass(frozen=True, slots=True)
class RedLeagueBattleQuote:
    objective_id: str
    trainer_class: int
    trainer_set: int
    expected_money: int
    maximum_opponent_level: int
    recovery_controller: str = "damage-bounded-zero-item"
    maximum_full_restores: int = 0
    maximum_critical_exposures: int = 0

    def __post_init__(self) -> None:
        risk = self.recovery_controller == "bounded-critical-risk"
        healing = self.recovery_controller == "ordinary-bounded-healing"
        if (
            self.recovery_controller not in {
                "damage-bounded-zero-item", "bounded-critical-risk",
                "ordinary-bounded-healing",
            }
            or type(self.maximum_full_restores) is not int
            or type(self.maximum_critical_exposures) is not int
            or (risk and (
                self.objective_id != "defeat_lance"
                or self.maximum_critical_exposures != 2
                or self.maximum_full_restores != 0
            ))
            or (not risk and self.maximum_critical_exposures != 0)
            or (healing != (self.maximum_full_restores == 1))
        ):
            raise ValueError("League battle controller contract differs")


@dataclass(frozen=True, slots=True)
class RedLeagueSupplySale:
    """One prospective sale of renewable battle stock at Indigo."""

    item: ItemId
    quantity: int
    unit_proceeds: int

    def __post_init__(self) -> None:
        prices = {
            ItemId.X_SPECIAL: 175,
            ItemId.X_ACCURACY: 475,
            ItemId.X_ATTACK: 250,
        }
        if self.item not in prices or self.unit_proceeds != prices[self.item]:
            raise ValueError("League sale is not renewable source-priced stock")
        if type(self.quantity) is not int or not 1 <= self.quantity <= 99:  # noqa: E721
            raise ValueError("League sale quantity must be one through 99")

    @property
    def proceeds(self) -> int:
        return self.quantity * self.unit_proceeds


@dataclass(frozen=True, slots=True)
class RedLeagueSupplyPlan:
    """Exact pre-League liquidity and recovery reserve."""

    route: RoutePlan
    sales: tuple[RedLeagueSupplySale, ...]
    full_restores_purchased: int
    full_restore_unit_price: int = 3_000

    def __post_init__(self) -> None:
        if (
            type(self.full_restores_purchased) is not int  # noqa: E721
            or not 0 <= self.full_restores_purchased <= 1
            or self.full_restore_unit_price != 3_000
            or len({sale.item for sale in self.sales}) != len(self.sales)
        ):
            raise ValueError("League supply plan differs from its one-restore contract")

    @property
    def sale_proceeds(self) -> int:
        return sum(sale.proceeds for sale in self.sales)

    @property
    def purchase_cost(self) -> int:
        return self.full_restores_purchased * self.full_restore_unit_price


@dataclass(frozen=True, slots=True)
class RedLeagueFundingQualification:
    exit_plan: RoutePlan | None
    fly_town: int
    fly_landing: tuple[int, int]
    supply: RedLeagueSupplyPlan
    entry_plan: RoutePlan
    battles: tuple[RedLeagueBattleQuote, ...]
    supported_attack_pp: int
    opponent_attack_demands: int

    @property
    def expected_gross_income(self) -> int:
        return sum(battle.expected_money for battle in self.battles)

    @property
    def expected_net_income(self) -> int:
        return self.expected_gross_income + self.supply.sale_proceeds - self.supply.purchase_cost

    @property
    def maximum_campaign_full_restores(self) -> int:
        """One shared reserve may settle the first qualified mandatory need."""
        return max((battle.maximum_full_restores for battle in self.battles), default=0)

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.red.repeatable-league-funding-qualification.v3",
            "status": "ready_for_bounded_executor",
            "exit_steps": 0 if self.exit_plan is None else len(self.exit_plan.steps),
            "fly_town": self.fly_town,
            "supply_steps": len(self.supply.route.steps),
            "supply_sales": [
                {
                    "item_id": int(sale.item),
                    "quantity": sale.quantity,
                    "unit_proceeds": sale.unit_proceeds,
                    "proceeds": sale.proceeds,
                }
                for sale in self.supply.sales
            ],
            "sale_proceeds": self.supply.sale_proceeds,
            "full_restores_purchased": self.supply.full_restores_purchased,
            "purchase_cost": self.supply.purchase_cost,
            "entry_steps": len(self.entry_plan.steps),
            "battle_count": len(self.battles),
            "expected_gross_income": self.expected_gross_income,
            "expected_net_income": self.expected_net_income,
            "supported_attack_pp": self.supported_attack_pp,
            "opponent_attack_demands": self.opponent_attack_demands,
            "minimum_one_attack_allocation": True,
            "battles": [
                {
                    "objective_id": battle.objective_id,
                    "expected_money": battle.expected_money,
                    "maximum_opponent_level": battle.maximum_opponent_level,
                    "recovery_controller": battle.recovery_controller,
                    "maximum_full_restores": battle.maximum_full_restores,
                    "maximum_critical_exposures": battle.maximum_critical_exposures,
                }
                for battle in self.battles
            ],
            "controller_actions": 0,
            "emulator_frames": 0,
            "cumulative_recovery_reserved": self.maximum_campaign_full_restores,
            "recovery_allocation": "first-qualified-need-within-campaign-cap",
            "survival_proven": False,
            "net_profit_proven": False,
            "rematch_executed": False,
        }


_ROOMS = (
    ("defeat_lorelei", MapId.LORELEIS_ROOM, EventFlag.BEAT_LORELEI, False),
    ("defeat_bruno", MapId.BRUNOS_ROOM, EventFlag.BEAT_BRUNO, False),
    ("defeat_agatha", MapId.AGATHAS_ROOM, EventFlag.BEAT_AGATHA, False),
    (
        "defeat_lance",
        MapId.LANCES_ROOM,
        EventFlag.BEAT_LANCES_ROOM_TRAINER,
        True,
    ),
)
_INDIGO_TOWN = 9
_INDIGO_CLERK_AT = (5, 2)  # Traversal coordinates are (y, x).
_FULL_RESTORE_RESERVE = 1
# These three X items are repeatably purchasable in Celadon.  Sale prices are
# half of the source-backed purchase prices in data/items/prices.asm.  Unique
# key items, fossils, HMs and finite found TMs are deliberately ineligible.
_RENEWABLE_LIQUIDITY = (
    (ItemId.X_SPECIAL, 175),
    (ItemId.X_ACCURACY, 475),
    (ItemId.X_ATTACK, 250),
)


def _room_quote(
    rom: bytes,
    event_flags: bytes,
    objective_id: str,
    map_id: MapId,
    event_flag: EventFlag,
    allow_final_class: bool,
) -> TrainerPartyQuote:
    matches = tuple(
        zone
        for zone in static_trainer_sight_zones(
            trainer_headers(rom, {int(map_id)}, full_event_offsets=True),
            map_object_events(rom, {int(map_id)}),
            event_flags,
        )
        if zone.event_flag == event_flag
    )
    if len(matches) != 1 or matches[0].defeated:
        raise RedLeagueFundingError(f"{objective_id} is not one fresh cartridge battle")
    trainer = matches[0]
    return trainer_party_quote(
        rom,
        trainer.trainer_class,
        trainer.trainer_set,
        allow_final_class=allow_final_class,
    )


def _battle_quote(
    objective_id: str,
    quote: TrainerPartyQuote,
    *,
    recovery_controller: str,
    maximum_full_restores: int,
    maximum_critical_exposures: int = 0,
) -> RedLeagueBattleQuote:
    return RedLeagueBattleQuote(
        objective_id=objective_id,
        trainer_class=quote.opponent_id,
        trainer_set=quote.trainer_set,
        expected_money=quote.expected_victory_money,
        maximum_opponent_level=max(member.level for member in quote.party),
        recovery_controller=recovery_controller,
        maximum_full_restores=maximum_full_restores,
        maximum_critical_exposures=maximum_critical_exposures,
    )


def _plan_supply(
    money: int,
    bag_items: tuple[tuple[int, int], ...] | None,
    route: RoutePlan,
) -> RedLeagueSupplyPlan:
    """Fund one Champion restore without liquidating finite completion assets."""

    if bag_items is None or len({item for item, _ in bag_items}) != len(bag_items):
        raise RedLeagueFundingError("League funding lacks an exact bag")
    inventory = dict(bag_items)
    existing = inventory.get(int(ItemId.FULL_RESTORE), 0)
    purchase = max(0, _FULL_RESTORE_RESERVE - existing)
    cost = purchase * 3_000
    shortfall = max(0, cost - money)
    needs_slot = bool(
        purchase and int(ItemId.FULL_RESTORE) not in inventory and len(inventory) >= 20
    )
    sales: list[RedLeagueSupplySale] = []
    # Prefer whole renewable stacks: this also frees a bag slot for the restore.
    for item, unit_proceeds in _RENEWABLE_LIQUIDITY:
        quantity = inventory.get(int(item), 0)
        if shortfall <= 0 and not needs_slot:
            break
        if quantity:
            sale = RedLeagueSupplySale(item, quantity, unit_proceeds)
            sales.append(sale)
            shortfall -= sale.proceeds
            needs_slot = False
    if shortfall > 0:
        raise RedLeagueFundingError("renewable inventory cannot fund Champion recovery")
    projected_slots = len(inventory) - sum(
        inventory[int(sale.item)] == sale.quantity for sale in sales
    ) + (purchase > 0 and int(ItemId.FULL_RESTORE) not in inventory)
    if needs_slot or projected_slots > 20:
        raise RedLeagueFundingError("League recovery purchase lacks a bag slot")
    return RedLeagueSupplyPlan(route, tuple(sales), purchase)


def _require_party_coverage(party: PartyObservation, quotes: tuple[TrainerPartyQuote, ...]) -> None:
    if not party.members or any(member.hp <= 0 for member in party.members):
        raise RedLeagueFundingError("League funding requires a living restored party")
    for quote in quotes:
        try:
            plan_trainer_party(party, quote)
        except ValueError as error:
            raise RedLeagueFundingError("party lacks offensive coverage for the League") from error


def _minimum_attack_allocation(
    party: PartyObservation,
    quotes: tuple[TrainerPartyQuote, ...],
) -> tuple[int, int]:
    """Allocate one supported, non-immune PP unit to every League opponent.

    This is deliberately only a necessary floor.  It prevents independent
    matchup checks from reusing one last PP across an entire gauntlet, but it
    does not predict damage, misses or survival.
    """

    move_capacities: dict[tuple[int, int], int] = {}
    eligible_moves: dict[tuple[int, int], tuple[str, str]] = {}
    for member in party.members:
        for move_index, move in enumerate(member.moves):
            if not move.is_usable:
                continue
            ref = pokemon_red_move_ref(move.move_id)
            if not RED_BATTLE_CATALOG.recovery_attack_supported(ref):
                continue
            mechanics = RED_BATTLE_CATALOG.resolve_move(ref)
            key = (member.slot, move_index)
            move_capacities[key] = move.current_pp
            eligible_moves[key] = (ref, mechanics.type_name)

    demands: list[tuple[tuple[int, int], ...]] = []
    for quote in quotes:
        for opponent in quote.party:
            candidates = trainer_matchup_candidates(
                party,
                opponent_species=opponent.internal_species,
                opponent_level=opponent.level,
            )
            candidate_slots = {candidate.party_slot for candidate in candidates}
            opponent_types = RED_BATTLE_CATALOG.resolve_species(
                pokemon_red_species_ref(opponent.internal_species)
            ).types
            options = tuple(
                key
                for key, (_, move_type) in eligible_moves.items()
                if key[0] in candidate_slots
                and RED_BATTLE_CATALOG.type_effectiveness(move_type, opponent_types) > 0
            )
            if not options:
                raise RedLeagueFundingError(
                    "League opponent lacks a supported non-immune PP allocation"
                )
            demands.append(options)

    # Unit-demand bipartite max flow with move-slot PP as integer capacity.
    source: object = ("source", -1)
    sink: object = ("sink", -1)
    capacity: dict[tuple[object, object], int] = {}
    adjacency: dict[object, set[object]] = {}

    def edge(left: object, right: object, amount: int) -> None:
        capacity[(left, right)] = amount
        capacity.setdefault((right, left), 0)
        adjacency.setdefault(left, set()).add(right)
        adjacency.setdefault(right, set()).add(left)

    for key, amount in move_capacities.items():
        edge(source, ("move", key), amount)
    for index, options in enumerate(demands):
        demand = ("demand", index)
        edge(demand, sink, 1)
        for key in options:
            edge(("move", key), demand, 1)

    flow = 0
    while True:
        parent: dict[object, object | None] = {source: None}
        queue: list[object] = [source]
        for current in queue:
            for neighbor in adjacency.get(current, ()):
                if neighbor not in parent and capacity[(current, neighbor)] > 0:
                    parent[neighbor] = current
                    queue.append(neighbor)
                    if neighbor == sink:
                        break
            if sink in parent:
                break
        if sink not in parent:
            break
        cursor: object = sink
        while parent[cursor] is not None:
            previous = parent[cursor]
            assert previous is not None
            capacity[(previous, cursor)] -= 1
            capacity[(cursor, previous)] += 1
            cursor = previous
        flow += 1
    if flow != len(demands):
        raise RedLeagueFundingError(
            "party PP cannot allocate one supported attack to every League opponent"
        )
    return sum(move_capacities.values()), len(demands)


def qualify_red_league_funding(
    rom: bytes,
    observation: RedGoalObservation,
    reader: PokemonRedStateReader,
    world: StrategicScenarioRouteWorld,
) -> RedLeagueFundingQualification:
    """Prove a rematch-ready save, an exit, Fly access, entry, and five quotes."""

    raw = observation.raw
    if (
        raw.event_flags is None
        or raw.map_id is None
        or raw.player_y is None
        or raw.player_x is None
        or type(raw.player_money) is not int  # noqa: E721
        or not 0 <= raw.player_money <= 999_999
        or raw.battle_state != 0
        or not observation.input_ready
        or "story:victory_road_cleared" not in observation.game_state.facts
        or any(
            event_flag_is_set(raw.event_flags, flag)
            for flag in (
                EventFlag.BEAT_LORELEI,
                EventFlag.BEAT_BRUNO,
                EventFlag.BEAT_AGATHA,
                EventFlag.BEAT_LANCES_ROOM_TRAINER,
                EventFlag.BEAT_LANCE,
                EventFlag.BEAT_CHAMPION_RIVAL,
            )
        )
    ):
        raise RedLeagueFundingError("save is not at a fresh postgame League boundary")
    if not int(raw.badge_bits or 0) & int(Badge.THUNDER):
        raise RedLeagueFundingError("League funding requires observed Fly permission")
    try:
        fly_menu_indices(raw)
    except Gen1FieldMoveError as error:
        raise RedLeagueFundingError("party cannot currently execute Fly") from error
    destinations = reader.read_fly_destinations()
    landings = dict(red_fly_landings(rom))
    if _INDIGO_TOWN not in destinations or _INDIGO_TOWN not in landings:
        raise RedLeagueFundingError("Indigo Plateau is not an observed Fly destination")

    start = Gen1TraversalObserver(reader).observe()
    exit_plan: RoutePlan | None = None
    projected = start
    if start.map_id >= 0x25:
        if start.last_outside_map is None:
            raise RedLeagueFundingError("indoor League funding lacks an observed exit")
        try:
            exit_plan = world.plan_feasible_to_map(start, start.last_outside_map)
        except RoutePlanningError as error:
            raise RedLeagueFundingError("no bounded walking exit before Fly") from error
        if not exit_plan.steps or not _walking_plan(exit_plan):
            raise RedLeagueFundingError("League funding exit is not a bounded walk")
        projected = replace(
            start,
            map_id=exit_plan.terminal_map,
            at=exit_plan.terminal_at,
            last_outside_map=exit_plan.terminal_map,
            occupied=frozenset(),
        )
    if not 0 <= projected.map_id <= 0x24 or projected.map_id == 0x0B:
        raise RedLeagueFundingError("League funding did not reach a legal Fly origin")

    landing = landings[_INDIGO_TOWN]
    graph = world.local_graphs.get(_INDIGO_TOWN)
    if (
        graph is None
        or landing not in graph.edges
        or landing in world.object_blockers[_INDIGO_TOWN]
    ):
        raise RedLeagueFundingError("Indigo Fly landing is not a standable cartridge tile")
    indigo = replace(
        projected,
        map_id=_INDIGO_TOWN,
        at=landing,
        last_outside_map=_INDIGO_TOWN,
        occupied=world.object_blockers[_INDIGO_TOWN],
        hazards=(),
    )
    arrival = trainer_room_arrival(rom, int(MapId.LORELEIS_ROOM), raw.event_flags)
    entry_world = replace(
        world,
        macro_graph=with_scripted_trainer_arrival(world.macro_graph, arrival),
    )
    try:
        supply_route = world.plan_feasible_to_map(
            indigo, int(MapId.INDIGO_PLATEAU_LOBBY), goal_at=_INDIGO_CLERK_AT,
        )
    except RoutePlanningError as error:
        raise RedLeagueFundingError("no bounded route from Indigo landing to its clerk") from error
    if not supply_route.steps or not _walking_plan(supply_route):
        raise RedLeagueFundingError("Indigo supply route is not a bounded walk")
    supplied = replace(
        indigo,
        map_id=supply_route.terminal_map,
        at=supply_route.terminal_at,
        last_outside_map=_INDIGO_TOWN,
        occupied=world.object_blockers[supply_route.terminal_map],
    )
    supply = _plan_supply(raw.player_money, raw.bag_items, supply_route)
    try:
        entry = entry_world.plan_feasible_to_map(supplied, int(MapId.LORELEIS_ROOM))
    except RoutePlanningError as error:
        raise RedLeagueFundingError("no bounded route from Indigo landing to Lorelei") from error
    if not entry.steps or not _walking_plan(entry):
        raise RedLeagueFundingError("League entry is not a bounded walk")

    room_quotes = tuple(
        _room_quote(rom, raw.event_flags, objective, room, event, final_class)
        for objective, room, event, final_class in _ROOMS
    )
    champion = champion_script_binding(rom, reader.read_rival_starter())
    champion_quote = trainer_party_quote(
        rom, champion.opponent, champion.trainer_set, allow_final_class=True,
    )
    quotes = (*room_quotes, champion_quote)
    _require_party_coverage(observation.party, quotes)
    supported_attack_pp, opponent_attack_demands = _minimum_attack_allocation(
        observation.party, quotes,
    )
    objectives = (*[row[0] for row in _ROOMS], "defeat_champion")
    battles = tuple(
        _battle_quote(
            objective,
            quote,
            recovery_controller=(
                "bounded-critical-risk"
                if objective == "defeat_lance"
                else "ordinary-bounded-healing"
            ),
            maximum_full_restores=0 if objective == "defeat_lance" else 1,
            maximum_critical_exposures=2 if objective == "defeat_lance" else 0,
        )
        for index, (objective, quote) in enumerate(zip(objectives, quotes, strict=True))
    )
    if raw.player_money + supply.sale_proceeds - supply.purchase_cost < 0:
        raise RedLeagueFundingError("League supply plan is not affordable")
    if raw.player_money + supply.sale_proceeds - supply.purchase_cost + sum(
        battle.expected_money for battle in battles
    ) > 999_999:
        raise RedLeagueFundingError("save lacks money headroom for the quoted League gross")
    return RedLeagueFundingQualification(
        exit_plan, _INDIGO_TOWN, landing, supply, entry, battles,
        supported_attack_pp, opponent_attack_demands,
    )


__all__ = [
    "RedLeagueBattleQuote",
    "RedLeagueFundingError",
    "RedLeagueFundingQualification",
    "RedLeagueSupplyPlan",
    "RedLeagueSupplySale",
    "qualify_red_league_funding",
]
