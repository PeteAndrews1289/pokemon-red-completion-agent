"""Model-selectable owned Cut-carrier exchange using existing native mechanics.

Demand comes from conditional routes to observed legal story destinations.
Private dependency probes never execute. No gym/trainer execution
is bundled. Compatibility/PC/teaching are disclosed mechanical support.
"""
from collections import Counter
from dataclasses import asdict, dataclass, replace
from hashlib import sha256

from .gen1_field_moves import GEN1_FIELD_MOVE_IDS
from .goal_manager import GoalFailureReason, GoalKind
from .goal_manager_runtime import ExecutableGoalBinding, GoalExecutionReport, GoalVerification
from .observation import ItemId
from .player_option_challenge import OptionChallenge
from .player_option_story_unit import OptionStoryUnit
from .provenance import canonical_sha256
from .red_battle_catalog import RED_BATTLE_CATALOG, pokemon_red_move_ref
from .red_field_carrier_custody import FieldCarrierCustody, settle_pending_field_carrier
from .red_field_capability_demand import observed_cut_dependencies, post_return_field_moves, dependency_witness_sha256
from .red_goal_skills import _POKEMON_CENTER_MAPS
from .red_machine_teaching import execute_machine_lesson, plan_machine_lesson, plan_observed_machine_lesson
from .red_pc_storage import close_generic_pc_session, deposit_party_member, face_pc_boundary, open_bills_pc, withdraw_box_member
from .red_player_field_goals import _field_ready, nearest_reachable_player_center
from .red_player_party_guard import RedPlayerPartyGuard
from .red_player_party_loan import _stock, _walk, party_loan_return_center


class FieldCarrierSettlementError(RuntimeError):
    """The primary exchange failure and the separate native return both failed."""


@dataclass(frozen=True)
class CarrierQuote:
    carrier_ref: str
    box_index: int
    box_slot: int
    species_id: int
    level: int
    experience: int
    displaced_ref: str
    displaced_slot: int
    center: int
    moves: tuple[int, ...]
    pp: tuple[int, ...]
    lesson: object
    objective_ref: str
    dependency_witness_sha256: str


def _party_resources(runtime):
    guard = runtime.adapter.party_guard
    raw = runtime.reader.read()
    return {r: (raw.party_moves[i], raw.party_pp[i], raw.party_status[i], raw.party_hp[i])
            for i, r in enumerate(guard.reader.preparation_specimen_refs())}


