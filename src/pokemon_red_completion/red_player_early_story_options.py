"""Compose existing native early-story skills, without chapter-order dispatch.

Every function observes one graph-legal goal. Choosing between goals belongs to
the mixed-menu policy. Selecting the nearest currently executable prerequisite
within a chosen goal is disclosed mechanical support, not learned planning.
No old private chapter assembly or actor mutation is imported here.
"""

from dataclasses import replace

from .gen1_trainer_parties import trainer_party_quote
from .gen1_traversal import map_object_events
from .goal_manager import GoalKind
from .observation import SAFFRON_GUARD_ACCESS_MASK, EventFlag, ItemId, MapId, event_flag_is_set
from .player_option_challenge import OptionChallenge
from .red_player_captain import captain_interaction_binding
from .red_player_cerulean_branches import cerulean_story_options
from .red_player_cerulean_rival import scripted_rival_binding
from .red_player_field_goals import _field_ready, parcel_story_binding
from .red_player_field_item import blocking_field_item_binding
from .red_player_fossil import fossil_pickup_binding
from .red_player_hideout import (
    hideout_elevator_binding,
    hideout_interaction_binding,
    hideout_restoration_binding,
)
from .red_player_saffron import saffron_access_binding
from .red_player_story_battle import story_battle_binding
from .red_player_story_obstruction import obstructing_story_battle_binding
from .red_player_story_travel import story_destination_map, story_travel_binding
from .red_player_tower import fuji_binding, marowak_binding, marowak_pending
from .red_scripted_story_trainer import (
    fossil_guard_contract,
    hideout_scripted_contract,
    ss_anne_rival_contract,
    tower_rival_contract,
)
from .red_story_battle import StoryTrainerContract
from .red_training_ground_route import RedVermilionGroundTransition


def _legal(runtime, objective):
    return _field_ready(runtime) and objective in {
        o.id
        for o in runtime.adapter.graph.available_objectives(runtime.adapter.observe().game_state)
    }


def _row(binding, objective, *, route, combat_levels=(), contract=None, combat=False):
    if binding is None:
        return None
    challenge = OptionChallenge(combat, False, 0.0, 0.0, 0.0)
    if contract is not None:
        quote = trainer_party_quote(
            route.rom, contract.trainer_identity[0], contract.trainer_identity[2]
        )
        challenge = OptionChallenge.from_levels(
            combat_levels=combat_levels,
            opponent_levels=tuple(m.level for m in quote.party),
        )
    return replace(binding, story_objective_ref=objective), challenge


def early_story_travel_option(runtime, actions, *, objective_id, route, battler):
    """Keep travel/obstruction as peers; departing Bill observes the exit first."""
    if not _legal(runtime, objective_id):
        return None
    raw = runtime.reader.read()
    departing_bill = raw.map_id == int(MapId.BILLS_HOUSE)
    boarding = (
        objective_id == "obtain_cut"
        and raw.map_id == int(MapId.VERMILION_CITY)
        and isinstance(route, RedVermilionGroundTransition)
        and any(
            item == int(ItemId.SS_TICKET) and type(quantity) is int and quantity > 0
            for item, quantity in (getattr(raw, "bag_items", None) or ())
        )
    )
    if boarding:
        # The known ticket guard speaks during movement. A poison-only route or
        # text-free cash certificate cannot settle it. This one-map opt-in keeps
        # the existing bounded dialogue handler, destination and resource checks;
        # it grants no combat, spending, captain reward or strategic substitution.
        route = replace(
            route, maximum_scripted_dialogues=1, require_cash_safe=False,
            allow_wild_faints=False, allow_field_faint_dialogue=False,
        )
    kwargs = dict(
        frontier=not departing_bill,
        stop_at_map_boundary=True,
        intermediate_map=int(MapId.ROUTE_25) if departing_bill else None,
    )
    binding = story_travel_binding(
        runtime, actions, objective_id=objective_id, route=route,
        **({"certify_cash_approach": False} if boarding else {}), **kwargs
    )
    combat = False
    if binding is None:
        binding = obstructing_story_battle_binding(
            runtime,
            actions,
            objective_id=objective_id,
            route=route,
            battler=battler,
            allow_sequence=True,
            frontier=not departing_bill,
            intermediate_map=kwargs["intermediate_map"],
        )
        combat = binding is not None
    return _row(binding, objective_id, route=route, combat=combat)


def parcel_story_option(runtime, actions, observation=None, *, route):
    if not _legal(runtime, "receive_pokedex"):
        return None
    return _row(parcel_story_binding(runtime, actions, route=route), "receive_pokedex", route=route)


