"""Selected owned-machine lessons for a current-box evolution precursor.

Discovery quotes observed storage moves; only the selected bundle may borrow
the declared party slot. Existing native PC and lesson executors own inputs.
"""

from collections import Counter
from dataclasses import asdict, dataclass
from hashlib import sha256

from .goal_manager import GoalFailureReason, GoalKind
from .goal_manager_runtime import ExecutableGoalBinding, GoalExecutionReport, GoalVerification
from .living_dex_option_value import (
    LivingDexOptionAvailability, LivingDexOptionCandidate, LivingDexOptionFeatures,
    LivingDexOptionKind,
)
from .player_option_challenge import OptionChallenge
from .provenance import canonical_sha256
from .red_autonomous_player import _exception_chain
from .red_battle_catalog import RED_BATTLE_CATALOG, pokemon_red_move_ref
from .red_collection import red_internal_species_number, red_species_ref
from .red_goal_skills import _POKEMON_CENTER_MAPS
from .red_live_option_menu import RedLiveSupplementalOption, supplemental_live_option
from .red_machine_teaching import (
    RedMachineLesson, execute_machine_lesson, plan_machine_lesson, plan_observed_machine_lesson,
)
from .red_pc_storage import (
    close_generic_pc_session, deposit_party_member, face_pc_boundary,
    open_bills_pc, withdraw_box_member,
)
from .red_player_field_goals import _field_ready
from .red_player_owned_machines import direct_attack_capacity
from .red_player_party_guard import RedPlayerPartyGuard
from .red_player_party_loan import _stock, _walk, restore_guarded_party_loan


@dataclass(frozen=True)
class BoxedMachineBundle:
    target_ref: str
    box_index: int
    box_slot: int
    loan_ref: str
    loan_slot: int
    lesson: RedMachineLesson


@dataclass(frozen=True)
class BoxedMachineChoice:
    bundle: BoxedMachineBundle
    option: RedLiveSupplementalOption


class BoxedMachineSettlementError(RuntimeError):
    """A primary failure and its separately recorded custody-return failure."""


def _party_moves_by_ref(runtime):
    guard = runtime.adapter.party_guard
    raw = runtime.reader.read()
    refs = guard.reader.preparation_specimen_refs()
    return {ref: (raw.party_moves[i], raw.party_pp[i], raw.party_status[i], raw.party_hp[i])
            for i, ref in enumerate(refs)}


def boxed_frontier_machine_options(runtime, actions, observation, *, rom, world):
    """Retain the existing public option-only interface."""
    return tuple(row.option for row in quoted_boxed_frontier_machine_options(
        runtime, actions, observation, rom=rom, world=world))