def field_carrier_branches(runtime, actions, observation, *, rom, route, combat_refs, preparation=None, on_commit=None, dependency_witnesses=None, include_other_boxes=False):
    """Read-only options from current box evidence; never select a donor/target."""
    if type(include_other_boxes) is not bool:
        raise ValueError("other-box carrier permission must be boolean")
    if dependency_witnesses is not None:
        from .red_field_capability_demand import CutDependencyWitness
        if (type(dependency_witnesses) is not tuple or not dependency_witnesses
                or any(not isinstance(w, CutDependencyWitness) or w.cut_count <= 0 for w in dependency_witnesses)):
            raise ValueError("explicit carrier dependencies require typed positive Cut witnesses")
    guard = getattr(runtime.adapter, "party_guard", None)
    raw = runtime.reader.read()
    legal = {o.id for o in runtime.adapter.graph.available_objectives(observation.game_state)}
    if (not isinstance(guard, RedPlayerPartyGuard) or guard.storage_reader is None
            or guard.field_carrier is not None or not _field_ready(runtime)
            or (not legal and dependency_witnesses is None) or raw.bag_items is None
            or dict(raw.bag_items).get(int(ItemId.HM01_CUT), 0) <= 0
            or raw.party_count != 6 or raw.party_moves is None or raw.party_pp is None
            or any(15 in moves for moves in raw.party_moves)):
        return ()
    guard.verify_active_roster_restored()
    if dependency_witnesses is not None:
        from .observation import Badge
        if not int(raw.badge_bits or 0) & int(Badge.CASCADE):
            return ()
    witnesses = (observed_cut_dependencies(runtime, observation, route=route)
                 if dependency_witnesses is None else dependency_witnesses)
    if not witnesses:
        return ()
    # One mechanical exchange per carrier/donor/lesson,not per objective.
    representative = min(witnesses, key=lambda w: canonical_sha256(asdict(w))).objective_ref
    witness_sha = dependency_witness_sha256(witnesses)
    refs = guard.reader.preparation_specimen_refs()
    if set(refs) != set(guard.refs) or not set(combat_refs) <= set(refs):
        return ()
    center = nearest_reachable_player_center(runtime, route=route, centers=frozenset(int(m) for m in _POKEMON_CENTER_MAPS))
    if center is None:
        return ()
    current = runtime.reader.read_current_box_state()
    counts = runtime.reader.read_all_box_states().counts
    if not include_other_boxes and counts[current.box_index] >= observation.collection_observation.box_capacity:
        return ()
    identities = runtime.reader.read_box_specimen_identities()
    identity_counts = Counter(refs) + Counter(m.preparation_ref for m in identities)
    moves_by_box = {i: {m.box_slot: m for m in runtime.reader.read_box_move_members(i)}
        for i in (range(len(counts)) if include_other_boxes else (current.box_index,))
        if counts[i] < observation.collection_observation.box_capacity}
    source = runtime.emulator.save_state_bytes()
    rows = []
    for member in identities:
        if (member.box_index not in moves_by_box or member.preparation_ref in guard.refs
                or identity_counts[member.preparation_ref] != 1):
            continue
        boxed = moves_by_box[member.box_index].get(member.box_slot)
        if boxed is None:
            continue
        lessons = [None] if 15 in boxed.moves else []
        for slot in range(1, 5) if 15 not in boxed.moves else ():
            prior = boxed.moves[slot - 1]
            if prior and (prior in GEN1_FIELD_MOVE_IDS or
                    RED_BATTLE_CATALOG.resolve_move(pokemon_red_move_ref(prior)).category != "status"):
                continue
            try:
                lessons.append(plan_observed_machine_lesson(rom, bag_items=raw.bag_items,
                    species_id=member.species_id, moves=boxed.moves, item_id=int(ItemId.HM01_CUT),
                    party_slot=6, replace_slot=slot))
            except ValueError:
                continue
        for lesson in lessons:
            helper_moves = set(boxed.moves) | {15}
            required = GEN1_FIELD_MOVE_IDS & {m for row in raw.party_moves for m in row}
            for index, ref in enumerate(refs):
                if ref in combat_refs:
                    continue
                remaining = {m for i, row in enumerate(raw.party_moves) if i != index for m in row}
                if not required <= remaining | helper_moves:
                    continue
                quote = CarrierQuote(member.preparation_ref, member.box_index, member.box_slot,
                    member.species_id, member.level, member.experience, ref, index + 1, center, boxed.moves, boxed.pp, lesson, representative, witness_sha)
                rows.append((_carrier_binding(runtime, actions, rom, route, quote, source, preparation, on_commit,
                    **({"allow_box_switch": True} if include_other_boxes else {})),
                             OptionChallenge(False, False, 0.0, 0.0, 0.0)))
    if runtime.emulator.save_state_bytes() != source:
        raise ValueError("field-carrier discovery changed native state")
    return tuple(rows)