def cerulean_arrival_story_option(runtime, actions, observation=None, *, route,
                                 battler, combat_levels):
    """Reuse real travel, then the exact native fossil gate when it blocks passage.

    Fossil selection is existing least-cost interaction support, not a learned
    strategic preference or an automatic completion of the Cerulean objective.
    """
    objective = "reach_cerulean"
    if not _legal(runtime, objective):
        return None
    row = early_story_travel_option(
        runtime, actions, objective_id=objective, route=route, battler=battler
    )
    if row is not None:
        return row
    raw = runtime.reader.read()
    event = int(EventFlag.BEAT_MT_MOON_EXIT_SUPER_NERD)
    if (raw.map_id != int(MapId.MT_MOON_B2F) or raw.event_flags is None
            or len(raw.event_flags) * 8 <= event):
        return None
    if not event_flag_is_set(raw.event_flags, event):
        contract = fossil_guard_contract(route.rom, raw)
        binding = story_battle_binding(
            runtime, actions, contract=contract, route=route, battler=battler,
            completes_objective=False, scripted_fossil_guard=True,
        )
        return _row(binding, objective, route=route, combat_levels=combat_levels,
                    contract=contract)
    return _row(fossil_pickup_binding(runtime, actions, route=route), objective, route=route)


def bill_story_option(runtime, actions, observation=None, *, route, battler, combat_levels):
    if not _legal(runtime, "help_bill"):
        return None
    rows = cerulean_story_options(
        runtime, actions, route=route, battler=battler, combat_levels=combat_levels
    )
    bill = next((r for r in rows if r.objective_id == "help_bill"), None)
    return None if bill is None else (bill.binding, bill.challenge)


def cut_story_option(runtime, actions, observation=None, *, route, battler, combat_levels):
    objective = "obtain_cut"
    if not _legal(runtime, objective):
        return None
    raw = runtime.reader.read()
    if raw.map_id == int(MapId.SS_ANNE_2F) and runtime.reader.read_ss_anne_rival_script() != 4:
        binding = scripted_rival_binding(
            runtime,
            actions,
            route=route,
            battler=battler,
            objective_id=objective,
            map_id=int(MapId.SS_ANNE_2F),
            contract_factory=ss_anne_rival_contract,
            already_defeated=lambda: runtime.reader.read_ss_anne_rival_script() == 4,
            entries=(((9, 36), "up"), ((9, 37), "up"), ((8, 35), "right"), ((8, 38), "left")),
        )
        return _row(
            binding,
            objective,
            route=route,
            combat_levels=combat_levels,
            contract=ss_anne_rival_contract(route.rom, runtime.reader) if binding else None,
        )
    if raw.map_id == int(MapId.SS_ANNE_CAPTAINS_ROOM):
        return _row(
            captain_interaction_binding(runtime, actions, route=route), objective, route=route
        )
    return early_story_travel_option(
        runtime, actions, objective_id=objective, route=route, battler=battler
    )


def hideout_story_option(
    runtime, actions, observation=None, *, objective_id, route, battler, combat_levels
):
    if objective_id not in {"clear_rocket_hideout", "obtain_silph_scope"}:
        raise ValueError("Hideout composition requires its own graph objective")
    if not _legal(runtime, objective_id):
        return None
    raw = runtime.reader.read()
    binding = hideout_interaction_binding(runtime, actions, route=route)
    if binding is not None:
        return _row(binding, objective_id, route=route)
    contracts = []
    if objective_id == "clear_rocket_hideout":
        if raw.map_id == 135 and any(
            o.sprite_index == 11 for o in runtime.reader.read_current_map_objects()
        ):
            contracts.append((hideout_scripted_contract(route.rom, raw), True, False))
        elif raw.map_id == 202:
            # These are cartridge prerequisites of the native door/key/boss,
            # not a supplied goal order. Quote ALL reachable unfinished guards.
            for event in (1700, 1698, 1699, 1703):
                if event_flag_is_set(raw.event_flags, event):
                    continue
                contract = (
                    hideout_scripted_contract(route.rom, raw)
                    if event == 1703
                    else StoryTrainerContract.from_cartridge(
                        route.rom,
                        raw,
                        objective_id=objective_id,
                        battle_plan_id="hideout-required-trainer",
                        map_id=202,
                        defeated_event=event,
                    )
                )
                contracts.append((contract, event == 1703, event == 1703))
    candidates = []
    for contract, scripted, completes in contracts:
        binding = story_battle_binding(
            runtime,
            actions,
            contract=contract,
            route=route,
            battler=battler,
            scripted_hideout=scripted,
            completes_objective=completes,
        )
        if binding is not None:
            candidates.append((binding, contract))
    if candidates:
        binding, contract = min(
            candidates, key=lambda row: (row[0].estimated_effort, row[0].binding_ref)
        )
        return _row(
            binding, objective_id, route=route, combat_levels=combat_levels, contract=contract
        )
    binding = hideout_elevator_binding(runtime, actions, route=route)
    if binding is not None:
        return _row(binding, objective_id, route=route)
    intermediate = (
        135 if not event_flag_is_set(raw.event_flags, int(EventFlag.FOUND_ROCKET_HIDEOUT)) else None
    )
    binding = story_travel_binding(
        runtime,
        actions,
        objective_id=objective_id,
        route=route,
        intermediate_map=intermediate,
        frontier=intermediate is None,
        stop_at_map_boundary=True,
    )
    combat = False
    if binding is None:
        binding = obstructing_story_battle_binding(
            runtime,
            actions,
            objective_id=objective_id,
            route=route,
            battler=battler,
            intermediate_map=intermediate,
            frontier=intermediate is None,
            allow_sequence=True,
        )
        combat = binding is not None
    return _row(binding, objective_id, route=route, combat=combat)