def quoted_boxed_frontier_machine_options(runtime, actions, observation, *, rom, world):
    """Finite read-only options at an observed Center and current box only."""
    guard = getattr(runtime.adapter, "party_guard", None)
    registration = runtime.registration_policy
    raw = runtime.reader.read()
    if (not isinstance(guard, RedPlayerPartyGuard) or guard.storage_reader is None
            or len(guard.loanable_refs) != 1 or registration is None
            or raw.map_id not in _POKEMON_CENTER_MAPS or not _field_ready(runtime)
            or raw.party_count != 6 or raw.bag_items is None
            or any(getattr(raw, f, None) is None for f in
                   ("party_moves", "party_pp", "party_status", "party_hp"))):
        return ()
    guard.verify_active_roster_restored()
    refs = guard.reader.preparation_specimen_refs()
    if set(refs) != set(guard.refs):
        return ()
    loan_ref = next(iter(guard.loanable_refs))
    loan_slot = refs.index(loan_ref) + 1
    boxes = runtime.reader.read_all_box_states()
    current = runtime.reader.read_current_box_state()
    if boxes.counts[current.box_index] >= observation.collection_observation.box_capacity:
        return ()
    identities = runtime.reader.read_box_specimen_identities()
    ref_counts = Counter(refs) + Counter(m.preparation_ref for m in identities)
    frontier = {
        source for source, target, _ in guard.edges
        if registration.evolution_allowed(observation.collection_observation,
            red_species_ref(red_internal_species_number(source)),
            red_species_ref(red_internal_species_number(target)))
    }
    source_state = runtime.emulator.save_state_bytes()
    move_rows = {m.box_slot: m for m in runtime.reader.read_box_move_members(current.box_index)}
    rows = []
    for identity in identities:
        if (identity.box_index != current.box_index or identity.species_id not in frontier
                or identity.preparation_ref in guard.refs
                or ref_counts[identity.preparation_ref] != 1):
            continue
        member = move_rows[identity.box_slot]
        before = direct_attack_capacity(identity.species_id, member.moves, member.pp)
        for item, quantity in sorted(raw.bag_items):
            if not 196 <= item <= 250 or quantity <= 0:
                continue
            for replace_slot in range(1, 5):
                try:
                    lesson = plan_observed_machine_lesson(rom, bag_items=raw.bag_items,
                        species_id=identity.species_id, moves=member.moves,
                        item_id=item, party_slot=6, replace_slot=replace_slot)
                except ValueError:
                    continue
                move = RED_BATTLE_CATALOG.resolve_move(pokemon_red_move_ref(lesson.move_id))
                if move.power <= 0 or move.effect_flags & {"ohko", "self_destruct", "fixed_damage"}:
                    continue
                moves, pp = list(member.moves), list(member.pp)
                moves[replace_slot-1], pp[replace_slot-1] = lesson.move_id, move.max_pp
                after = direct_attack_capacity(identity.species_id, tuple(moves), tuple(pp))
                if after <= before:
                    continue
                bundle = BoxedMachineBundle(identity.preparation_ref, identity.box_index,
                    identity.box_slot, loan_ref, loan_slot, lesson)
                binding = _boxed_machine_binding(runtime, actions, world, rom, bundle,
                    source_state, raw, tuple(moves), tuple(pp), before, after)
                candidate = LivingDexOptionCandidate(
                    binding_ref=binding.binding_ref,
                    availability=LivingDexOptionAvailability.AVAILABLE,
                    features=LivingDexOptionFeatures(LivingDexOptionKind.DEVELOP,
                        0., (after-before)/after, 0., .08, .08, 0., 0., .2, .5),
                    challenge=OptionChallenge(False, False, 0., 0., 0.))
                rows.append(BoxedMachineChoice(bundle, supplemental_live_option(binding, candidate)))
    if runtime.emulator.save_state_bytes() != source_state:
        raise ValueError("boxed-machine discovery changed native state")
    if len({row.option.binding.binding_ref for row in rows}) != len(rows):
        raise ValueError("boxed-machine discovery repeats a bundle")
    return tuple(rows)