def _carrier_binding(runtime, actions, rom, route, quote, source, preparation=None, on_commit=None, *, allow_box_switch=False):
    original_guard = runtime.adapter.party_guard
    used, terminal, receipt = False, None, None

    def execute():
        nonlocal used, terminal, receipt
        if used or runtime.emulator.save_state_bytes() != source or not _field_ready(runtime):
            raise ValueError("field-carrier exchange is stale or consumed")
        original_guard.verify_active_roster_restored()
        used = True
        a, f = actions.actions_executed, runtime.emulator.frame_count
        # This is not a zero-cash-risk certificate. Existing route support owns
        # encounters/faint boundaries; no additional trainer permission is given.
        if (runtime.reader.read().map_id, runtime.reader.read().player_y,
                runtime.reader.read().player_x) != (quote.center, 3, 3):
            approach = replace(route, destination_map=quote.center, destination_at=(3, 3))
            approach(actions, runtime.reader, runtime.emulator)
        if not _field_ready(runtime):
            raise ValueError("field-carrier approach lacks settled Center control")
        original_guard.verify_active_roster_restored()
        # Recheck exact observed stock immediately before the first PC input.
        members = [m for m in runtime.reader.read_box_specimen_identities()
                   if m.preparation_ref == quote.carrier_ref]
        if (len(members) != 1 or members[0].box_index != quote.box_index
                or members[0].box_slot != quote.box_slot
                or (not allow_box_switch and runtime.reader.read_current_box_state().box_index != quote.box_index)):
            raise ValueError("field-carrier storage quote is stale")
        before = runtime.reader.read()
        protected_party, stock = _party_resources(runtime), _stock(runtime)
        dex, pc = runtime.reader.read_pokedex_state(), runtime.reader.read_pc_items()
        custody = FieldCarrierCustody("pending", 15, quote.objective_ref, quote.displaced_ref,
            quote.carrier_ref, quote.species_id, quote.level, quote.experience,
            original_guard.before, original_guard.refs, original_guard.loanable_refs,
            sha256(source).hexdigest(), preparation)
        runtime.adapter.party_guard = replace(original_guard, field_carrier=custody)
        try:
            _walk(runtime, actions, route.route_world, quote.center, (4, 13))
            face_pc_boundary(actions, runtime.reader, "up")
            open_bills_pc(actions, runtime.reader)
            if runtime.reader.read_current_box_state().box_index != quote.box_index:
                if not allow_box_switch:
                    raise ValueError("carrier quote cannot change boxes")
                from .red_pc_storage import switch_box
                if not switch_box(actions, runtime.reader, target_box_index=quote.box_index).passed:
                    raise ValueError("carrier box switch did not verify")
            active = runtime.adapter.party_guard.reader.preparation_specimen_refs()
            if active[quote.displaced_slot - 1] != quote.displaced_ref:
                raise ValueError("field-carrier displaced individual changed")
            if not deposit_party_member(actions, runtime.reader, party_slot=quote.displaced_slot,
                    expected_species_id=before.party_species_ids[quote.displaced_slot - 1]).passed:
                raise ValueError("field-carrier original deposit failed")
            targets = [m for m in runtime.reader.read_box_specimen_identities()
                       if m.preparation_ref == quote.carrier_ref]
            if len(targets) != 1 or targets[0].box_index != quote.box_index:
                raise ValueError("field-carrier withdrawal identity is ambiguous")
            if not withdraw_box_member(actions, runtime.reader, box_slot=targets[0].box_slot,
                                       expected_species_id=quote.species_id).passed:
                raise ValueError("field-carrier withdrawal failed")
            close_generic_pc_session(actions, runtime.reader)
            active = runtime.adapter.party_guard.reader.preparation_specimen_refs()
            if len(active) != 6 or active[-1] != quote.carrier_ref:
                raise ValueError("field-carrier withdrawn individual differs")
            if quote.lesson is not None:
                actual = plan_machine_lesson(rom, runtime.reader, item_id=quote.lesson.item_id,
                    party_slot=6, replace_slot=quote.lesson.replace_slot)
                if actual != quote.lesson:
                    raise ValueError("field-carrier actual lesson differs from quote")
                execute_machine_lesson(runtime.emulator, actions, runtime.reader, actual, rom=rom)
            _walk(runtime, actions, route.route_world, quote.center, (3, 3))
            after = runtime.reader.read()
            current_resources = _party_resources(runtime)
            deposited = [m for m in runtime.reader.read_box_specimen_identities() if m.preparation_ref == quote.displaced_ref]
            boxed_donor = (None if len(deposited) != 1 else next((m for m in runtime.reader.read_box_move_members(deposited[0].box_index) if m.box_slot == deposited[0].box_slot), None))
            expected_moves, expected_pp = list(quote.moves), list(quote.pp)
            if quote.lesson is not None:
                expected_moves[quote.lesson.replace_slot-1] = 15
                expected_pp[quote.lesson.replace_slot-1] = RED_BATTLE_CATALOG.resolve_move(pokemon_red_move_ref(15)).max_pp
            remaining = set(original_guard.refs) - {quote.displaced_ref}
            if (stock != _stock(runtime) or before.player_money != after.player_money
                    or before.bag_items != after.bag_items or before.badge_bits != after.badge_bits
                    or before.event_flags != after.event_flags
                    or runtime.reader.read_pokedex_state() != dex or runtime.reader.read_pc_items() != pc
                    or runtime.reader.read_current_box_state().box_index != quote.box_index
                    or boxed_donor is None or boxed_donor.moves != protected_party[quote.displaced_ref][0]
                    or boxed_donor.pp != protected_party[quote.displaced_ref][1]
                    or current_resources[quote.carrier_ref][:2] != (tuple(expected_moves), tuple(expected_pp))
                    or any(protected_party[r] != current_resources[r] for r in remaining)
                    or not _field_ready(runtime)):
                raise ValueError("field-carrier PC exchange changed protected stock or resources")
            committed = replace(custody, phase="active")
            candidate_guard = replace(original_guard, field_carrier=committed)
            candidate_guard.verify_authorized_active_roster()
            if on_commit is not None:
                on_commit(committed)
            runtime.adapter.party_guard = candidate_guard
        except BaseException as primary:
            try:
                settle_pending_field_carrier(runtime, actions, route.route_world)
            except BaseException as secondary:
                record = getattr(actions, "record_diagnostic_event", None)
                if callable(record):
                    record("field_carrier_settlement_failure", dict(
                        primary_error_type=type(primary).__name__, settlement_error_type=type(secondary).__name__,
                        partial_costs_retained=True, pending_custody_retained=True))
                from .red_autonomous_player import _exception_chain
                failure = FieldCarrierSettlementError("field-carrier return failed: " + type(secondary).__name__)
                failure.settlement_error_chain = _exception_chain(secondary)
                raise failure from primary
            raise
        terminal = runtime.emulator.save_state_bytes()
        receipt = GoalExecutionReport(actions.actions_executed-a, runtime.emulator.frame_count-f,
            dict(mechanic="owned_field_carrier_exchange", selected_exchange_authority="model_or_disclosed_equivalent_choice",
                 objective_completed=False, field_move=15, active_field_carrier=True,
                 objective=quote.objective_ref, dependency_witness_sha256=quote.dependency_witness_sha256,
                 custody_sha256=canonical_sha256(committed.private_dict()), original_baseline_preserved=True,
                 trainer_battles=0, no_new_combat_role=True, learned_menu_execution=False,
                 source_sha256=sha256(source).hexdigest(), terminal_sha256=sha256(terminal).hexdigest()))
        return receipt

    def verify(report):
        if receipt is None or report is not receipt or runtime.emulator.save_state_bytes() != terminal:
            return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        runtime.adapter.party_guard.verify_authorized_active_roster()
        return GoalVerification.succeeded() if _field_ready(runtime) else GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)

    return ExecutableGoalBinding("pokemon.red:owned-field-carrier:" + sha256(source).hexdigest()+":"+
        canonical_sha256(asdict(quote)) + (":box-switch" if allow_box_switch else ""), GoalKind.ADVANCE_STORY, 0.08, 0.15, execute, verify,
        maximum_cash_debit=None, story_objective_ref=quote.objective_ref, story_approach_only=True,
        story_unit=OptionStoryUnit("interaction", True))


