"""No-sale story prerequisites using the qualified ordinary trainer battler.

Trainer targeting is disclosed skill planning, not a learned destination choice.
The existing frozen actor owns battle decisions; no scripted attack fallback.
"""

from dataclasses import replace

from .battle_runtime import BattleRuntimeTiming
from .executor import CountingExecutor
from .gen1_route_runtime import Gen1TraversalObserver
from .gen1_trainer_sight import (
    Gen1TrainerSightProjector,
    static_trainer_sight_zones,
    trainer_headers,
    trainer_sight_zones,
)
from .gen1_traversal import cut_capabilities, map_object_events
from .goal_manager import GoalDecisionOutcome
from .observation import ItemId
from .red_goal_skills import (
    _POKEMON_CENTER_MAPS,
    RedCenterRestoreGoalProvider,
    _raw_party_fully_restored,
)
from .red_learned_trainer import FrozenTrainerBattler, qualified_party_limit
from .red_regional_trainer_funding import funding_scope, regional_trainer_funding_candidates
from .red_routed_trainer_funding import _face_trainer_boundary
from .red_trainer_funding import local_trainer_funding_candidates
from .red_trainer_funding_battle import run_prepared_trainer_funding
from .red_training_ground_route import RedVermilionGroundTransition
from .silph import (
    HYPER_POTION_PRICE,
    HYPER_POTION_PURCHASE_QUANTITY,
    SILPH_X_SPECIAL_SUPPLY_TARGET,
    X_ACCURACY_REPLACEMENT_PRICE,
    X_SPECIAL_PRICE,
)
from .story_supply import SupplyRequirement, plan_no_sale_supplies


def silph_supply_plan(raw, *, recovery_buffer=0):
    """Supply budget only, not chapter admission; Ice Beam must be preinstalled.

    The caller separately verifies moves, events, bag capacity and entry location.
    Existing conservative battle reserves remain unchanged.
    """
    return plan_no_sale_supplies(raw.bag_items, raw.player_money, (
        SupplyRequirement(int(ItemId.HYPER_POTION), HYPER_POTION_PURCHASE_QUANTITY,
                          HYPER_POTION_PRICE),
        SupplyRequirement(int(ItemId.X_SPECIAL), SILPH_X_SPECIAL_SUPPLY_TARGET, X_SPECIAL_PRICE),
        SupplyRequirement(int(ItemId.X_ACCURACY), 1, X_ACCURACY_REPLACEMENT_PRICE),
    ), recovery_buffer=recovery_buffer)


def center_trainer_candidates(rom, reader, route):
    """Reachable undefeated trainers; callers apply their own purpose admission."""
    raw = reader.read()
    if (raw.map_id not in _POKEMON_CENTER_MAPS or raw.battle_state != 0
            or (raw.player_y, raw.player_x) != (3, 3)
            or not raw.party_hp or raw.party_hp != raw.party_max_hp
            or raw.party_status is None or any(raw.party_status)
            or len(raw.party_hp) != raw.party_count
            or len(raw.party_status) != raw.party_count
            or min(raw.party_hp) <= 0 or not reader.read_input_readiness().ready):
        return ()
    observer = Gen1TraversalObserver(reader,
        hazard_projector=Gen1TrainerSightProjector(rom, reader, full_event_offsets=True),
        capability_projector=cut_capabilities)
    start = observer.observe()
    world = route.route_world.with_current_blocks(reader.read_current_map_blocks())
    maps = funding_scope(world.macro_graph, start, indoor_exit_map=start.last_outside_map)
    zones = ()
    for map_id in sorted(maps):
        headers = trainer_headers(rom, {map_id}, full_event_offsets=True)
        objects = map_object_events(rom, {map_id})
        zones += (trainer_sight_zones(headers, objects, raw, reader.read_current_map_objects())
                  if map_id == raw.map_id else
                  static_trainer_sight_zones(headers, objects, raw.event_flags))
    candidates = regional_trainer_funding_candidates(
        rom, world, start, zones, inventoried_maps=maps,
        indoor_exit_map=start.last_outside_map,
        static_blockers={m: world.object_blockers[m] for m in maps},
    )
    return tuple(c for c in candidates if not c.trainer.defeated and c.quote.party)


