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
from .gen1_trainer_parties import TrainerPartyQuote, trainer_party_quote
from .gen1_trainer_sight import static_trainer_sight_zones, trainer_headers
from .gen1_traversal import map_object_events
from .observation import Badge, EventFlag, MapId, PokemonRedStateReader, event_flag_is_set
from .party import PartyObservation
from .red_collection_fly import red_fly_landings
from .red_goal_manager import RedGoalObservation
from .red_resource_goal_router import _walking_plan
from .red_trainer_party import plan_trainer_party
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


@dataclass(frozen=True, slots=True)
class RedLeagueFundingQualification:
    exit_plan: RoutePlan | None
    fly_town: int
    fly_landing: tuple[int, int]
    entry_plan: RoutePlan
    battles: tuple[RedLeagueBattleQuote, ...]

    @property
    def expected_gross_income(self) -> int:
        return sum(battle.expected_money for battle in self.battles)

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.red.repeatable-league-funding-qualification.v1",
            "status": "ready_for_bounded_executor",
            "exit_steps": 0 if self.exit_plan is None else len(self.exit_plan.steps),
            "fly_town": self.fly_town,
            "entry_steps": len(self.entry_plan.steps),
            "battle_count": len(self.battles),
            "expected_gross_income": self.expected_gross_income,
            "battles": [
                {
                    "objective_id": battle.objective_id,
                    "expected_money": battle.expected_money,
                    "maximum_opponent_level": battle.maximum_opponent_level,
                }
                for battle in self.battles
            ],
            "controller_actions": 0,
            "emulator_frames": 0,
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


def _battle_quote(objective_id: str, quote: TrainerPartyQuote) -> RedLeagueBattleQuote:
    return RedLeagueBattleQuote(
        objective_id=objective_id,
        trainer_class=quote.opponent_id,
        trainer_set=quote.trainer_set,
        expected_money=quote.expected_victory_money,
        maximum_opponent_level=max(member.level for member in quote.party),
    )


def _require_party_coverage(party: PartyObservation, quotes: tuple[TrainerPartyQuote, ...]) -> None:
    if not party.members or any(member.hp <= 0 for member in party.members):
        raise RedLeagueFundingError("League funding requires a living restored party")
    for quote in quotes:
        try:
            plan_trainer_party(party, quote)
        except ValueError as error:
            raise RedLeagueFundingError("party lacks offensive coverage for the League") from error


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
    try:
        entry = world.plan_feasible_to_map(indigo, int(MapId.LORELEIS_ROOM))
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
    battles = tuple(
        _battle_quote(objective, quote)
        for objective, quote in zip(
            (*[row[0] for row in _ROOMS], "defeat_champion"), quotes, strict=True,
        )
    )
    return RedLeagueFundingQualification(exit_plan, _INDIGO_TOWN, landing, entry, battles)


__all__ = [
    "RedLeagueBattleQuote",
    "RedLeagueFundingError",
    "RedLeagueFundingQualification",
    "qualify_red_league_funding",
]