def field_carrier_return_binding(runtime, actions, *, route, on_return=None, on_unavailable=None):
    """A separate selected roster return once the quoted dependency is fulfilled."""
    guard = runtime.adapter.party_guard
    custody = guard.field_carrier
    if (custody is None or custody.phase != "active" or not _field_ready(runtime)
            or custody.objective_ref not in runtime.adapter.graph.completed_ids(runtime.adapter.observe().game_state)):
        return None
    guard.verify_authorized_active_roster()
    # Fulfillment of one selection does not make its field capability obsolete.
    # Protect access required by any currently legal destination after return.
    after_moves = post_return_field_moves(runtime, custody)
    if observed_cut_dependencies(runtime, runtime.adapter.observe(), route=route, post_return_moves=after_moves):
        return None
    center_quote = party_loan_return_center(
        runtime, route.route_world, allow_cut=(custody.move_id == 15),
    )
    if center_quote is None:
        from .goal_manager import GoalAvailability, GoalUnavailableReason, GoalOpportunity
        unavailable = GoalOpportunity(
            "pokemon.red:field-carrier-return:" + sha256(runtime.emulator.save_state_bytes()).hexdigest(),
            GoalKind.MANAGE_STORAGE, GoalAvailability.UNAVAILABLE,
            unavailable_reason=GoalUnavailableReason.MISSING_CAPABILITY,
        )
        if on_unavailable is not None:
            on_unavailable(unavailable)
        record = getattr(actions, "record_diagnostic_event", None)
        if callable(record):
            record("field_carrier_return_unavailable", dict(
                reason="no_executable_walking_center", binding_ref=unavailable.binding_ref,
                native_state_unchanged=True, active_custody_retained=True,
            ))
        return None
    source, used, terminal, receipt = runtime.emulator.save_state_bytes(), False, None, None

    def execute():
        nonlocal used, terminal, receipt
        if used or runtime.emulator.save_state_bytes() != source or not _field_ready(runtime):
            raise ValueError("field-carrier return is stale or consumed")
        if party_loan_return_center(
            runtime, route.route_world, allow_cut=(custody.move_id == 15),
        ) != center_quote:
            raise ValueError("field-carrier return quote changed before input")
        used = True
        a,f = actions.actions_executed,runtime.emulator.frame_count
        runtime.adapter.party_guard = replace(guard, field_carrier=replace(custody, phase="pending"))
        try:
            settle_pending_field_carrier(runtime, actions, route.route_world)
        except BaseException:
            if (runtime.emulator.save_state_bytes() == source
                    and actions.actions_executed == a and runtime.emulator.frame_count == f
                    and not runtime.emulator.pressed_buttons and _field_ready(runtime)):
                guard.verify_authorized_active_roster()
                runtime.adapter.party_guard = guard
            raise
        if on_return is not None:
            on_return(custody)
        terminal = runtime.emulator.save_state_bytes()
        receipt = GoalExecutionReport(actions.actions_executed-a,runtime.emulator.frame_count-f,
            dict(mechanic="selected_field_carrier_return", original_roster_restored=True,
                 learned_menu_execution=False, objective_completed=False))
        return receipt

    def verify(report):
        runtime.adapter.party_guard.verify_active_roster_restored()
        return (GoalVerification.succeeded() if report is receipt and receipt is not None
                and runtime.emulator.save_state_bytes() == terminal and _field_ready(runtime)
                else GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED))
    return ExecutableGoalBinding("pokemon.red:field-carrier-return:"+sha256(source).hexdigest(),
        GoalKind.MANAGE_STORAGE,0.08,0.15,execute,verify,maximum_cash_debit=None)