def story_funding_candidates(rom, reader, route):
    """Unchanged ordinary funding admission, including its ten-level margin."""
    raw = reader.read()
    candidates = center_trainer_candidates(rom, reader, route)
    # Preserve ordinary funding's conservative lead-level screen; it is not a
    # claim that level alone predicts victory or broad battler competence.
    return tuple(c for c in candidates if not c.trainer.defeated and c.quote.party
                 and raw.first_party_level is not None
                 and raw.first_party_level >= max(m.level for m in c.quote.party) + 10
                 and c.quote.expected_money_after(raw.player_money) > raw.player_money)


def restore_story_team(reader, actions, emulator, adapter):
    """Reuse the general Center recovery skill and its independent verifier."""
    live = adapter.observe()
    if _raw_party_fully_restored(live.raw) and (live.raw.player_y, live.raw.player_x) == (3, 3):
        return
    offer = RedCenterRestoreGoalProvider(CountingExecutor(actions), reader, emulator,
        adapter, require_full_pp_restore=True).offer(live)
    if offer.binding is None:
        raise ValueError("earned funding return lacks an executable Center recovery")
    report = offer.binding.execute()
    if offer.binding.verify(report).status is not GoalDecisionOutcome.SUCCEEDED:
        raise RuntimeError("earned funding Center recovery did not verify")


def field_story_funding_candidates(rom, reader, route):
    """Local recovery only: useful undefeated trainers reachable without sight entry."""
    raw = reader.read()
    if (raw.battle_state or raw.map_id in _POKEMON_CENTER_MAPS
            or not raw.party_hp or not any(raw.party_hp)
            or not reader.read_input_readiness().ready):
        return ()
    observer = Gen1TraversalObserver(reader,
        hazard_projector=Gen1TrainerSightProjector(rom, reader, full_event_offsets=True),
        capability_projector=cut_capabilities)
    zones = trainer_sight_zones(trainer_headers(rom, {raw.map_id}, full_event_offsets=True),
        map_object_events(rom, {raw.map_id}), raw, reader.read_current_map_objects())
    world = route.route_world.with_current_blocks(reader.read_current_map_blocks())
    candidates = local_trainer_funding_candidates(rom, world, observer.observe(), zones)
    return tuple(c for c in candidates if c.quote.party and not c.trainer.defeated
        and raw.first_party_hp and raw.first_party_hp > 0 and raw.first_party_level is not None
        and raw.first_party_level >= max(m.level for m in c.quote.party) + 10
        and c.quote.expected_money_after(raw.player_money) > raw.player_money)


def execute_story_trainer_income(*, rom, reader, actions, emulator, battler, adapter,
                                 target, source_raw, target_cash, record,
                                 field_recovery_home: int | None = None):
    """One earned excursion. Caller durably claims and retains terminal on error."""
    if not isinstance(battler, FrozenTrainerBattler) or not (
        1 <= source_raw.party_count <= qualified_party_limit(
            battler.model_sha256, battler.qualification_sha256)
    ):
        raise ValueError("story income requires an authenticated qualified battler")
    if type(target_cash) is not int or not 0 <= source_raw.player_money < target_cash <= 999999:
        raise ValueError("story income requires a real remaining cash shortfall")
    if reader.read() != source_raw:
        raise ValueError("story funding state changed; re-quote before acting")
    route = replace(RedVermilionGroundTransition.from_rom(rom),
        full_event_offsets=True, observe_terrain=True,
        excluded_maps=frozenset({127, 203, 236}))
    if field_recovery_home is not None and (
        type(field_recovery_home) is not int or field_recovery_home not in _POKEMON_CENTER_MAPS
    ):
        raise ValueError("field funding recovery needs its declared Center")
    candidates = (story_funding_candidates(rom, reader, route) if field_recovery_home is None
                  else field_story_funding_candidates(rom, reader, route))
    if target not in candidates:
        raise ValueError("story trainer is not in the current safe funding inventory")
    record("quote", {"target_cash": target_cash, "cash_before": source_raw.player_money,
        "expected_income": target.quote.expected_victory_money,
        "trainer_map": target.trainer.map_id, "trainer_event": target.trainer.event_flag,
        "battle_model_sha256": battler.model_sha256,
        "qualification_sha256": battler.qualification_sha256,
        "recovery_contract": "story-income-recovery-v1",
        "goal_authority": "disclosed funding prerequisite", "sales": 0})
    return _execute_admitted_trainer_excursion(
        reader=reader, actions=actions, emulator=emulator, battler=battler, adapter=adapter,
        target=target, source_raw=source_raw, record=record, route=route, rom=rom,
        field_recovery_home=field_recovery_home)


