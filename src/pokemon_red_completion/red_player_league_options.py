"""Fresh League options using the existing cartridge skill and learned actor.

Room order is a cartridge prerequisite, not a strategic preference. This adapter
only exposes the currently legal challenge; the existing mixed menu chooses it
against actual resource/preparation alternatives. No input lives in enumeration.
"""

from dataclasses import asdict, dataclass, replace
from hashlib import sha256

from .gen1_champion_script import champion_script_binding
from .gen1_trainer_parties import trainer_party_quote
from .goal_manager import GoalFailureReason, GoalKind
from .goal_manager_runtime import ExecutableGoalBinding, GoalExecutionReport, GoalVerification
from .observation import EventFlag, ItemId, MapId, event_flag_is_set
from .player_option_challenge import OptionChallenge
from .provenance import canonical_sha256
from .red_champion_story import RedCartridgeChampionSkill
from .red_development_story_scope import DevelopmentStoryScope
from .red_goal_context_profile import (
    RedGoalMechanic,
    _thaw,
    build_red_goal_context_profile_payload,
    parse_red_goal_context_profile,
    require_resupply_only_profile_transition,
)
from .red_goal_skills import _raw_party_fully_restored
from .red_league_entry import forecast_league_entry_events
from .red_lorelei_story import (
    LoreleiStoryBattleStopped,
    ScopedAssistedChampionController,
    ScopedAssistedLeagueRetryController,
)
from .red_player_field_goals import _field_ready, routed_restoration_binding
from .red_resource_goal_router import RedResourceGoalRouter
from .red_story_battle import StoryTrainerContract
from .red_trainer_story import RedCartridgeLoreleiSkill


@dataclass(frozen=True)
class LeaguePlayerTarget:
    objective_id: str
    room: MapId
    event: EventFlag
    entry_maps: frozenset[MapId]


LEAGUE_PLAYER_TARGETS = (
    LeaguePlayerTarget("defeat_lorelei", MapId.LORELEIS_ROOM, EventFlag.BEAT_LORELEI,
                      frozenset({MapId.INDIGO_PLATEAU, MapId.INDIGO_PLATEAU_LOBBY,
                                 MapId.LORELEIS_ROOM})),
    LeaguePlayerTarget("defeat_bruno", MapId.BRUNOS_ROOM, EventFlag.BEAT_BRUNO,
                      frozenset({MapId.LORELEIS_ROOM, MapId.BRUNOS_ROOM})),
    LeaguePlayerTarget("defeat_agatha", MapId.AGATHAS_ROOM, EventFlag.BEAT_AGATHA,
                      frozenset({MapId.BRUNOS_ROOM, MapId.AGATHAS_ROOM})),
    LeaguePlayerTarget("defeat_lance", MapId.LANCES_ROOM, EventFlag.BEAT_LANCES_ROOM_TRAINER,
                      frozenset({MapId.AGATHAS_ROOM, MapId.LANCES_ROOM})),
)
CHAMPION_PLAYER_TARGET = LeaguePlayerTarget(
    "defeat_champion",MapId.CHAMPIONS_ROOM,EventFlag.BEAT_CHAMPION_RIVAL,
    frozenset({MapId.LANCES_ROOM}),
)


def _league_target_contract(reader, rom, raw, target):
    if target is CHAMPION_PLAYER_TARGET:
        script = champion_script_binding(rom, reader.read_final_league_scene().rival_starter)
        quote = trainer_party_quote(rom, script.opponent, script.trainer_set)
        return StoryTrainerContract(
            target.objective_id, "cartridge-final-story", int(target.room),
            script.active_identity, script.event_flag, quote.expected_victory_money,
        )
    return StoryTrainerContract.from_cartridge(
        rom, raw, objective_id=target.objective_id,
        battle_plan_id="cartridge-trainer-story", map_id=int(target.room),
        defeated_event=int(target.event), allow_final_class=target.objective_id == "defeat_lance",
    )


