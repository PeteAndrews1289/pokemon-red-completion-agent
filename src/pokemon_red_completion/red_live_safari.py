"""Action-free Safari discovery and one bounded live acquisition binding."""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import TypeGuard

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
    EventFlag,
    MapId,
    OverworldMovementMode,
    PokemonRedStateReader,
    RedSafariSessionState,
    event_flag_is_set,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_acquisition import (
    RED_ACQUISITION_CATALOG,
    RedAcquisitionCatalog,
    RedAreaExecutionPolicy,
    RedAreaExecutionReport,
    run_red_area_survey,
)
from pokemon_red_completion.red_collection import red_species_ref
from pokemon_red_completion.red_live_option_menu import (
    RedLiveSupplementalOption,
    supplemental_live_option,
)
from pokemon_red_completion.red_safari_acquisition import (
    SAFARI_ADMISSION_COST,
    LiveSafariAreaExecutor,
    LiveSafariPatrol,
    RedSafariGatePreparationReport,
    RedSafariPatrolPlan,
    RedSafariTransportReport,
    RedSafariZoneOffer,
    derive_red_safari_offer_patrol,
    enter_red_safari_area,
    enter_red_safari_area_from_gate,
    plan_red_safari_clerk_approach,
    prepare_red_safari_gate_origin,
    red_safari_admission_route,
    red_safari_area_menu,
    red_safari_zone_offers,
    relocate_red_safari_origin_to_fuchsia_center,
)
from pokemon_red_completion.strategic_navigation_scenario_runtime import (
    StrategicScenarioRouteWorld,
)


class RedSafariEntryMode(StrEnum):
    OUTDOOR_FLY = "outdoor_fly"
    GATE = "gate"


def _is_reader_ready(reader: PokemonRedStateReader) -> bool:
    read_input_readiness = getattr(reader, "read_input_readiness", None)
    if read_input_readiness is None or not read_input_readiness().ready:
        return False
    read_movement = getattr(reader, "read_overworld_movement_mode", None)
    if read_movement is None or read_movement() is not OverworldMovementMode.WALKING:
        return False
    read_dialogue = getattr(reader, "read_bottom_dialogue_box_visible", None)
    if read_dialogue is None or read_dialogue():
        return False
    read_trainer = getattr(reader, "read_pending_trainer_battle_identity", None)
    return read_trainer is not None and read_trainer() is None