def _boxed_machine_binding(runtime, actions, world, rom, bundle, source, before,
                          expected_moves, expected_pp, capacity_before, capacity_after):
    guard = runtime.adapter.party_guard
    original_stock = _stock(runtime)
    original_party = _party_moves_by_ref(runtime)
    dex, pc = runtime.reader.read_pokedex_state(), runtime.reader.read_pc_items()
    bag = dict(before.bag_items)
    consumed = int(bundle.lesson.item_id >= 201)
    bag[bundle.lesson.item_id] -= consumed
    expected_bag = {i:q for i,q in bag.items() if q}
    claimed, terminal, receipt = False, None, None

    def repay():
        close_generic_pc_session(actions,runtime.reader)
        restore_guarded_party_loan(runtime,actions,world)
        _walk(runtime,actions,world,before.map_id,(before.player_y,before.player_x))
        guard.verify_active_roster_restored()

    def protected():
        guard.verify_active_roster_restored()
        raw = runtime.reader.read()
        identities = [m for m in runtime.reader.read_box_specimen_identities()
                      if m.preparation_ref == bundle.target_ref]
        if len(identities) != 1 or identities[0].box_index != bundle.box_index:
            return False
        target = identities[0]
        boxed = next((m for m in runtime.reader.read_box_move_members(target.box_index)
                      if m.box_slot == target.box_slot),None)
        fields = ("map_id","player_x","player_y","player_money","badge_bits",
                  "event_flags","battle_state","party_count")
        return (all(getattr(raw,f)==getattr(before,f) for f in fields)
            and _stock(runtime)==original_stock
            and _party_moves_by_ref(runtime)==original_party
            and dict(raw.bag_items or ())==expected_bag
            and runtime.reader.read_pokedex_state()==dex
            and runtime.reader.read_pc_items()==pc
            and runtime.reader.read_current_box_state().box_index==bundle.box_index
            and boxed is not None and boxed.moves==expected_moves and boxed.pp==expected_pp
            and _field_ready(runtime))

    def execute():
        nonlocal claimed,terminal,receipt
        if claimed or runtime.emulator.save_state_bytes()!=source or not _field_ready(runtime):
            raise ValueError("boxed-machine bundle is stale or consumed")
        guard.verify_active_roster_restored();claimed=True
        a,f=actions.actions_executed,runtime.emulator.frame_count
        settlement_started=False
        try:
            _walk(runtime,actions,world,before.map_id,(4,13))
            face_pc_boundary(actions,runtime.reader,"up")
            open_bills_pc(actions,runtime.reader)
            if runtime.reader.read_current_box_state().box_index != bundle.box_index:
                raise ValueError("boxed-machine current box changed")
            if not deposit_party_member(actions,runtime.reader,party_slot=bundle.loan_slot,
                    expected_species_id=before.party_species_ids[bundle.loan_slot-1]).passed:
                raise ValueError("boxed-machine loan deposit failed")
            if not withdraw_box_member(actions,runtime.reader,box_slot=bundle.box_slot,
                    expected_species_id=bundle.lesson.species_id).passed:
                raise ValueError("boxed-machine target withdrawal failed")
            close_generic_pc_session(actions,runtime.reader)
            active=guard.reader.preparation_specimen_refs()
            if (len(active)!=6 or active[-1]!=bundle.target_ref
                    or set(guard.refs)-set(active)!={bundle.loan_ref}):
                raise ValueError("boxed-machine borrowed identity differs")
            guard.verify()
            actual=plan_machine_lesson(rom,runtime.reader,item_id=bundle.lesson.item_id,
                party_slot=6,replace_slot=bundle.lesson.replace_slot)
            if actual!=bundle.lesson:
                raise ValueError("boxed-machine actual lesson differs from its quote")
            execute_machine_lesson(runtime.emulator,actions,runtime.reader,actual,rom=rom)
            settlement_started=True;repay()
        except BaseException as primary:
            if not settlement_started:
                try:
                    settlement_started=True;repay()
                except BaseException as secondary:
                    record=getattr(actions,"record_diagnostic_event",None)
                    if callable(record):
                        record("boxed_machine_return_failure",dict(
                            primary_error_chain=_exception_chain(primary),
                            settlement_error_chain=_exception_chain(secondary),
                            partial_costs_retained=True))
                    raise BoxedMachineSettlementError(
                        "boxed-machine return failed: "+type(secondary).__name__+": "+str(secondary)
                    ) from primary
            raise
        if not protected():
            raise RuntimeError("boxed-machine lesson changed protected native state")
        terminal=runtime.emulator.save_state_bytes()
        receipt=GoalExecutionReport(actions.actions_executed-a,runtime.emulator.frame_count-f,
            dict(mechanic="owned_current_box_frontier_machine_lesson",
                selected_bundle_authority="model_or_disclosed_equivalent_choice",
                lesson=asdict(bundle.lesson),normal_controller_inputs=True,
                declared_party_loan_repaid=True,stock_xp_ownership_preserved=True,
                current_box_only=True,current_center_only=True,
                capacity_before=capacity_before,capacity_after=capacity_after,
                capacity_proxy="current_PP_times_power_accuracy_STAB_not_damage_or_win",
                machine_consumed=consumed,cash_debit=0,xp_gained=0,registrations_gained=0))
        return receipt

    def verify(report):
        return (GoalVerification.succeeded() if receipt is not None and report is receipt
            and terminal==runtime.emulator.save_state_bytes() and protected()
            else GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED))

    return ExecutableGoalBinding("pokemon.red:boxed-frontier-machine:"+sha256(source).hexdigest()
        +":"+canonical_sha256(asdict(bundle)),GoalKind.DEVELOP_TEAM,.08,0.,execute,verify,
        maximum_cash_debit=0)