def engaged_league_contract(reader, rom, *, include_champion=False):
    """Authenticate an existing League battle; never approach or start one.

    The field projection checks the native earned prefix only. Actual room,
    flags and active trainer identity still bind the returned battle contract.
    """
    if type(include_champion) is not bool:
        raise TypeError("Champion connection permission must be an explicit boolean")
    raw = reader.read()
    targets = LEAGUE_PLAYER_TARGETS + ((CHAMPION_PLAYER_TARGET,) if include_champion else ())
    target = next((t for t in targets if raw.map_id == t.room), None)
    if raw.battle_state != 2 or target is None:
        return None
    eligibility = replace(raw, battle_state=0, map_id=(
        int(MapId.LANCES_ROOM) if target is CHAMPION_PLAYER_TARGET else raw.map_id))
    if live_league_player_target(eligibility, include_champion=include_champion) is not target:
        return None
    contract = _league_target_contract(reader, rom, raw, target)
    if reader.read_active_trainer_identity() != contract.trainer_identity:
        raise ValueError("engaged League trainer identity differs from its native room")
    return target, contract


def bind_live_league_runtime(
    runtime, *, battler, rom, route_world, output, work_order,
    include_champion=False, development_retry_reentry=False,
    maximum_level_deficit=30, maximum_decisions=80, allow_engaged=False,
):
    """Compose the existing scoped actor for this actual native frontier.

    This is DEVELOPMENT admission, not deployment or phase selection. The
    mixed menu still chooses challenge versus its resource/preparation peers.
    Calling it again after a room transition binds the new exact contract; no
    previous room's actor or completed-objective ordering is substituted.
    Enumeration issues no inputs and performs no weight, flag or party edits.
    """
    if type(work_order) is not bytes or not work_order:
        raise ValueError("League composition requires its exact work-order bytes")
    if type(allow_engaged) is not bool:
        raise TypeError("Engaged League permission must be an explicit boolean")
    raw = runtime.reader.read()
    if raw.battle_state == 2:
        retained = (engaged_league_contract(runtime.reader, rom, include_champion=include_champion)
                    if allow_engaged else None)
        if retained is None:
            return None
        target, contract = retained
    else:
        latch = (runtime.reader.read_league_challenge_started()
                 if development_retry_reentry and raw.map_id == MapId.INDIGO_PLATEAU else None)
        target = live_league_player_target(
            raw, include_champion=include_champion,
            development_retry_reentry=development_retry_reentry, challenge_started=latch,
        )
        if target is None or not _field_ready(runtime):
            return None
        forecast = replace(raw, event_flags=forecast_league_entry_events(
            raw, development_retry_reentry=development_retry_reentry, challenge_started=latch,
        ))
        contract = _league_target_contract(runtime.reader, rom, forecast, target)
    champion = target is CHAMPION_PLAYER_TARGET
    scope = DevelopmentStoryScope(
        battler.source_state_sha256, battler.root_lineage_id, battler.model_sha256,
        canonical_sha256(battler.model.to_dict()), sha256(work_order).hexdigest(),
        contract=contract, allow_learned_tactics=True, diagnostic_status_entry=True,
        screen_capped_status_moves=True,
    )
    actor = replace(battler, calls=0, output=output,
                    qualification_sha256=scope.identity, development_story_scope=scope)
    actor.require_story_contract(contract)
    owner_type = (ScopedAssistedChampionController if champion
                  else ScopedAssistedLeagueRetryController)
    owner = owner_type(
        actor, contract, work_order, maximum_decisions,
        declared_model_sha256=actor.model_sha256, declared_level_deficit=maximum_level_deficit,
        declared_stay_when_productive=False,
    )
    actor.pp_reentry_screen_active(actor.story_authority())
    return replace(
        runtime, trainer_battle_runner=actor.run, trainer_battle_model_sha256=actor.model_sha256,
        trainer_battle_qualification_sha256=scope.identity,
        league_story_battle_controller=owner, trainer_story_world=route_world,
    ), actor, target