def resolve_red_safari_entry_mode(
    reader: PokemonRedStateReader,
    world: StrategicScenarioRouteWorld | None = None,
    *,
    free_storage_slots: int = 1,
) -> RedSafariEntryMode | None:
    """Resolve the supported entry mode from semantic observations."""

    raw = reader.read()
    raw_map_id = getattr(raw, "map_id", None)
    if (
        raw_map_id is None
        or getattr(raw, "battle_state", None)
        or free_storage_slots <= 0
        or not _is_reader_ready(reader)
    ):
        return None

    if 0 <= raw_map_id <= 0x24 and raw_map_id not in {int(MapId.FUCHSIA_CITY), 0x0B}:
        if not int(raw.badge_bits or 0) & int(Badge.THUNDER):
            return None
        fly_destinations = getattr(reader, "read_fly_destinations", None)
        if fly_destinations is None or int(MapId.FUCHSIA_CITY) not in fly_destinations():
            return None
        try:
            fly_menu_indices(raw)
        except Gen1FieldMoveError:
            return None
        return RedSafariEntryMode.OUTDOOR_FLY

    if raw.map_id == int(MapId.SAFARI_ZONE_GATE):
        if raw.player_x not in {3, 4} or raw.player_y not in {2, 3, 4, 5}:
            return None
        if raw.event_flags is None or len(raw.event_flags) <= (int(EventFlag.IN_SAFARI_ZONE) // 8):
            return None
        if event_flag_is_set(raw.event_flags, int(EventFlag.IN_SAFARI_ZONE)):
            return None
        if event_flag_is_set(raw.event_flags, int(EventFlag.SAFARI_GAME_OVER)):
            return None

        read_session = getattr(reader, "read_safari_session_state", None)
        if not callable(read_session):
            return None
        try:
            session = read_session()
        except Exception:
            return None
        if not isinstance(session, RedSafariSessionState) or session.has_active_session:
            return None

        read_gate_script = getattr(reader, "read_safari_zone_gate_script", None)
        if not callable(read_gate_script):
            return None
        try:
            gate_script = read_gate_script()
        except Exception:
            return None
        if type(gate_script) is not int or gate_script != 0:
            return None

        if world is None:
            return None
        gate_graph = getattr(world, "local_graphs", {}).get(int(MapId.SAFARI_ZONE_GATE))
        gate_terrain = getattr(world, "terrain", {}).get(int(MapId.SAFARI_ZONE_GATE))
        if gate_graph is None or gate_terrain is None:
            return None
        start = (int(raw.player_y), int(raw.player_x))
        blockers = frozenset(
            getattr(world, "object_blockers", {}).get(int(MapId.SAFARI_ZONE_GATE), frozenset())
        )
        approach = plan_red_safari_clerk_approach(gate_graph, start, blockers)
        if approach is None:
            return None
        return RedSafariEntryMode.GATE

    return None


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
    """Action-free areas with either a legacy top binding or all area bindings."""

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
        if (
            len(self.supplements) not in {0, 1, len(self.areas)}
            or bool(self.areas) != bool(self.supplements)
            or len({s.binding.binding_ref for s in self.supplements}) != len(self.supplements)
        ):
            raise RedLiveSafariError("Safari inventory needs distinct aligned bindings")
        if any(s.binding.kind is not GoalKind.ACQUIRE_SPECIES for s in self.supplements):
            raise RedLiveSafariError("Safari binding must be an acquisition")

    def public_dict(self) -> dict[str, object]:
        return {
            "candidate_area_count": len(self.areas),
            "ranked_binding_count": len(self.supplements),
            "areas": [area.public_dict() for area in self.areas],
            "identity_fields_public": 0,
            "schema": "pokemon.red.live-safari-inventory.v1",
        }


def _is_valid_player_money(money: object) -> TypeGuard[int]:
    return (
        type(money) is int
        and not isinstance(money, bool)
        and 0 <= money <= 999_999
    )


def discover_eligible_red_safari_areas(
    rom: bytes,
    registered_species_numbers: Collection[int],
    *,
    free_storage_slots: int,
    world: StrategicScenarioRouteWorld,
    reader: PokemonRedStateReader,
) -> tuple[RedReachableSafariArea, ...]:
    """Inventory all productive areas satisfying non-money entry prerequisites."""

    mode = resolve_red_safari_entry_mode(
        reader,
        world,
        free_storage_slots=free_storage_slots,
    )
    if mode is None:
        return ()

    local_approach_steps = 0
    if mode is RedSafariEntryMode.GATE:
        raw = reader.read()
        if raw.player_x is None or raw.player_y is None:
            return ()
        start = (int(raw.player_y), int(raw.player_x))
        gate_graph = getattr(world, "local_graphs", {}).get(int(MapId.SAFARI_ZONE_GATE))
        if gate_graph is None:
            return ()
        blockers = frozenset(
            getattr(world, "object_blockers", {}).get(int(MapId.SAFARI_ZONE_GATE), frozenset())
        )
        approach = plan_red_safari_clerk_approach(gate_graph, start, blockers)
        if approach is None:
            return ()
        local_approach_steps = len(approach.edges)

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
                local_approach_steps
                + len(red_safari_admission_route(offer))
                + len(patrol.approach_directions),
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
    if not _is_valid_player_money(raw.player_money) or raw.player_money < SAFARI_ADMISSION_COST:
        return ()
    return discover_eligible_red_safari_areas(
        rom,
        registered_species_numbers,
        free_storage_slots=free_storage_slots,
        world=world,
        reader=reader,
    )


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
    expose_all_areas: bool = False,
    complete_paid_session: bool = False,
) -> RedLiveSafariInventory:
    """Build funded acquisition alternatives without controller input.

    Legacy callers retain their single ranked binding. Autonomous callers expose
    every genuinely distinct discovered area; each executes only its own patrol.
    """
    if type(expose_all_areas) is not bool:
        raise ValueError("Safari area exposure must be an explicit boolean")
    if type(complete_paid_session) is not bool:
        raise ValueError("Safari lifecycle must be an explicit boolean")

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
        candidates = red_safari_area_menu(
            context,
            tuple(area.offer for area in areas),
            route_steps=tuple(area.route_steps for area in areas),
            maximum_route_steps=maximum_route_steps,
            available_money=available_money,
            free_storage_slots=free_storage_slots,
        ).candidates
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
        candidates = (candidate,)
    mode = resolve_red_safari_entry_mode(
        reader, world, free_storage_slots=free_storage_slots
    )
    if mode is None:
        return RedLiveSafariInventory((), ())
    initial_raw = reader.read()
    bound_map_id = getattr(initial_raw, "map_id", None)
    initial_x = getattr(initial_raw, "player_x", None)
    initial_y = getattr(initial_raw, "player_y", None)
    bound_coords = (
        (int(initial_x), int(initial_y))
        if initial_x is not None and initial_y is not None
        else None
    )
    supplements = []
    for selected, candidate in zip(
        areas if expose_all_areas else areas[:1],
        candidates if expose_all_areas else candidates[:1],
        strict=True,
    ):
        binding = _live_safari_binding(
            area=selected,
            mode=mode,
            bound_map_id=bound_map_id,
            bound_coords=bound_coords,
            free_storage_slots=free_storage_slots,
            controller=controller,
            actions=actions,
            reader=reader,
            world=world,
            maximum_encounters=maximum_encounters,
            complete_paid_session=complete_paid_session,
        )
        supplements.append(supplemental_live_option(binding, candidate))
    return RedLiveSafariInventory(areas, tuple(supplements))


