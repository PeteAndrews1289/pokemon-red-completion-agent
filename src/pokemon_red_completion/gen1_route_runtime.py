"""Pokémon Red/Blue adapters for the game-neutral route executor."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.battle_runtime import (
    BattleIntent,
    BattleRuntimeError,
    MoveSlotPolicy,
    run_adaptive_trainer_battle,
)
from pokemon_red_completion.battle_semantics import STAB_MULTIPLIER
from pokemon_red_completion.gen1_repel import gen1_repel_resource
from pokemon_red_completion.gen1_story_routing import gen1_story_capabilities
from pokemon_red_completion.observation import MapId, PokemonRedStateReader, RawGameState
from pokemon_red_completion.red_battle_catalog import (
    PokemonRedBattleCatalog,
    pokemon_red_move_ref,
    pokemon_red_species_ref,
)
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
    capability_projector: Callable[[RawGameState], frozenset[str]] | None = None

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
        projected_capabilities = (
            self.capability_projector(raw)
            if self.capability_projector is not None
            else frozenset()
        )
        if not isinstance(projected_capabilities, frozenset) or any(
            not isinstance(item, str) or not item for item in projected_capabilities
        ):
            raise RouteExecutionError(
                "Gen I capability projector returned an invalid capability set"
            )
        return TraversalSnapshot(
            map_id=raw.map_id,
            at=(raw.player_y, raw.player_x),
            ready=(interruption is None and self.reader.read_input_readiness().ready),
            interruption=interruption,
            mode=movement_mode.traversal_mode,
            occupied=occupied,
            hazards=hazards,
            capabilities=gen1_story_capabilities(raw).union(projected_capabilities),
            resources=(gen1_repel_resource(raw),),
            last_outside_map=self.reader.read_retained_outside_map(),
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


_BATTLE_CATALOG = PokemonRedBattleCatalog()


def strongest_usable_move_slot(raw: RawGameState) -> int:
    """Choose a damaging move from live mechanics, without chapter identity."""

    moves = raw.battler_moves
    pp = raw.battler_pp
    attacker_id = raw.active_party_species_id
    if attacker_id is None and raw.party_species_ids:
        index = raw.active_party_index or 0
        if 0 <= index < len(raw.party_species_ids):
            attacker_id = raw.party_species_ids[index]
    if moves is None or pp is None or attacker_id is None or raw.enemy_species_id is None:
        raise RouteExecutionError("route battle lacks mechanics-ranked move evidence")

    attacker = _BATTLE_CATALOG.resolve_species(pokemon_red_species_ref(attacker_id))
    defender = _BATTLE_CATALOG.resolve_species(pokemon_red_species_ref(raw.enemy_species_id))
    usable: list[tuple[tuple[bool, float, float, int, int, int], int]] = []
    for index, (move_id, packed_pp) in enumerate(zip(moves, pp, strict=False)):
        slot = index + 1
        current_pp = packed_pp & 0x3F
        if (
            move_id == 0
            or current_pp == 0
            or (raw.player_disabled_move_slot == slot and (raw.player_disable_turns or 0) > 0)
        ):
            continue
        move = _BATTLE_CATALOG.resolve_move(pokemon_red_move_ref(move_id))
        damaging = move.category != "status" and move.power > 0
        effectiveness = _BATTLE_CATALOG.type_effectiveness(
            move.type_name,
            defender.types,
        )
        stab = STAB_MULTIPLIER if move.type_name in attacker.types else 1.0
        usable.append(
            (
                (
                    damaging,
                    move.power * move.accuracy * effectiveness * stab,
                    effectiveness,
                    move.power,
                    current_pp,
                    -slot,
                ),
                slot,
            )
        )
    if not usable:
        raise RouteExecutionError("route battle has no usable move")
    return max(usable)[1]


@dataclass(slots=True)
class Gen1RouteInterruptionHandler:
    """Resolve wild encounters and unavoidable trainer battles in one route."""

    executor: RouteActionPort
    reader: PokemonRedStateReader
    maximum_flees: int
    maximum_trainer_battles: int
    stabilization_frames: int
    route_name: str = "cartridge-composed route"
    max_trainer_intro_pulses: int = 32
    move_slot_policy: MoveSlotPolicy = strongest_usable_move_slot
    handled_hazard_kinds: frozenset[str] = field(
        default=frozenset({"trainer_sight"}),
        init=False,
    )
    trainer_evidence: list[InterruptionReceipt] = field(default_factory=list, init=False)
    _wild: Gen1WildFleeHandler = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if type(self.maximum_trainer_battles) is not int or self.maximum_trainer_battles < 0:  # noqa: E721
            raise ValueError("maximum_trainer_battles must be a non-negative integer")
        if type(self.max_trainer_intro_pulses) is not int or self.max_trainer_intro_pulses <= 0:  # noqa: E721
            raise ValueError("max_trainer_intro_pulses must be a positive integer")
        if not callable(self.move_slot_policy):
            raise TypeError("move_slot_policy must be callable")
        self._wild = Gen1WildFleeHandler(
            self.executor,
            self.reader,
            maximum_flees=self.maximum_flees,
            stabilization_frames=self.stabilization_frames,
            route_name=self.route_name,
        )

    @property
    def wild_evidence(self) -> tuple[Route1WildFleeEvidence, ...]:
        return tuple(self._wild.evidence)

    def handle(self, interruption: TraversalSnapshot) -> InterruptionReceipt:
        if interruption.interruption == "wild_battle":
            return self._wild.handle(interruption)
        if interruption.interruption not in {"trainer_engagement", "battle:2"}:
            raise RouteExecutionError(f"Gen I route cannot dismiss {interruption.interruption!r}")
        if len(self.trainer_evidence) >= self.maximum_trainer_battles:
            raise RouteExecutionError(
                f"{self.route_name} exceeded its {self.maximum_trainer_battles}-trainer budget"
            )

        initial = self.reader.read()
        if (
            initial.map_id != interruption.map_id
            or (
                initial.player_y,
                initial.player_x,
            )
            != interruption.at
        ):
            raise RouteExecutionError("trainer interruption drifted before recovery")
        intro_pulses = 0
        active = initial
        while active.battle_state != 2:
            if active.battle_state == 1:
                raise RouteExecutionError("wild battle replaced a trainer engagement")
            if active.battle_state not in {0, None}:
                raise RouteExecutionError(
                    f"trainer engagement exposed battle state {active.battle_state!r}"
                )
            if intro_pulses >= self.max_trainer_intro_pulses:
                raise RouteExecutionError("trainer engagement exceeded its intro budget")
            self.executor.execute(MacroAction(MacroActionKind.CONFIRM))
            intro_pulses += 1
            active = self.reader.read()

            if (
                active.battle_state == 0
                and not self.reader.trainer_engagement_active()
                and self.reader.read_input_readiness().ready
            ):
                receipt = InterruptionReceipt(
                    kind="trainer_engagement",
                    resumed_map=interruption.map_id,
                    resumed_at=interruption.at,
                    details={
                        "battle_started": False,
                        "intro_pulses": intro_pulses,
                        "verified": True,
                    },
                )
                self.trainer_evidence.append(receipt)
                return receipt

        ordinal = len(self.trainer_evidence) + 1
        battle_plan_id = f"generated-route-map-{interruption.map_id}-trainer-{ordinal}"
        try:
            final = run_adaptive_trainer_battle(
                self.reader,
                self.executor,
                self.move_slot_policy,
                expected_map=interruption.map_id,
                intent=BattleIntent(
                    objective_id="route_traversal",
                    battle_plan_id=battle_plan_id,
                ),
                label=f"{self.route_name} trainer {ordinal}",
                consume_battle_start_schedule=False,
            )
        except BattleRuntimeError as error:
            raise RouteExecutionError(str(error)) from error
        if (
            final.battle_state != 0
            or final.map_id != interruption.map_id
            or (final.player_y, final.player_x) != interruption.at
            or not self.reader.read_input_readiness().ready
        ):
            raise RouteExecutionError("trainer battle failed to restore its route boundary")
        receipt = InterruptionReceipt(
            kind="trainer_engagement",
            resumed_map=interruption.map_id,
            resumed_at=interruption.at,
            details={
                "battle_plan_id": battle_plan_id,
                "battle_started": True,
                "intro_pulses": intro_pulses,
                "verified": True,
            },
        )
        self.trainer_evidence.append(receipt)
        return receipt


def _interruption_kind(battle_state: int) -> str | None:
    if battle_state == 0:
        return None
    if battle_state == 1:
        return "wild_battle"
    return f"battle:{battle_state}"