def league_medicine_profiles(
    runtime, *, full_restore_target=4, revive_target=2, full_heal_target=0,
):
    """Normal Indigo shop lots; quantities are disclosed support, not learning.

    Only an already configured Indigo mart provider may receive these clerk
    indices. The existing executor still verifies price, affordability, native
    stock and party preservation. No PP item or money generation is invented.
    """
    for target in (full_restore_target, revive_target, full_heal_target):
        if type(target) is not int or not 0 <= target <= 99:
            raise ValueError("League medicine targets must be integer stack limits")
    supply = next((s for s in runtime.profile.providers if s.kind is GoalKind.RESUPPLY), None)
    if (supply is None or supply.mechanic is not RedGoalMechanic.MART_RESUPPLY
            or supply.parameters.get("map_id") != int(MapId.INDIGO_PLATEAU_LOBBY)):
        raise ValueError("League medicine lots require the configured Indigo mart")
    bag = dict(runtime.reader.read().bag_items)
    profiles = []
    for item, index, price, target in (
        (ItemId.FULL_RESTORE, 2, 3000, full_restore_target),
        (ItemId.REVIVE, 5, 1500, revive_target),
        (ItemId.FULL_HEAL, 4, 600, full_heal_target),
    ):
        held = bag.get(int(item), 0)
        for quantity in (1, 2):
            if held + quantity > target:
                continue
            providers = []
            for spec in runtime.profile.providers:
                parameters = _thaw(spec.parameters)
                if spec.kind is GoalKind.RESUPPLY:
                    parameters.pop("affordable_ball_purchase", None)
                    parameters.pop("resource_choice_variants", None)
                    parameters.update(
                        purchases=[dict(absolute_index=index, item_id=int(item),
                                        quantity=quantity, unit_price=price)],
                        reserve_targets=[dict(item_id=int(item), quantity=held + quantity)],
                    )
                providers.append((spec.kind, spec.mechanic, parameters))
            profile = parse_red_goal_context_profile(build_red_goal_context_profile_payload(
                profile_id=runtime.profile.profile_id, providers=tuple(providers),
            ))
            require_resupply_only_profile_transition(runtime.profile, profile)
            profiles.append(profile)
    return tuple(profiles)