def _live_safari_binding(
    *,
    area: RedReachableSafariArea,
    mode: RedSafariEntryMode | None,
    bound_map_id: int | None = None,
    bound_coords: tuple[int, int] | None = None,
    free_storage_slots: int,
    controller: FrameBudgetController,
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    world: StrategicScenarioRouteWorld | None = None,
    maximum_encounters: int,
    maximum_search_actions: int | None = None,
    complete_paid_session: bool = False,
) -> ExecutableGoalBinding:
    if type(complete_paid_session) is not bool or (
        complete_paid_session and (world is None or maximum_search_actions is not None)
    ):
        raise ValueError("complete paid session requires native routing, not a training probe")
    if maximum_search_actions is not None and (
        type(maximum_search_actions) is not int or not 1 <= maximum_search_actions <= 256
    ):
        raise ValueError("explicit Safari search action bound differs")
    attempt: dict[str, object] = {}
    claimed = False

    if bound_map_id is None or bound_coords is None:
        construction_raw = reader.read()
        if bound_map_id is None:
            bound_map_id = getattr(construction_raw, "map_id", None)
        cx = getattr(construction_raw, "player_x", None)
        cy = getattr(construction_raw, "player_y", None)
        if bound_coords is None and cx is not None and cy is not None:
            bound_coords = (int(cx), int(cy))

    def execute() -> GoalExecutionReport:
        nonlocal claimed
        if claimed:
            raise RedLiveSafariError("live Safari binding was already consumed")
        claimed = True
        before_actions = actions.actions_executed
        before_frames = controller.frame_count

        if controller.pressed_buttons:
            raise RedLiveSafariError("Cannot execute Safari binding with pressed buttons")

        current_raw = reader.read()
        current_map_id = getattr(current_raw, "map_id", None)
        cur_x = getattr(current_raw, "player_x", None)
        cur_y = getattr(current_raw, "player_y", None)
        current_coords = (
            (int(cur_x), int(cur_y))
            if cur_x is not None and cur_y is not None
            else None
        )
        if bound_map_id is not None and current_map_id != bound_map_id:
            raise RedLiveSafariError(
                f"Player map ({current_map_id}) does not match bound origin map ({bound_map_id})",
            )
        if bound_coords is not None and current_coords != bound_coords:
            raise RedLiveSafariError(
                f"Player origin {current_coords} does not match bound origin {bound_coords}",
            )
        if (
            current_raw.player_money is None
            or current_raw.player_money < SAFARI_ADMISSION_COST
        ):
            raise RedLiveSafariError(
                f"Player funds ({current_raw.player_money}) "
                "insufficient for Safari admission (500)",
            )

        current_mode = resolve_red_safari_entry_mode(
            reader, world, free_storage_slots=free_storage_slots
        )
        if current_mode is None or current_mode is not mode:
            raise RedLiveSafariError(
                f"Current entry mode ({current_mode}) does not match bound mode ({mode})",
            )
        before_registered = frozenset(reader.read_pokedex_state().owned_species)
        catalog = _registered_safari_catalog(area, before_registered)
        transport: RedSafariTransportReport | RedSafariGatePreparationReport
        if current_mode is RedSafariEntryMode.OUTDOOR_FLY:
            transport = relocate_red_safari_origin_to_fuchsia_center(controller, actions, reader)
            admission = enter_red_safari_area(controller, actions, reader, area.offer)
        elif current_mode is RedSafariEntryMode.GATE:
            if world is None:
                raise RedLiveSafariError("Safari gate execution requires route world")
            transport = prepare_red_safari_gate_origin(controller, actions, reader, world)
            admission = enter_red_safari_area_from_gate(
                controller, actions, reader, area.offer, continuation=transport.continuation
            )
        else:
            raise RedLiveSafariError(f"Unsupported Safari entry mode: {current_mode}")
        patrol = LiveSafariPatrol(controller, actions, reader, area.patrol)
        patrol.enter()
        search_encounters = 0
        minimum_exit_steps = 0
        if complete_paid_session:
            from .red_paid_safari_departure import paid_search_step_reserve

            minimum_exit_steps = paid_search_step_reserve(controller, reader, world, area.patrol)

        def bounded_seek_step():
            nonlocal search_encounters
            patrol.seek_step()
            if reader.read().battle_state:
                search_encounters += 1

        port = LiveSafariAreaExecutor(
            controller,
            actions,
            reader,
            source_id=area.offer.source_id,
            map_id=area.offer.map_id,
            seek_step=(bounded_seek_step if maximum_search_actions is not None
                       or complete_paid_session else patrol.seek_step),
        )
        def search_resources():
            if not complete_paid_session:
                return port.safari_balls_available()
            session = reader.read_safari_session_state()
            # The area executor permits eight throws per encounter. Retain a
            # ball so the cartridge cannot auto-expel the player mid-capture.
            return (session.in_safari_zone and not session.safari_game_over
                    and session.safari_balls > 8 and session.safari_steps > minimum_exit_steps)

        survey = run_red_area_survey(
            area.offer.source_id,
            port,
            policy=RedAreaExecutionPolicy(
                max_actions=(2 * reader.read_safari_session_state().safari_steps
                             + 2 * maximum_encounters + 2 if complete_paid_session else
                             2 * maximum_encounters + 2
                             if maximum_search_actions is None else maximum_search_actions),
                max_encounters=maximum_encounters,
                capture_quota=1,
            ),
            catalog=catalog,
            capture_resources_available=search_resources,
            safety_check=(
                lambda: search_encounters < maximum_encounters or bool(reader.read().battle_state)
            ) if maximum_search_actions is not None or complete_paid_session else None,
        )
        departure = None
        if complete_paid_session:
            from .red_paid_safari_departure import exit_paid_search

            departure = exit_paid_search(controller, actions, reader, world)
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
                **({"paid_session_departure": departure,
                    "reserved_exit_steps": minimum_exit_steps,
                    "search_actions": survey.actions_executed,
                    "search_safety_stopped": survey.safety_stopped,
                    "search_resource_stopped": survey.capture_items_exhausted}
                   if complete_paid_session else {}),
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
                **({"complete_paid_session": True} if complete_paid_session else {}),
                **({"maximum_search_actions": maximum_search_actions}
                   if maximum_search_actions is not None else {}),
            }
        ),
        kind=GoalKind.ACQUIRE_SPECIES,
        search_source_ref=f"pokemon.red:paid-safari:{area.offer.source_id}",
        search_objective_sha256=canonical_sha256({
            "schema": "pokemon.red.safari-remaining-targets.v1",
            "missing_species": sorted(set(area.offer.missing_species_numbers)),
        }),
        estimated_effort=min(1.0, 0.2 + area.route_steps / 1_000),
        estimated_risk=0.1,
        execute=execute,
        verify=verify,
    )