def fuji_story_option(runtime, actions, observation=None, *, route, battler, combat_levels,
                      trainer_battler=None):
    """Keep the exact one-off wild actor separate from optional scoped trainers."""
    objective = "rescue_fuji"
    if not _legal(runtime, objective):
        return None
    raw = runtime.reader.read()
    story_actor = battler if trainer_battler is None else trainer_battler
    if raw.map_id in (199, 202, 203):
        # The lift's exit is mutable game state, not its static ROM warp.
        # Reuse the qualified, resource-preserving return through B2 before
        # onward Tower travel. This advances only the selected goal's route;
        # it neither heals the party nor completes Fuji or selects a battle.
        binding = hideout_restoration_binding(runtime, actions, route=route, return_only=True)
        return _row(
            None if binding is None else replace(binding, kind=GoalKind.ADVANCE_STORY),
            objective,
            route=route,
        )
    if raw.map_id == 143 and not event_flag_is_set(raw.event_flags, 239):
        binding = scripted_rival_binding(
            runtime,
            actions,
            route=route,
            battler=story_actor,
            objective_id=objective,
            map_id=143,
            contract_factory=tower_rival_contract,
            already_defeated=lambda: event_flag_is_set(runtime.reader.read().event_flags, 239),
            entries=(((7, 14), "up"),),
        )
        return _row(
            binding,
            objective,
            route=route,
            combat_levels=combat_levels,
            contract=tower_rival_contract(route.rom, runtime.reader) if binding else None,
        )
    binding = fuji_binding(runtime, actions, route=route)
    if binding is not None:
        return _row(binding, objective, route=route)
    if marowak_pending(raw):
        binding = marowak_binding(runtime, actions, route=route, battler=battler)
        if binding is not None:
            return _row(binding, objective, route=route, combat=True)
        binding = blocking_field_item_binding(
            runtime, actions, route=route, destination_at=(16, 11), forbidden=frozenset({(16, 10)})
        )
        if binding is not None:
            return _row(binding, objective, route=route)
    target = None
    if raw.map_id == 148 and story_destination_map(objective, raw) == 148:
        fuji = next(o for o in map_object_events(route.rom, {148}) if o.object_index == 4)
        target = (fuji.y + 1, fuji.x)
    binding = story_travel_binding(
        runtime,
        actions,
        objective_id=objective,
        route=route,
        frontier=target is None,
        stop_at_map_boundary=True,
        destination_at=target,
    )
    if binding is not None:
        return _row(binding, objective, route=route)
    if raw.map_id == 148:
        candidates = []
        for event in (273, 274, 275):
            if event_flag_is_set(raw.event_flags, event):
                continue
            contract = StoryTrainerContract.from_cartridge(
                route.rom,
                raw,
                objective_id=objective,
                battle_plan_id="required-tower-rocket",
                map_id=148,
                defeated_event=event,
            )
            binding = story_battle_binding(
                runtime,
                actions,
                contract=contract,
                route=route,
                battler=story_actor,
                completes_objective=False,
            )
            if binding is not None:
                candidates.append((binding, contract))
        if candidates:
            binding, contract = min(
                candidates, key=lambda row: (row[0].estimated_effort, row[0].binding_ref)
            )
            return _row(
                binding, objective, route=route, combat_levels=combat_levels, contract=contract
            )
    binding = obstructing_story_battle_binding(
        runtime,
        actions,
        objective_id=objective,
        route=route,
        battler=story_actor,
        frontier=target is None,
        allow_sequence=True,
        destination_at=target,
    )
    return _row(binding, objective, route=route, combat=binding is not None)


def saffron_story_option(runtime, actions, observation=None, *, route, battler):
    if not _legal(runtime, "reach_saffron"):
        return None
    flags = runtime.reader.read().status_flags_1
    if flags is None or not flags & SAFFRON_GUARD_ACCESS_MASK:
        return _row(
            saffron_access_binding(runtime, actions, route=route), "reach_saffron", route=route
        )
    return early_story_travel_option(
        runtime, actions, objective_id="reach_saffron", route=route, battler=battler
    )