def league_medicine_reserve_binding(
    runtime, actions, *, route_world, observation, full_restore_target=4,
    revive_target=2, full_heal_target=0, development_retry_reentry=False, record=None,
    balanced_first_lots=False,
    minimum_revive_coverage=0,
):
    """One affordable pre-entry support purchase, or None; never a model choice.

    Call only under the explicitly declared temporary medicine safeguard. The
    caller must attribute this binding to support, not mask a learned decision.
    After entry there is no assumed return route to the shop. Partial stock is
    not reported as a satisfied reserve when cash or carrying space runs out.
    """
    if type(development_retry_reentry) is not bool:
        raise TypeError("League retry permission must be an explicit boolean")
    if type(balanced_first_lots) is not bool:
        raise TypeError("Balanced medicine coverage requires an explicit boolean")
    if (
        type(revive_target) is not int
        or not 0 <= revive_target <= 99
        or type(minimum_revive_coverage) is not int
        or not 0 <= minimum_revive_coverage <= revive_target
        or (minimum_revive_coverage and not balanced_first_lots)
    ):
        raise ValueError("Minimum revive coverage requires balanced explicit stack targets")
    profiles = league_medicine_profiles(runtime, full_restore_target=full_restore_target,
                                        revive_target=revive_target,
                                        full_heal_target=full_heal_target)
    raw = runtime.reader.read()
    if (raw.map_id not in {MapId.INDIGO_PLATEAU, MapId.INDIGO_PLATEAU_LOBBY}
            or not observation.input_ready or not _field_ready(runtime)):
        return None
    target = live_league_player_target(
        raw, development_retry_reentry=development_retry_reentry,
        challenge_started=(runtime.reader.read_league_challenge_started()
                           if development_retry_reentry else None),
    )
    if target is not LEAGUE_PLAYER_TARGETS[0]:
        return None
    offers = []
    for profile in profiles:
        supply = next(s for s in profile.providers if s.kind is GoalKind.RESUPPLY)
        purchase = supply.parameters["purchases"][0]
        item, quantity, price = (purchase[key] for key in ("item_id", "quantity", "unit_price"))
        router = RedResourceGoalRouter(
            replace(runtime, profile=profile), actions, route_world,
            quote_resource_costs=True, prepare_capture_party=False,
            prepare_capture_escort=False, include_recovery_offers=False,
        )
        inventory = router.enumerate_routed_kinds(observation, frozenset({GoalKind.RESUPPLY}))
        for binding in inventory.bindings:
            if binding.kind is GoalKind.RESUPPLY:
                quote = binding.resource_quote
                if (quote is None or quote.funding_proceeds or quote.expected_income
                        or quote.available_funds != raw.player_money
                        or quote.purchase_cost != quantity * price or len(quote.reserves) != 1
                        or quote.reserves[0].resource != "recovery"
                        or quote.reserves[0].available != dict(raw.bag_items).get(item, 0)
                        or quote.reserves[0].purchased != quantity
                        or quote.reserves[0].target != dict(raw.bag_items).get(item, 0) + quantity):
                    raise ValueError("medicine safeguard requires actual affordable recovery stock")
                missing_coverage = (balanced_first_lots
                                    and dict(raw.bag_items).get(item, 0) == 0)
                if (
                    balanced_first_lots
                    and item == int(ItemId.REVIVE)
                    and dict(raw.bag_items).get(int(ItemId.FULL_RESTORE), 0) > 0
                    and dict(raw.bag_items).get(item, 0) < minimum_revive_coverage
                ):
                    # A later faint needs a real Revive, not another HP topup.
                    # Preserve first HP coverage; never assume future payouts
                    # or spend more than the ordinary quoted current cash.
                    missing_coverage = True
                if item == int(ItemId.FULL_HEAL) and not (
                    dict(raw.bag_items).get(int(ItemId.FULL_RESTORE), 0)
                    and dict(raw.bag_items).get(int(ItemId.REVIVE), 0)
                ):
                    # Do not spend the last cure money ahead of affordable
                    # first HP/revival coverage (e.g. the existing 4500 lot).
                    missing_coverage = False
                # Cover the declared roles before topping up larger lots.
                # An opted-in 600-cash status cure preserves a 3000-cash
                # Full Restore for actual HP loss. Default two-role ordering
                # remains unchanged; no unavailable Indigo item is invented.
                # A single first Revive leaves 3000 for a heal at 4500cash;
                # two Revives first would leave that ordinary heal unaffordable.
                first = 0 if missing_coverage else 1
                role = (-1 if item == int(ItemId.FULL_HEAL) else
                        0 if item == int(ItemId.REVIVE) else 1) if missing_coverage else (
                    -1 if item == int(ItemId.FULL_HEAL) else
                    0 if item == int(ItemId.FULL_RESTORE) else 1)
                first_single = missing_coverage and dict(raw.bag_items).get(item, 0) == 0
                lot = quantity if first_single else -quantity
                offers.append((first, role, lot, binding))
    binding = min(offers, key=lambda row: row[:3])[3] if offers else None
    if record is not None:
        record("league-medicine-safeguard", dict(
            schema="pokemon.red.league-medicine-safeguard.v1", learned_procurement=False,
            supplied_targets=dict(full_restore=full_restore_target, revive=revive_target,
                                  full_heal=full_heal_target),
            balanced_first_lots=balanced_first_lots,
            minimum_revive_coverage=minimum_revive_coverage,
            actual_cash=raw.player_money, reserve_satisfied=not profiles,
            purchase_available=binding is not None,
            quote=None if binding is None else binding.resource_quote.public_dict(),
        ))
    return binding