def _registered_safari_catalog(
    area: RedReachableSafariArea,
    registered_species_numbers: Collection[int],
) -> RedAcquisitionCatalog:
    """Restrict one live survey to the registration targets its offer promised."""

    return replace(
        RED_ACQUISITION_CATALOG,
        remaining_demand=True,
        registered_species=frozenset(
            red_species_ref(number) for number in registered_species_numbers
        ),
        wild_source_species=(
            (
                area.offer.source_id,
                tuple(red_species_ref(number) for number in area.offer.missing_species_numbers),
            ),
        ),
    )


def quote_red_safari_funding(
    rom: bytes,
    registered_species_numbers: Collection[int],
    *,
    free_storage_slots: int,
    world: StrategicScenarioRouteWorld,
    reader: PokemonRedStateReader,
):
    """Quote one paid Safari entry if non-money eligibility is satisfied."""
    from .red_safari_funding_budget import quote_red_safari_funding as _quote

    return _quote(
        rom,
        registered_species_numbers,
        free_storage_slots=free_storage_slots,
        world=world,
        reader=reader,
    )


__all__ = [
    "RedLiveSafariError",
    "RedLiveSafariInventory",
    "RedReachableSafariArea",
    "RedSafariEntryMode",
    "build_red_live_safari_inventory",
    "discover_eligible_red_safari_areas",
    "discover_reachable_red_safari_areas",
    "quote_red_safari_funding",
    "resolve_red_safari_entry_mode",
]
