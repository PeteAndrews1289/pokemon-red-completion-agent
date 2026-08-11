"""Pokémon Red/Blue adapters for the game-neutral route executor."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from pokemon_red_completion.gen1_repel import gen1_repel_resource
from pokemon_red_completion.gen1_story_routing import gen1_story_capabilities
from pokemon_red_completion.observation import MapId, PokemonRedStateReader, RawGameState
from pokemon_red_completion.route_1_wild import Route1WildFleeEvidence, flee_wild
from pokemon_red_completion.route_executor import (
    InterruptionReceipt,
    RouteActionPort,
    RouteExecutionError,
    TraversalHazard,
    TraversalSnapshot,
)


class Gen1HazardProjector(Protocol):
    def observe_hazards(self, raw: RawGameState) -> tuple[TraversalHazard, ...]: ...


@dataclass(slots=True)
class Gen1TraversalObserver:
    """Project revision-decoded Red/Blue state into portable traversal state."""

    reader: PokemonRedStateReader
    hazard_projector: Gen1HazardProjector | None = None

    def observe(self) -> TraversalSnapshot:
        raw = self.reader.read()
        if (
            not raw.game_started
            or raw.map_id is None
            or raw.player_y is None
            or raw.player_x is None
            or raw.battle_state is None
        ):
            raise RouteExecutionError("Gen I traversal state is unavailable")
        interruption = _interruption_kind(raw.battle_state)
        if interruption is None and self.reader.trainer_engagement_active():
            interruption = "trainer_engagement"
        movement_mode = self.reader.read_overworld_movement_mode()
        occupied = (
            frozenset()
            if interruption is not None
            else self.reader.read_visible_object_coordinates()
        )
        hazards = (
            ()
            if interruption is not None or self.hazard_projector is None
            else self.hazard_projector.observe_hazards(raw)
        )
        return TraversalSnapshot(
            map_id=raw.map_id,
            at=(raw.player_y, raw.player_x),
            ready=(interruption is None and self.reader.read_input_readiness().ready),
            interruption=interruption,
            mode=movement_mode.traversal_mode,
            occupied=occupied,
            hazards=hazards,
            capabilities=gen1_story_capabilities(raw),
            resources=(gen1_repel_resource(raw),),
        )


@dataclass(slots=True)
class Gen1WildFleeHandler:
    """Restore the exact overworld boundary after a bounded wild encounter."""

    executor: RouteActionPort
    reader: PokemonRedStateReader
    maximum_flees: int
    stabilization_frames: int
    route_name: str = "cartridge-composed route"
    evidence: list[Route1WildFleeEvidence] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        if type(self.maximum_flees) is not int or self.maximum_flees < 0:  # noqa: E721
            raise ValueError("maximum_flees must be a non-negative integer")
        if type(self.stabilization_frames) is not int or self.stabilization_frames <= 0:  # noqa: E721
            raise ValueError("stabilization_frames must be a positive integer")
        if not self.route_name:
            raise ValueError("a route name is required")

    def handle(self, interruption: TraversalSnapshot) -> InterruptionReceipt:
        if interruption.interruption != "wild_battle":
            raise RouteExecutionError(f"Gen I route cannot dismiss {interruption.interruption!r}")
        if len(self.evidence) >= self.maximum_flees:
            raise RouteExecutionError(
                f"{self.route_name} exceeded its {self.maximum_flees}-flee budget"
            )
        encounter = self.reader.read()
        if (
            encounter.map_id != interruption.map_id
            or (encounter.player_y, encounter.player_x) != interruption.at
        ):
            raise RouteExecutionError("wild interruption drifted before recovery")
        try:
            expected_map = MapId(interruption.map_id)
        except ValueError as error:
            raise RouteExecutionError(f"unsupported Gen I map id {interruption.map_id}") from error
        receipt = flee_wild(
            self.executor,
            self.reader,
            encounter,
            expected_map_id=expected_map,
            route_name=self.route_name,
            stabilization_frames=self.stabilization_frames,
            error_type=RouteExecutionError,
        )
        self.evidence.append(receipt)
        return InterruptionReceipt(
            kind="wild_battle",
            resumed_map=receipt.map_id,
            resumed_at=(receipt.player_y, receipt.player_x),
            details=receipt.public_dict(),
        )


def _interruption_kind(battle_state: int) -> str | None:
    if battle_state == 0:
        return None
    if battle_state == 1:
        return "wild_battle"
    return f"battle:{battle_state}"