def league_medicine_capacity_binding(runtime, actions, *, route, observation,
                                    development_retry_reentry=False, record=None,
                                    full_restore_target=4, revive_target=2, full_heal_target=0):
    """Store completed keys only as the approved medicine-reserve prerequisite.

    This is free, conserving native PC support before first-room entry. It
    neither earns money nor supplies a broader strategic storage preference.
    The next boundary must re-observe real stock before purchasing anything.
    """
    from .red_story_item_storage import completed_key_storage_binding

    if type(development_retry_reentry) is not bool:
        raise TypeError("League capacity permission must be an explicit boolean")
    raw = runtime.reader.read()
    if (raw.map_id not in {MapId.INDIGO_PLATEAU, MapId.INDIGO_PLATEAU_LOBBY}
            or not observation.input_ready or not _field_ready(runtime)):
        return None
    target = live_league_player_target(
        raw, development_retry_reentry=development_retry_reentry,
        challenge_started=(runtime.reader.read_league_challenge_started()
                           if raw.map_id == MapId.INDIGO_PLATEAU else None),
    )
    if target is not LEAGUE_PLAYER_TARGETS[0]:
        return None
    profiles = league_medicine_profiles(runtime, full_restore_target=full_restore_target,
                                       revive_target=revive_target,
                                       full_heal_target=full_heal_target)
    absent = {int(next(spec for spec in profile.providers if spec.kind is GoalKind.RESUPPLY)
                  .parameters["purchases"][0]["item_id"]) for profile in profiles}
    bag = dict(raw.bag_items or ())
    slots = sum(item not in bag for item in absent)
    if slots == 0 or len(bag) + slots <= 20:
        return None
    binding = completed_key_storage_binding(runtime, actions, route=route,
        reserved_slots=slots, include_indigo_lobby=True, allow_spare_tm_storage=True)
    if binding is None:
        return None
    if binding.kind is not GoalKind.MANAGE_STORAGE or binding.maximum_cash_debit != 0:
        raise ValueError("League medicine capacity requires free native key storage")

    def execute():
        report = binding.execute()
        evidence = dict(report.evidence, support="approved_league_medicine_capacity",
                        learned_item_selection=False, medicine_slots_required=slots)
        if record is not None:
            record("league-medicine-capacity", evidence)
        return replace(report, evidence=evidence)

    return replace(binding, binding_ref="league-medicine-capacity:" + binding.binding_ref,
                   execute=execute)


def league_pre_entry_healing_binding(runtime, actions, *, route,
                                    development_retry_reentry=False, record=None,
                                    require_indigo_checkpoint=False):
    """The approved normal-nurse safeguard, only before the first League room.

    No levels, cash, party identities or flags are edited. The existing routed
    nurse verifies full HP/status/PP and retained stock, progress and specimens.
    This is disclosed support, not learned medicine anticipation or a new goal.
    """
    if type(development_retry_reentry) is not bool:
        raise TypeError("League healing permission must be an explicit boolean")
    if type(require_indigo_checkpoint) is not bool:
        raise TypeError("League Indigo checkpoint permission must be an explicit boolean")
    raw = runtime.reader.read()
    if (raw.map_id not in {MapId.INDIGO_PLATEAU, MapId.INDIGO_PLATEAU_LOBBY}
            or not _field_ready(runtime) or _raw_party_fully_restored(raw) and not (
                require_indigo_checkpoint
                and runtime.reader.read_last_blackout_map() != int(MapId.INDIGO_PLATEAU))):
        return None
    target = live_league_player_target(
        raw, development_retry_reentry=development_retry_reentry,
        challenge_started=(runtime.reader.read_league_challenge_started()
                           if raw.map_id == MapId.INDIGO_PLATEAU else None),
    )
    if target is not LEAGUE_PLAYER_TARGETS[0]:
        return None
    binding = routed_restoration_binding(
        runtime, actions, home_map=int(MapId.INDIGO_PLATEAU_LOBBY), route=route,
        include_indigo_lobby=True, observe_trainer_hazards=True,
        **({"require_indigo_checkpoint": True} if require_indigo_checkpoint else {}),
    )
    if binding is None:
        return None
    if binding.kind is not GoalKind.RESTORE_TEAM or binding.maximum_cash_debit != 0:
        raise ValueError("League healing safeguard requires a free native nurse")

    def execute():
        report = binding.execute()
        evidence = dict(report.evidence, support="approved_pre_entry_league_healing",
                        learned_healing=False, native_full_restoration_required=True,
                        **({"native_indigo_checkpoint_required": True,
                            "last_blackout_map": runtime.reader.read_last_blackout_map()}
                           if require_indigo_checkpoint else {}))
        if record is not None:
            record("league-pre-entry-healing", evidence)
        return replace(report, evidence=evidence)

    return replace(binding, binding_ref="league-pre-entry-healing:" + binding.binding_ref,
                   execute=execute)


