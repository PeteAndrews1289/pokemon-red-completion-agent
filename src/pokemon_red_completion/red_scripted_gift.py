"""Opt-in one-shot gift acquisition, with native prerequisites and accounting.

First supported boundary: the liberated Silph worker. Species/level and object
location come from the cartridge, not policy features. This does not authorize
story completion, a forced target, automatic storage changes or battle fallback.
Script semantics: pret/pokered 1e96034092686d006e863cace09e87273051a3d8,
scripts/SilphCo7F.asm and engine/events/give_pokemon.asm.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from functools import partial

from .actions import MacroAction, MacroActionKind
from .collection import CollectionLocation
from .gen1_acquisition import direct_gifts, map_objects
from .gen1_cartridge import CartridgeReadError
from .gen1_field_moves import Gen1FieldMoveError, Gen1FieldMovePort, fly_menu_indices
from .gen1_route_runtime import Gen1TraversalObserver
from .goal_manager import GoalFailureReason, GoalKind
from .goal_manager_runtime import ExecutableGoalBinding, GoalExecutionReport, GoalVerification
from .observation import Badge, EventFlag, MapId, OverworldMovementMode, event_flag_is_set
from .red_collection import red_species_ref
from .red_collection_fly import red_fly_landings
from .red_party import PokemonRedPartyReader
from .red_resource_goal_router import _supported_plan, collection_field_capabilities
from .route_executor import execute_route
from .route_plan import RoutePlanningError


class RedScriptedGiftError(RuntimeError):
    """The selected gift cannot be executed or verified under its contract."""


@dataclass(frozen=True, slots=True)
class RedScriptedGift:
    species: int
    level: int
    map_id: int
    sprite_index: int
    picture_id: int
    at: tuple[int, int]

    def __post_init__(self):
        if not 1 <= self.species <= 151 or not 1 <= self.level <= 100:
            raise ValueError("gift species or level differs")

    @property
    def species_ref(self):
        return red_species_ref(self.species)


def silph_gift(rom: bytes) -> RedScriptedGift:
    """Reject incompatible scripts/objects rather than guess a gift identity."""
    gift = direct_gifts(rom)[1]
    # Validate the flag test preceding the already-validated GivePokemon call.
    # text_asm; ld a,[wStatusFlags4]; bit 0,a; jr z,+15.
    if rom[0x51D8E:0x51D96] != bytes.fromhex("08 fa 2e d7 cb 47 28 0f") or rom[
        0x51DC3:0x51DC8
    ] != bytes.fromhex("21 2e d7 cb c6"):
        raise CartridgeReadError("Silph gift flag script differs")
    objects = map_objects(rom)[int(MapId.SILPH_CO_7F)]
    obj = objects[0]
    if obj.text_and_kind != 1 or obj.movement != 0xFF or obj.sprite != 0x2C:
        raise CartridgeReadError("Silph gift worker object differs")
    return RedScriptedGift(gift.species, gift.level, obj.map_id, 1, obj.sprite, (obj.y, obj.x))


def gift_available(reader, observation, gift: RedScriptedGift) -> bool:
    raw = observation.raw
    return bool(
        raw.game_started
        and raw.battle_state == 0
        and observation.input_ready
        and raw.event_flags is not None
        and event_flag_is_set(raw.event_flags, int(EventFlag.BEAT_SILPH_CO_GIOVANNI))
        # Being inside the gift room needs no access-door assumption. Outside
        # that floor, the supported corridor requires its actual unlocked flag.
        and (raw.map_id == gift.map_id or event_flag_is_set(
            raw.event_flags, int(EventFlag.SILPH_CO_3_UNLOCKED_DOOR_2)
        ))
        and not reader.read_silph_gift_received()
        and gift.species_ref not in observation.collection_observation.owned_species
        and raw.party_count is not None
        and 1 <= raw.party_count <= 6
        and (raw.party_count < 6 or len(reader.read_current_box_state().species_ids) < 20)
        and not reader.read_safari_session_state().has_active_session
        and reader.read_overworld_movement_mode() is OverworldMovementMode.WALKING
        and not reader.read_bottom_dialogue_box_visible()
        and reader.read_pending_trainer_battle_identity() is None
        and reader.read_fly_menu_state() is None
    )


def _specimens(observation):
    # Box insertion shifts slots. Preserve multiplicity, levels and containers,
    # not just a set that could conceal a lost duplicate.
    return Counter(
        (s.species_ref, s.level, s.location, s.container_index)
        for s in observation.collection_observation.specimens
    )


def verify_gift_transition(before, after, gift, *, received: bool) -> bool:
    """Independent fresh observations, not executor assertions, earn success."""
    old, new = before.collection_observation, after.collection_observation
    delta = _specimens(after)
    previous = _specimens(before)
    if any(delta[key] < count for key, count in previous.items()):
        return False
    delta.subtract(previous)
    added = [(key, count) for key, count in delta.items() if count]
    # Existing party records remain exact. New members may be appended only.
    party_size = before.raw.party_count
    expected_location = CollectionLocation.PARTY if party_size < 6 else CollectionLocation.BOX
    return bool(
        received
        and gift.species_ref not in old.owned_species
        and new.owned_species == old.owned_species | {gift.species_ref}
        and len(added) == 1
        and added[0][1] == 1
        and added[0][0][:2] == (gift.species_ref, gift.level)
        and added[0][0][2] is expected_location
        and before.raw.player_money == after.raw.player_money
        and before.raw.bag_items == after.raw.bag_items
        and before.party.members == after.party.members[:party_size]
        and after.raw.party_count == min(6, party_size + 1)
        and after.raw.map_id == gift.map_id
        and after.raw.battle_state == 0
        and after.input_ready
    )


def _approach(world, start, gift):
    y, x = gift.at
    plans = []
    for at in ((y + 1, x), (y, x - 1), (y, x + 1), (y - 1, x)):
        if at in start.occupied:
            continue
        try:
            plan = world.plan_feasible_to_map(start, gift.map_id, goal_at=at)
        except RoutePlanningError:
            continue
        if _supported_plan(plan, allow_cut=False, allow_surf=False):
            plans.append(plan)
    return min(plans, key=lambda p: (p.cost, len(p.steps))) if plans else None


def scripted_gift_bindings(runtime, observation, actions, world):
    """Zero-input menu discovery; only a selected binding sends controller input."""
    if not getattr(runtime, "scripted_gifts", False):
        return ()
    reader = runtime.reader
    gift = silph_gift(world.rom)
    if not gift_available(reader, observation, gift):
        return ()
    observer = Gen1TraversalObserver(
        reader,
        capability_projector=partial(
            collection_field_capabilities, runtime.emulator, allow_cut=False, allow_surf=False
        ),
    )
    origin = observer.observe()
    if not origin.ready or origin.mode != "land":
        return ()
    # The first adapter supports walking within Silph or a legal flight from
    # outdoors. Indoor departure for other buildings is explicitly not claimed.
    town = int(MapId.SAFFRON_CITY)
    flight = origin.map_id < 0x25 and origin.map_id != town
    start = origin
    if flight:
        if (
            origin.map_id == 0x0B
            or town not in reader.read_fly_destinations()
            or not int(observation.raw.badge_bits or 0) & int(Badge.THUNDER)
        ):
            return ()
        try:
            fly_menu_indices(observation.raw)
        except Gen1FieldMoveError:
            return ()
        start = replace(
            origin,
            map_id=town,
            at=dict(red_fly_landings(world.rom))[town],
            last_outside_map=town,
            occupied=frozenset(),
        )
    plan = _approach(world, start, gift)
    if plan is None:
        return ()
    used = False
    before_frames = runtime.emulator.frame_count
    before_actions = actions.actions_executed
    origin_box = reader.read_current_box_state()
    party_reader = PokemonRedPartyReader(runtime.emulator)
    origin_party = party_reader.read().members

    def execute():
        nonlocal used
        if used:
            raise RedScriptedGiftError("gift binding already attempted")
        used = True
        fresh = runtime.adapter.observe()
        if (
            fresh != observation
            or observer.observe() != origin
            or reader.read_current_box_state() != origin_box
            or party_reader.read().members != origin_party
            or runtime.emulator.frame_count != before_frames
            or actions.actions_executed != before_actions
            or not gift_available(reader, fresh, gift)
        ):
            raise RedScriptedGiftError("gift origin changed before input")
        port = Gen1FieldMovePort(actions, reader, runtime.emulator)
        if flight:
            port.execute(MacroAction(MacroActionKind.FIELD_MOVE, "fly:saffron_city"))
            landed = observer.observe()
            if (
                not landed.ready
                or landed.map_id != start.map_id
                or landed.at != start.at
                or landed.mode != "land"
            ):
                raise RedScriptedGiftError("gift flight landing differs")
        live_plan = _approach(world, observer.observe(), gift)
        if live_plan is None:
            raise RedScriptedGiftError("gift approach disappeared")
        # No trainer/teacher fallback: an unexpected battle retains its terminal.
        route = execute_route(live_plan, port, observer, replanner=world.replanner())
        if not route.passed:
            raise RedScriptedGiftError("gift route did not settle")
        objects = tuple(
            o
            for o in reader.read_current_map_objects()
            if o.sprite_index == gift.sprite_index and o.picture_id == gift.picture_id
        )
        if len(objects) != 1 or objects[0].at != gift.at:
            raise RedScriptedGiftError("gift worker identity or position differs")
        here = observer.observe()
        delta = gift.at[0] - here.at[0], gift.at[1] - here.at[1]
        facing = {(1, 0): "down", (-1, 0): "up", (0, 1): "right", (0, -1): "left"}.get(delta)
        if facing is None:
            raise RedScriptedGiftError("gift worker is not adjacent")
        if reader.read_player_facing() != facing:
            actions.execute(MacroAction(MacroActionKind.MOVE, facing))
        if observer.observe().at != here.at or reader.read_player_facing() != facing:
            raise RedScriptedGiftError("gift facing did not settle")
        actions.execute(MacroAction(MacroActionKind.INTERACT))
        # B advances this unconditional gift dialogue and declines nicknames;
        # never sample partially shifted PC structures during GivePokemon.
        for _ in range(48):
            actions.execute(MacroAction(MacroActionKind.WAIT, repeat=180))
            if (
                reader.read_silph_gift_received()
                and reader.read_input_readiness().ready
                and not reader.read_bottom_dialogue_box_visible()
            ):
                break
            if reader.read().battle_state:
                raise RedScriptedGiftError("unexpected gift battle")
            actions.execute(MacroAction(MacroActionKind.CANCEL))
        else:
            raise RedScriptedGiftError("gift dialogue exceeded its budget")
        return GoalExecutionReport(
            actions.actions_executed - before_actions,
            runtime.emulator.frame_count - before_frames,
            {
                "mechanic": "scripted_gift",
                "fly_used": flight,
                "route_steps": len(route.executed_steps),
            },
        )

    def verify(report):
        after = runtime.adapter.observe()
        if (
            used
            and report.actions_executed > 0
            and not runtime.emulator.pressed_buttons
            and party_reader.read().members[: len(origin_party)] == origin_party
            and verify_gift_transition(
                observation, after, gift, received=reader.read_silph_gift_received()
            )
        ):
            return GoalVerification.succeeded()
        return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)

    return (
        ExecutableGoalBinding(
            binding_ref=f"red-scripted-gift:{gift.map_id}:{gift.sprite_index}",
            kind=GoalKind.ACQUIRE_SPECIES,
            estimated_effort=min(1.0, (len(plan.steps) + (32 if flight else 0) + 48) / 1000),
            estimated_risk=0.0,
            execute=execute,
            verify=verify,
            search_source_ref=f"pokemon.red:scripted-gift:{gift.map_id}:{gift.sprite_index}",
        ),
    )