def _execute_admitted_trainer_excursion(*, reader, actions, emulator, battler, adapter,
                                      target, source_raw, record, route, rom,
                                      field_recovery_home=None, preparation_evolution_guard=None):
    """Shared execution only, after purpose-specific admission; never selects goals."""
    replace(route, destination_map=target.trainer.map_id,
            destination_at=target.approach.terminal_at)(actions, reader, emulator)
    _face_trainer_boundary(actions, reader, target.interaction_facing.value)

    def validate():
        zones = trainer_sight_zones(
            trainer_headers(rom, {target.trainer.map_id}, full_event_offsets=True),
            map_object_events(rom, {target.trainer.map_id}), reader.read(),
            reader.read_current_map_objects())
        expected = target.trainer
        if not any(not t.defeated and all(getattr(t, field) == getattr(expected, field)
                   for field in ("map_id", "sprite_index", "event_flag", "trainer_class",
                                 "trainer_set", "at")) for t in zones):
            raise ValueError("funding trainer identity or undefeated state changed")

    def no_scripted_fallback(_):
        raise RuntimeError("story funding must not query a scripted attack policy")

    receipt = run_prepared_trainer_funding(reader, actions, target=target,
        validate_target=validate, move_slot_policy=no_scripted_fallback,
        timing=BattleRuntimeTiming(), battle_runner_override=battler.run,
        story_income_recovery=True, preparation_evolution_guard=preparation_evolution_guard)
    record("battle_receipt", {"cash_before": receipt.initial_money,
        "cash_after": receipt.final_money, "payout": receipt.payout,
        "ordinary_victory_money": receipt.ordinary_victory_money,
        "pay_day_money": receipt.pay_day_money})
    home = int(source_raw.map_id) if field_recovery_home is None else field_recovery_home
    replace(route, destination_map=home,
            destination_at=(7, 3))(actions, reader, emulator)
    record("healing-started", {"home_map": home})
    restore_story_team(reader, actions, emulator, adapter)
    after = reader.read()
    if (after.player_money != source_raw.player_money + receipt.payout
            or after.bag_items != source_raw.bag_items
            or not (preparation_evolution_guard.matches(source_raw, after)
                    if preparation_evolution_guard is not None
                    else after.party_species_ids == source_raw.party_species_ids)
            or after.party_hp != after.party_max_hp or any(after.party_status)
            or after.map_id != home or (after.player_y, after.player_x) != (3, 3)
            or after.battle_state or not reader.read_input_readiness().ready
            or emulator.pressed_buttons):
        raise RuntimeError("funding return failed resource or healed-party preservation")
    return {"status": "complete", "cash_before": source_raw.player_money,
            "cash_after": after.player_money, "net_income": receipt.payout,
            "sales": 0, "purchase_cost": 0, "model_goal_queries": 0,
            "battle_authority": "qualified_frozen_trainer", "battles": 1}