def live_league_player_target(raw, *, include_champion=False,
                             development_retry_reentry=False, challenge_started=None):
    """Use current native flags, never historical completed-quest ordering.

Champion uses its existing distinct skill/contract and needs explicit opt-in.
Missing telemetry, engaged battle and unrelated locations
do not create a challenge. Non-prefix native flags refuse ambiguous inference.
"""
    if type(include_champion) is not bool:
        raise TypeError("Champion connection permission must be an explicit boolean")
    events = forecast_league_entry_events(raw,
        development_retry_reentry=development_retry_reentry,
        challenge_started=challenge_started)
    if events is None or raw.battle_state:
        return None
    if len(events) <= max(int(t.event) for t in LEAGUE_PLAYER_TARGETS) // 8:
        return None
    defeated = tuple(event_flag_is_set(events, int(t.event))
                     for t in LEAGUE_PLAYER_TARGETS)
    if any(defeated[i] and not all(defeated[:i]) for i in range(len(defeated))):
        raise ValueError("League native flags do not form a current earned prefix")
    for target, done in zip(LEAGUE_PLAYER_TARGETS, defeated, strict=True):
        if not done:
            return target if raw.map_id in target.entry_maps else None
    if (include_champion and raw.map_id in CHAMPION_PLAYER_TARGET.entry_maps
        and len(raw.event_flags)>int(CHAMPION_PLAYER_TARGET.event)//8
        and event_flag_is_set(raw.event_flags,int(EventFlag.BEAT_LANCE))
        and not event_flag_is_set(raw.event_flags,int(CHAMPION_PLAYER_TARGET.event))):
        return CHAMPION_PLAYER_TARGET
    return None


def league_native_prerequisite(target, objective_ref):
    """A reset earlier room can serve a still-unfinished later story goal.

    This does not choose a goal or claim the later room was won. The game,
    not historical quest completion, determines the actual combat contract.
    """
    targets = LEAGUE_PLAYER_TARGETS + (CHAMPION_PLAYER_TARGET,)
    ids = tuple(t.objective_id for t in targets)
    return (target in targets and objective_ref in ids
            and ids.index(target.objective_id) <= ids.index(objective_ref))


