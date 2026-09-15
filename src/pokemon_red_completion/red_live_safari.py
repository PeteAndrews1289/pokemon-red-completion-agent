"""Action-free Safari discovery and one bounded live acquisition binding."""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass

from pokemon_red_completion.executor import CountingExecutor, FrameBudgetController
from pokemon_red_completion.gen1_field_moves import Gen1FieldMoveError, fly_menu_indices
from pokemon_red_completion.goal_manager import GoalFailureReason, GoalKind
from pokemon_red_completion.goal_manager_runtime import (
    ExecutableGoalBinding,
    GoalExecutionReport,
    GoalVerification,
)
from pokemon_red_completion.living_dex_option_value import (
    LivingDexOptionAvailability,
    LivingDexOptionCandidate,
    LivingDexOptionContext,
    LivingDexOptionFeatures,
    LivingDexOptionKind,
)
from pokemon_red_completion.observation import (
    Badge,
    MapId,
    OverworldMovementMode,
    PokemonRedStateReader,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_acquisition import (
    RED_ACQUISITION_CATALOG,
    RedAreaExecutionPolicy,
    RedAreaExecutionReport,
    run_red_area_survey,
)
from pokemon_red_completion.red_live_option_menu import (
    RedLiveSupplementalOption,
    supplemental_live_option,
)
from pokemon_red_completion.red_safari_acquisition import (
    SAFARI_ADMISSION_COST,
    LiveSafariAreaExecutor,
    LiveSafariPatrol,
    RedSafariPatrolPlan,
    RedSafariZoneOffer,
    derive_red_safari_offer_patrol,
    enter_red_safari_area,
    red_safari_admission_route,
    red_safari_area_menu,
    red_safari_zone_offers,
    relocate_red_safari_origin_to_fuchsia_center,
)
from pokemon_red_completion.strategic_navigation_scenario_runtime import (
    StrategicScenarioRouteWorld,
)


class RedLiveSafariError(RuntimeError):
    """Safari inventory or execution crossed its observed boundary."""


@dataclass(frozen=True, slots=True)
class RedReachableSafariArea:
    """One cartridge offer with a pre-input derived patrol."""

    offer: RedSafariZoneOffer
    patrol: RedSafariPatrolPlan
    route_steps: int

    def __post_init__(self) -> None:
        if not isinstance(self.offer, RedSafariZoneOffer) or not isinstance(
            self.patrol, RedSafariPatrolPlan
        ):
            raise TypeError("reachable Safari area needs an offer and patrol")
        if self.patrol.source_id != self.offer.source_id:
            raise RedLiveSafariError("Safari patrol differs from its offer")
        if type(self.route_steps) is not int or self.route_steps < 0:
            raise ValueError("Safari route steps must be non-negative")

    def public_dict(self) -> dict[str, object]:
        return {
            "cartridge_derived": True,
            "feature_values": self.offer.policy_features(),
            "patrol": self.patrol.public_dict(),
            "route_steps": self.route_steps,
            "private_map_fields": 0,
            "private_path_fields": 0,
            "private_species_fields": 0,
        }


@dataclass(frozen=True, slots=True)
class RedLiveSafariInventory:
    """All action-free areas plus the single ranked top-level binding."""

    areas: tuple[RedReachableSafariArea, ...]
    supplements: tuple[RedLiveSupplementalOption, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.areas, tuple) or any(
            not isinstance(area, RedReachableSafariArea) for area in self.areas
        ):
            raise TypeError("live Safari areas must be immutable")
        if not isinstance(self.supplements, tuple) or any(
            not isinstance(option, RedLiveSupplementalOption) for option in self.supplements
        ):
            raise TypeError("live Safari supplements must be immutable")
        if len(self.supplements) not in {0, 1} or bool(self.areas) != bool(self.supplements):
            raise RedLiveSafariError("Safari inventory needs at most one ranked binding")
        if self.supplements and self.supplements[0].binding.kind is not GoalKind.ACQUIRE_SPECIES:
            raise RedLiveSafariError("Safari binding must be an acquisition")

    def public_dict(self) -> dict[str, object]:
        return {
            "candidate_area_count": len(self.areas),
            "ranked_binding_count": len(self.supplements),
            "areas": [area.public_dict() for area in self.areas],
            "identity_fields_public": 0,
            "schema": "pokemon.red.live-safari-inventory.v1",
        }


def discover_reachable_red_safari_areas(
    rom: bytes,
    registered_species_numbers: Collection[int],
    *,
    free_storage_slots: int,
    world: StrategicScenarioRouteWorld,
    reader: PokemonRedStateReader,
) -> tuple[RedReachableSafariArea, ...]:
    """Inventory all productive areas only when one admission is executable."""

    raw = reader.read()
    if (
        raw.map_id is None
        or not 0 <= raw.map_id <= 0x24
        or raw.map_id in {int(MapId.FUCHSIA_CITY), 0x0B}
        or raw.battle_state
        or raw.player_money is None
        or raw.player_money < SAFARI_ADMISSION_COST
        or free_storage_slots <= 0
        or not reader.read_input_readiness().ready
        or reader.read_overworld_movement_mode() is not OverworldMovementMode.WALKING
        or reader.read_bottom_dialogue_box_visible()
        or reader.read_pending_trainer_battle_identity() is not None
        or not int(raw.badge_bits or 0) & int(Badge.THUNDER)
        or int(MapId.FUCHSIA_CITY) not in reader.read_fly_destinations()
    ):
        return ()
    try:
        fly_menu_indices(raw)
    except Gen1FieldMoveError:
        return ()
    areas: list[RedReachableSafariArea] = []
    for offer in red_safari_zone_offers(rom, registered_species_numbers):
        terrain = world.terrain.get(offer.map_id)
        graph = world.local_graphs.get(offer.map_id)
        if terrain is None or graph is None:
            continue
        try:
            patrol = derive_red_safari_offer_patrol(
                offer,
                terrain,
                graph,
                excluded=(
                    frozenset(world.object_blockers.get(offer.map_id, frozenset()))
                    | frozenset(world.macro_graph.warp_locations.get(offer.map_id, ()))
                ),
            )
        except ValueError:
            continue
        areas.append(
            RedReachableSafariArea(
                offer,
                patrol,
                len(red_safari_admission_route(offer)) + len(patrol.approach_directions),
            )
        )
    areas.sort(
        key=lambda area: (
            -area.offer.productive_slot_count,
            area.route_steps,
            -len(area.offer.missing_species_numbers),
            area.offer.source_id,
        )
    )
    return tuple(areas)


def build_red_live_safari_inventory(
    rom: bytes,
    registered_species_numbers: Collection[int],
    context: LivingDexOptionContext,
    *,
    free_storage_slots: int,
    world: StrategicScenarioRouteWorld,
    controller: FrameBudgetController,
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    maximum_encounters: int = 32,
) -> RedLiveSafariInventory:
    """Build one ranked Safari acquisition without controller input."""

    areas = discover_reachable_red_safari_areas(
        rom,
        registered_species_numbers,
        free_storage_slots=free_storage_slots,
        world=world,
        reader=reader,
    )
    if not areas:
        return RedLiveSafariInventory((), ())
    maximum_route_steps = max(1, max(area.route_steps for area in areas))
    available_money = int(reader.read().player_money or 0)
    if len(areas) >= 2:
        candidate = red_safari_area_menu(
            context,
            tuple(area.offer for area in areas),
            route_steps=tuple(area.route_steps for area in areas),
            maximum_route_steps=maximum_route_steps,
            available_money=available_money,
            free_storage_slots=free_storage_slots,
        ).candidates[0]
    else:
        offer = areas[0].offer
        candidate = LivingDexOptionCandidate(
            binding_ref="safari-area-private-0",
            features=LivingDexOptionFeatures(
                kind=LivingDexOptionKind.ACQUIRE,
                completion_gain=min(1.0, len(offer.missing_species_numbers) / 6.0),
                dependency_unlock_gain=0.0,
                travel_effort=areas[0].route_steps / maximum_route_steps,
                execution_effort=1.0 - offer.productive_slot_count / len(offer.slots),
                resource_cost=min(1.0, SAFARI_ADMISSION_COST / available_money),
                storage_cost=min(1.0, 1.0 / free_storage_slots),
                party_risk=0.0,
                irreversibility_risk=0.0,
                uncertainty=1.0 - offer.productive_slot_count / len(offer.slots),
            ),
            availability=LivingDexOptionAvailability.AVAILABLE,
        )
    selected = areas[0]
    binding = _live_safari_binding(
        area=selected,
        controller=controller,
        actions=actions,
        reader=reader,
        maximum_encounters=maximum_encounters,
    )
    return RedLiveSafariInventory(
        areas,
        (supplemental_live_option(binding, candidate),),
    )


def _live_safari_binding(
    *,
    area: RedReachableSafariArea,
    controller: FrameBudgetController,
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    maximum_encounters: int,
) -> ExecutableGoalBinding:
    attempt: dict[str, object] = {}
    claimed = False

    def execute() -> GoalExecutionReport:
        nonlocal claimed
        if claimed:
            raise RedLiveSafariError("live Safari binding was already consumed")
        claimed = True
        before_actions = actions.actions_executed
        before_frames = controller.frame_count
        before_registered = frozenset(reader.read_pokedex_state().owned_species)
        transport = relocate_red_safari_origin_to_fuchsia_center(controller, actions, reader)
        admission = enter_red_safari_area(controller, actions, reader, area.offer)
        patrol = LiveSafariPatrol(controller, actions, reader, area.patrol)
        patrol.enter()
        port = LiveSafariAreaExecutor(
            controller,
            actions,
            reader,
            source_id=area.offer.source_id,
            map_id=area.offer.map_id,
            seek_step=patrol.seek_step,
        )
        survey = run_red_area_survey(
            area.offer.source_id,
            port,
            policy=RedAreaExecutionPolicy(
                max_actions=2 * maximum_encounters + 2,
                max_encounters=maximum_encounters,
                capture_quota=1,
            ),
            catalog=RED_ACQUISITION_CATALOG,
            capture_resources_available=port.safari_balls_available,
        )
        after_registered = frozenset(reader.read_pokedex_state().owned_species)
        attempt.update(
            before_registered=before_registered,
            after_registered=after_registered,
            survey=survey,
        )
        return GoalExecutionReport(
            actions.actions_executed - before_actions,
            controller.frame_count - before_frames,
            {
                "transport": transport.public_dict(),
                "admission": admission.public_dict(),
                "patrol": area.patrol.public_dict(),
                "encounters_seen": survey.encounters_seen,
                "captures": survey.captures,
                "flees": survey.flees,
                "search_exhausted": survey.search_exhausted,
            },
        )

    def verify(_report: GoalExecutionReport) -> GoalVerification:
        before = attempt.get("before_registered")
        after = attempt.get("after_registered")
        survey = attempt.get("survey")
        if (
            not isinstance(before, frozenset)
            or not isinstance(after, frozenset)
            or not isinstance(survey, RedAreaExecutionReport)
            or not before <= after
            or len(after - before) != survey.captures
            or controller.pressed_buttons
        ):
            return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        if survey.captures == 1:
            return GoalVerification.succeeded()
        return GoalVerification.failed(GoalFailureReason.SEARCH_EXHAUSTED)

    return ExecutableGoalBinding(
        binding_ref="pokemon.red:safari-live:"
        + canonical_sha256(
            {
                "source": area.offer.source_id,
                "missing": area.offer.missing_species_numbers,
                "patrol": area.patrol.public_dict(),
                "maximum_encounters": maximum_encounters,
            }
        ),
        kind=GoalKind.ACQUIRE_SPECIES,
        estimated_effort=min(1.0, 0.2 + area.route_steps / 1_000),
        estimated_risk=0.1,
        execute=execute,
        verify=verify,
    )


__all__ = [
    "RedLiveSafariError",
    "RedLiveSafariInventory",
    "RedReachableSafariArea",
    "build_red_live_safari_inventory",
    "discover_reachable_red_safari_areas",
]