def league_story_option(
    runtime, actions, *, route, combat_levels, record=None, history=None,
    maximum_level_deficit=5, development_retry_reentry=False,
    include_champion=False, rematch=True,
    progress_objective_ref=None,
):
    """One fresh executable challenge plus its exact cartridge preview.

The caller supplies the already admitted source/model-bound League controller.
Existing skill admission still owns controller, partition, party, approach and
resource legality. A verified ordinary loss is a failed goal, never a victory.
"""
    if type(rematch) is not bool or (not rematch and development_retry_reentry):
        raise ValueError("first League challenge cannot use retry permission")
    if type(development_retry_reentry) is not bool:
        raise TypeError("League retry permission must be an explicit boolean")
    if type(include_champion) is not bool:
        raise TypeError("Champion connection permission must be an explicit boolean")
    if not _field_ready(runtime):
        return None
    before = runtime.reader.read()
    target = live_league_player_target(before,include_champion=include_champion,
        development_retry_reentry=development_retry_reentry,
        challenge_started=(runtime.reader.read_league_challenge_started()
                           if development_retry_reentry and before.map_id == MapId.INDIGO_PLATEAU
                           else None))
    if target is None:
        return None
    objective_ref = (target.objective_id if progress_objective_ref is None
                     else progress_objective_ref)
    if progress_objective_ref is not None and (
        not league_native_prerequisite(target, objective_ref)
        or objective_ref not in {o.id for o in runtime.adapter.graph.available_objectives(
            runtime.adapter.observe().game_state)}
    ):
        return None
    owner = getattr(runtime, "league_story_battle_controller", None)
    if owner is None or owner.contract.objective_id != target.objective_id:
        raise ValueError("League controller does not bind the current native frontier")
    owner.require_identity()
    from .red_train_lorelei import FrozenTrainLoreleiStoryController
    train_owner = type(owner) is FrozenTrainLoreleiStoryController
    if train_owner and history is None:
        raise ValueError("TRAIN League feedback requires authenticated native history")
    champion = target is CHAMPION_PLAYER_TARGET
    skill: RedCartridgeChampionSkill | RedCartridgeLoreleiSkill
    if champion:
        skill = RedCartridgeChampionSkill(
            runtime,actions,route.route_world,recovery_controller=owner.controller_name,
            rematch=rematch,maximum_level_deficit=maximum_level_deficit,
        )
    else:
        skill = RedCartridgeLoreleiSkill(
            runtime, actions, route.route_world, recovery_controller=owner.controller_name,
            objective_id=target.objective_id, rematch=rematch,
            maximum_level_deficit=maximum_level_deficit,
            development_retry_reentry=(development_retry_reentry
                                       and target.objective_id == "defeat_lorelei"),
        )
    availability = skill.availability(runtime.adapter.observe().game_state)
    if record is not None:
        record("league-availability", dict(objective=target.objective_id,
               executable=availability.executable, reason=availability.reason))
    if not availability.executable:
        return None
    contract = owner.contract
    lance = target.objective_id == "defeat_lance"
    if lance and contract.trainer_identity != (247, 47, 1):
        raise ValueError("League Lance quote needs its exact supported first set")
    quote = trainer_party_quote(route.rom, contract.trainer_identity[0],
                                contract.trainer_identity[2],
                                **({"allow_final_class": True} if lance else {}))
    if quote.expected_victory_money != contract.victory_money:
        raise ValueError("League preview and native payout contract differ")
    challenge = OptionChallenge.from_levels(
        combat_levels=combat_levels, opponent_levels=tuple(m.level for m in quote.party),
    )
    origin = runtime.emulator.save_state_bytes()
    consumed, terminal, lost = False, None, False

    def execute():
        nonlocal consumed, terminal, lost
        if consumed or runtime.emulator.save_state_bytes() != origin:
            raise ValueError("League challenge is stale or consumed")
        consumed = True
        first_actions, first_frames = actions.actions_executed, runtime.emulator.frame_count
        previous = owner.last_completion if train_owner else None
        calls_before = owner.battler.calls if train_owner else None
        aftermath = None
        try:
            report = skill.execute()
            evidence = dict(status="won", report=asdict(report))
        except LoreleiStoryBattleStopped:
            result, after = owner.last_completion, runtime.reader.read()
            if (result is None or result.outcome != "lost" or not result.field_ready
                or not _field_ready(runtime)
                or event_flag_is_set(after.event_flags, int(target.event))
                or after.badge_bits != before.badge_bits or after.bag_items != before.bag_items
                or after.player_money != before.player_money // 2):
                raise
            if history is None:
                raise ValueError(
                    "ordinary League loss requires actual authenticated history"
                ) from None
            aftermath = history()
            lost = True
            evidence = dict(status="lost", native_loss_verified=True,
                            outcome=result.public_dict(), teacher_fallback=False)
        if train_owner:
            if not lost:
                aftermath = history()
            evidence["battle"] = owner.completion_evidence(
                previous, calls_before, runtime.reader.read(), aftermath,
                outcome="lost" if lost else "won",
            )
        terminal = runtime.emulator.save_state_bytes()
        if progress_objective_ref is not None:
            evidence.update(selected_objective=objective_ref,
                            native_prerequisite=target.objective_id,
                            objective_completed=not lost and objective_ref == target.objective_id)
        if record is not None:
            record("league-outcome", dict(objective=target.objective_id, **evidence))
        return GoalExecutionReport(actions.actions_executed-first_actions,
                                   runtime.emulator.frame_count-first_frames, evidence)

    def verify(_report):
        if (terminal is None or terminal != runtime.emulator.save_state_bytes()
                or not _field_ready(runtime)):
            return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        if lost:
            return GoalVerification.failed(GoalFailureReason.RECOVERY_REQUIRED)
        return (GoalVerification.succeeded()
                if event_flag_is_set(runtime.reader.read().event_flags, int(target.event))
                and (not champion or runtime.reader.read().map_id == MapId.HALL_OF_FAME)
                else GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED))

    binding = ExecutableGoalBinding(
        "league-model-choice:"+sha256(origin).hexdigest(), GoalKind.ADVANCE_STORY,
        .1, .2, execute, verify, maximum_cash_debit=None,
        story_objective_ref=objective_ref,
    )
    return binding, challenge
