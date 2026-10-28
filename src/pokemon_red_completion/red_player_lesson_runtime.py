"""One bounded TRAIN demonstration through existing live goal bindings.

Caller supplies an already authenticated isolated TRAIN source and runtime
factory. This module selects no source, opens no ROM, resets no save and starts
no campaign. Every declaration precedes input; unreadable/partial attempts keep
diagnostics but do not become invented successful or comparative examples.
"""

import json
from collections import Counter
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, replace
from hashlib import sha256
from time import monotonic

from .bootstrap import DEFAULT_NEW_GAME_TIMING
from .executor import (
    ControllerActionBudgetExhausted,
    CountingExecutor,
    FrameSafeExecutor,
    NativeLessonController,
)
from .goal_manager import GoalAvailability, GoalDecisionOutcome, GoalKind, GoalUnavailableReason
from .goal_manager_runtime import CompletionFirstGoalTeacher, GoalExecutionReport, GoalVerification
from .party_preparation import PreparationMember, PreparationPurpose
from .player_readiness import PlayerReadiness
from .post_battle_strategy import context_after_recovery
from .provenance import canonical_sha256
from .red_live_option_menu import build_red_live_forced_singleton, build_red_live_option_set
from .red_native_curriculum import (
    CHALLENGE_CONTRACT,
    CHALLENGE_OUTCOME_SCHEMA,
    CHALLENGE_PLAN_SCHEMA,
    PREPARATION_CONTRACT,
    PREPARATION_OUTCOME_SCHEMA,
    PREPARATION_PLAN_SCHEMA,
    READINESS_CONTRACT,
    READINESS_OUTCOME_SCHEMA,
    READINESS_PLAN_SCHEMA,
    RESOURCE_CONTRACT,
    RESOURCE_OUTCOME_SCHEMA,
    RESOURCE_PLAN_SCHEMA,
    STORY_UNIT_CONTRACT,
    STORY_UNIT_OUTCOME_SCHEMA,
    STORY_UNIT_PLAN_SCHEMA,
    curriculum_projection,
    publish_declaration,
    publish_outcome,
)
from .red_player_curriculum import NativePlayerCurriculum
from .red_player_economy import snapshot_document
from .red_player_lesson import capture_player_lesson_snapshot, validate_snapshot
from .red_player_resource_lesson import RESOURCE_LESSON_KINDS
from .red_player_support import PlayerBudgetStop, RedPlayerSupport
from .red_registered_observation import project_registered_observation
from .registered_collection import REGISTERED_OBJECTIVE
from .resource_economy_observation import EconomySnapshot


@dataclass(frozen=True)
class NativePlayerBoundary:
    """One coherent observed boundary shared by actor inference and TRAIN recording.

    Private snapshot identities establish roles only; the policy receives their
    measured readiness, not the identities or the teacher's selected target.
    """

    observation: object
    registered: object
    lesson_snapshot: dict
    readiness: PlayerReadiness
    economy: EconomySnapshot
    state: bytes


def player_diagnostic_state(observation, *, registration_policy=None):
    """Already decoded facts only; unknown remains None, not observed zero.

    This private diagnostic projection is deliberately outside policy features.
    No reserve-opponent roster, future RNG or memory address is included.
    """
    raw = observation.raw
    fields = (
        "map_id",
        "player_x",
        "player_y",
        "battle_state",
        "battle_result",
        "badge_bits",
        "player_money",
        "bag_items",
        "repel_remaining_steps",
        "party_count",
        "party_species_ids",
        "party_levels",
        "party_hp",
        "party_max_hp",
        "party_stats",
        "party_status",
        "party_moves",
        "party_pp",
        "active_party_index",
        "active_party_species_id",
        "active_party_level",
        "active_party_hp",
        "active_party_max_hp",
        "active_party_stats",
        "active_party_status",
        "active_party_moves",
        "active_party_pp",
        "enemy_species_id",
        "enemy_level",
        "enemy_hp",
        "enemy_max_hp",
        "enemy_status",
        "player_stat_stages",
        "enemy_stat_stages",
        "player_disabled_move_slot",
        "player_disable_turns",
        "player_confused",
        "enemy_confused",
        "enemy_using_trapping_move",
    )
    facts = {name: getattr(raw, name, None) for name in fields}
    facts["battle_fields_are_live"] = (
        None if facts["battle_state"] is None else facts["battle_state"] in (1, 2)
    )
    facts["outside_battle_enemy_fields_may_be_stale"] = True
    facts["party_pp_encoded"] = facts.pop("party_pp")
    facts["party_pp_current"] = facts["party_pp_maximum"] = None
    if facts["party_moves"] is not None and facts["party_pp_encoded"] is not None:
        from .red_party_pp import decode_red_party_pp

        decoded = [
            decode_red_party_pp(moves, quantities).moves
            for moves, quantities in zip(
                facts["party_moves"], facts["party_pp_encoded"], strict=True
            )
        ]
        facts["party_pp_current"] = [[move.current_pp for move in member] for member in decoded]
        facts["party_pp_maximum"] = [[move.maximum_pp for move in member] for member in decoded]
    collection = observation.collection_observation
    specimens = getattr(collection, "specimens", None)
    checkpoint = getattr(observation, "registered_checkpoint", None)
    from .red_registration_policy import RedRegistrationPolicy

    if isinstance(registration_policy, RedRegistrationPolicy):
        from .red_registered_observation import registered_completion_checkpoint

        checkpoint = registered_completion_checkpoint(observation, registration_policy)
    facts.update(
        input_ready=getattr(observation, "input_ready", None),
        owned_species=sorted(collection.owned_species),
        party_size=getattr(collection, "party_size", None),
        box_counts=getattr(collection, "box_counts", None),
        current_box_index=getattr(collection, "current_box_index", None),
        immediate_capture_slots=getattr(observation, "immediate_capture_slots", None),
        specimen_counts=(
            None if specimens is None else dict(Counter(s.species_ref for s in specimens))
        ),
        collection_ledger=collection_dependency_diagnostics(checkpoint),
    )
    # Changes to an unrelated owned bit must not masquerade as new physical
    # search conditions. This hash is observational, not a search-memory key.
    repel = facts["repel_remaining_steps"]
    facts["physical_search_context_sha256"] = canonical_sha256(dict(
        map_id=facts["map_id"],
        repel_active=None if repel is None else repel > 0,
        lead_level=(facts["party_levels"] or (None,))[0],
        bag_items=facts["bag_items"],
        specimen_counts=facts["specimen_counts"],
        protected_counts=(None if checkpoint is None else list(checkpoint.protected_counts)),
        capture_slots=facts["immediate_capture_slots"],
    ))
    return json.loads(
        json.dumps(
            dict(
                schema="pokemon.red.player-diagnostic-state.v1",
                diagnostic_only=True,
                unknown_fields=[key for key, value in facts.items() if value is None],
                **facts,
            ),
            allow_nan=False,
        )
    )


def collection_dependency_diagnostics(checkpoint):
    """Registration credit is not physical stock or a legal evolution offer."""
    if checkpoint is None:
        return None
    stock, protected = dict(checkpoint.specimen_counts), dict(checkpoint.protected_counts)
    missing = set(checkpoint.target_species) - set(checkpoint.credited_species)
    return dict(
        completion_scope=checkpoint.completion_scope,
        local_registered_species=list(checkpoint.local_species),
        global_registered_species=list(checkpoint.global_species),
        credited_species=list(checkpoint.credited_species),
        missing_registrations=sorted(missing),
        specimen_counts=stock,
        protected_counts=protected,
        potential_consuming_dependencies=[
            dict(
                source_species=source, target_species=target,
                physical_stock=stock.get(source, 0), protected_stock=protected.get(source, 0),
                unprotected_stock=max(0, stock.get(source, 0) - protected.get(source, 0)),
                physical_reacquisition_needed=stock.get(source, 0) <= protected.get(source, 0),
            )
            for source, target in checkpoint.allowed_evolutions if target in missing
        ],
        dependencies_are_alternatives_not_legal_offers=True,
    )


def player_diagnostic_delta(before, after):
    """Observable changes, not rewards or invented causes of resource losses."""
    delta = {}
    old, new = before.get("diagnostics", {}), after.get("diagnostics", {})
    for name in ("player_money", "repel_remaining_steps", "immediate_capture_slots"):
        a, b = old.get(name), new.get(name)
        delta[name] = b - a if type(a) is int and type(b) is int else None
    a, b = old.get("bag_items"), new.get("bag_items")
    if a is None or b is None:
        delta["bag_item_quantity_changes"] = None
    else:
        initial, final = dict(a), dict(b)
        delta["bag_item_quantity_changes"] = [
            dict(
                item_id=item,
                before=initial.get(item, 0),
                after=final.get(item, 0),
                change=final.get(item, 0) - initial.get(item, 0),
            )
            for item in sorted(initial.keys() | final.keys())
            if initial.get(item, 0) != final.get(item, 0)
        ]
    old_owned, new_owned = before.get("owned_species"), after.get("owned_species")
    delta["new_owned_species"] = (
        None if old_owned is None or new_owned is None else sorted(set(new_owned) - set(old_owned))
    )
    parties = [facts.get("player_lesson", {}).get("party") for facts in (before, after)]
    delta["retained_party_changes"] = None
    if all(isinstance(party, list) for party in parties):
        old_party = {m["specimen_ref"]: m for m in parties[0]}
        new_party = {m["specimen_ref"]: m for m in parties[1]}
        delta["retained_party_changes"] = [
            dict(
                specimen_ref=ref,
                changes={
                    name: dict(before=old_party[ref][name], after=new_party[ref][name])
                    for name in ("species_id", "level", "experience", "hp", "status", "moves")
                    if old_party[ref][name] != new_party[ref][name]
                },
            )
            for ref in sorted(old_party.keys() & new_party.keys())
        ]
    return dict(diagnostic_only=True, cause_not_inferred=True, **delta)


def player_resource_attribution(outcome):
    """Only recognized, checked receipts can explain a cash change.

    Net endpoint debit is never silently renamed gross spending. Quotes are
    prospective and cannot establish earnings, purchases, fees or blackouts.
    """
    delta = outcome.get("diagnostic_delta", {}).get("player_money")
    verified = outcome.get("verification") == "succeeded"
    receipts = []

    def add(kind, amount, path):
        if type(amount) is int and amount >= 0:
            receipts.append(dict(kind=kind, amount=amount, evidence_path=path))

    def visit(value, path):
        if isinstance(value, (list, tuple)):
            for index, nested in enumerate(value):
                visit(nested, path + f"[{index}]")
            return
        if not isinstance(value, Mapping):
            return
        if verified and value.get("schema") == "pokemon.red.repeatable-league-funding-execution.v2":
            names = ("observed_gross_income", "sale_proceeds", "purchase_cost",
                     "starting_money", "ending_money")
            if all(type(value.get(n)) is int and value[n] >= 0 for n in names):
                income, sales, cost, start, end = (value[n] for n in names)
                if end - start == income + sales - cost:
                    add("trainer_income", income, path + ".observed_gross_income")
                    add("item_sales", sales, path + ".sale_proceeds")
                    add("purchases", cost, path + ".purchase_cost")
            return  # Nested battle receipts must not double-count this total.
        if verified and (
            outcome.get("selected_kind") == GoalKind.RESUPPLY.value
            or value.get("procurement_executed") is True
        ):
            add("purchases", value.get("money_spent"), path + ".money_spent")
            add("item_sales", value.get("sale_proceeds"), path + ".sale_proceeds")
        mechanic = value.get("mechanic")
        if (verified and isinstance(mechanic, str)
                and mechanic in {"game_corner", "game_corner_coin_procurement"}):
            add("coin_procurement", value.get("cash_debit"), path + ".cash_debit")
        # Admission is independently verified: a later missed catch does not
        # undo the paid entrance. Do not infer a fee from the endpoint debit.
        if value.get("single_admission") is True and value.get("status") == "ok":
            add("admission_fee", value.get("admission_fee_paid"), path + ".admission_fee_paid")
        funding = value.get("trainer_funding")
        if verified and isinstance(funding, Mapping):
            fields = ("initial_money", "final_money", "payout",
                      "ordinary_victory_money", "pay_day_money")
            if all(type(funding.get(n)) is int and funding[n] >= 0 for n in fields):
                start, end, payout, ordinary, payday = (funding[n] for n in fields)
                if payout == end - start and end == min(999999, start + ordinary + payday):
                    add("trainer_income", payout, path + ".trainer_funding.payout")
        blackout = value.get("native_blackout_during_selected_restoration")
        if isinstance(blackout, Mapping) and blackout.get("blackout_verified") is True:
            start, end, lost = (blackout.get(n) for n in ("cash_before", "cash_after", "cash_lost"))
            if (type(start) is int and type(end) is int and type(lost) is int
                    and start >= 0 and end == start // 2 and lost == start - end):
                add("blackout_loss", lost, path + ".native_blackout_during_selected_restoration")
        for name, nested in value.items():
            visit(nested, path + "." + str(name))

    visit(outcome.get("evidence"), "evidence")
    explained = sum(
        row["amount"] * (
            -1 if row["kind"] in {"purchases", "blackout_loss", "coin_procurement", "admission_fee"}
            else 1
        )
        for row in receipts
    )
    return dict(
        unit="cartridge_currency", observed_net_cash_change=delta,
        supported_receipts=receipts, explained_net_cash_change=explained,
        unexplained_net_cash_change=None if delta is None else delta - explained,
        gross_spending_known=any(r["kind"] == "purchases" for r in receipts),
        unobserved_causes_not_inferred=True,
    )


def _reported_preparation_work(evidence):
    """Read explicit native totals; never infer battles from XP or healing calls."""
    reported = evidence.get("execution_diagnostics") or evidence
    if not isinstance(reported, Mapping):
        return None, None, None
    battles, trips = (reported.get(name) for name in ("completed_training_battles", "healing_trips"))
    battles = battles if type(battles) is int and battles >= 0 else None
    trips = trips if type(trips) is int and trips >= 0 else None
    prefix = "execution_diagnostics." if reported is not evidence else ""
    if battles is not None:
        return battles, trips, prefix + "completed_training_battles"
    preparation = evidence
    if evidence.get("mechanic") == "routed_preparation":
        preparation = evidence.get("preparation")
        prefix = "preparation."
    else:
        prefix = ""
    if not isinstance(preparation, Mapping):
        return None, trips, None
    total = preparation.get("completed_battles_across_doses")
    allowance = preparation.get("total_battle_allowance")
    doses = preparation.get("retained_doses")
    if (preparation.get("repeat_health_limited_zero_progress") is not True
            or type(total) is not int or type(allowance) is not int
            or not 1 <= allowance <= 128 or not 0 <= total <= allowance
            or not isinstance(doses, (tuple, list)) or not 1 <= len(doses) <= 128):
        return None, trips, None
    observed = 0
    for ordinal, dose in enumerate(doses):
        if (not isinstance(dose, Mapping) or type(dose.get("ordinal")) is not int
                or dose["ordinal"] != ordinal or not isinstance(dose.get("result"), Mapping)):
            return None, trips, None
        count = dose["result"].get("battles")
        if type(count) is not int or count < 0:
            return None, trips, None
        observed += count
    if observed != total:
        return None, trips, None
    return total, trips, prefix + "completed_battles_across_doses"


def player_outcome_diagnostics(outcome, *, resource_quote=None, selection_diagnostics=None):
    """Attach measured consequences without admitting rows or changing targets."""
    choice = outcome.get("choice", {})
    selected_index = choice.get("selected_candidate_index")
    candidates = (selection_diagnostics or {}).get("candidates", ())
    selected = next((row for row in candidates if row.get("candidate_index") == selected_index), {})
    before, after = outcome.get("before", {}), outcome.get("after", {})
    attribution = player_resource_attribution(outcome)
    purchases = [r["amount"] for r in attribution["supported_receipts"] if r["kind"] == "purchases"]
    quoted_purchase = None if resource_quote is None else resource_quote.get("purchase_cost")
    old = {m["specimen_ref"]: m for m in before.get("player_lesson", {}).get("party", ())}
    new = {m["specimen_ref"]: m for m in after.get("player_lesson", {}).get("party", ())}
    seconds = outcome.get("phase_seconds", {}).get("execution")
    cost = outcome.get("observed_cost") or outcome.get("measured_cost") or {}
    evidence = outcome.get("evidence") or {}
    battles, trips, battle_source = _reported_preparation_work(evidence)
    members = []
    for ref in sorted(old.keys() & new.keys()):
        a, b = old[ref].get("experience"), new[ref].get("experience")
        xp = b - a if type(a) is int and type(b) is int else None
        members.append(dict(
            specimen_ref=ref, xp_change=xp,
            declared_role=(
                None if "combat_specimen_refs" not in before else
                "combat" if ref in before["combat_specimen_refs"] else "undecided"
            ),
            level_before=old[ref].get("level"), level_after=new[ref].get("level"),
            xp_per_execution_second=(
                xp / seconds if xp is not None and isinstance(seconds, (int, float))
                and seconds > 0 else None
            ),
            xp_per_native_action=(
                xp / cost["actions"] if xp is not None and type(cost.get("actions")) is int
                and cost["actions"] > 0 else None
            ),
            xp_per_native_frame=(
                xp / cost["frames"] if xp is not None and type(cost.get("frames")) is int
                and cost["frames"] > 0 else None
            ),
            combat_participation=None,  # XP/HP alone cannot prove participation.
        ))
    raw, bounded = selected.get("raw_predictions"), selected.get("bounded_predictions")
    observed_success = (
        1 if outcome.get("verification") == "succeeded"
        else 0 if outcome.get("verification") == "failed" else None
    )
    return dict(
        schema="pokemon.red.player-outcome-diagnostics.v1", diagnostic_only=True,
        training_admission=False,
        prediction_comparison=dict(
            selected_candidate_index=selected_index,
            raw_predictions=raw, bounded_predictions=bounded,
            observed_verified_success=observed_success,
            verified_success_residual=(
                observed_success - bounded["verified_success"]
                if observed_success is not None and bounded is not None else None
            ),
            prediction_is_calibrated_probability=False,
            normalized_prediction_costs_are_not_native_units=True,
        ),
        cost_comparison=dict(
            prospective_quote=resource_quote,
            measured_native_cost=outcome.get("measured_cost"),
            observed_native_cost=outcome.get("observed_cost"),
            execution_seconds=seconds,
            actions_and_frames_are_not_search_steps=True,
            verified_purchase_quote_error=(
                sum(purchases) - quoted_purchase
                if purchases and type(quoted_purchase) is int else None
            ),
        ),
        resource_attribution=attribution,
        preparation_efficiency=dict(
            retained_members=members,
            reported_training_battles=battles,
            reported_training_battle_source=battle_source,
            reported_healing_trips=trips if type(trips) is int else None,
            battle_count=None, healing_interaction_count=None,
            observed_restoration_attempts={
                name: after[name] - before[name]
                if type(before.get(name)) is int and type(after.get(name)) is int else None
                for name in ("restoration_attempts", "nested_restoration_attempts",
                             "training_healing_attempts")
            },
            participation_not_inferred=True,
        ),
    )


def player_stop_diagnostics(stop_reason, last_outcome=None):
    """A diagnostic category is not authorization or a proof of resumability."""
    row = last_outcome or {}
    if stop_reason in {"curriculum_complete", "declared_consequence_complete"}:
        category = "objective_complete"
    elif stop_reason in {
        "decision_budget", "wall_time_budget", "continuous_spending_exceeded",
        "continuous_spending_boundary", "cash_exposure_exceeded",
        "integrated_scope_or_spending_boundary",
    }:
        category = "allocation_limit"
    elif row.get("failure_phase") == "admission":
        category = "option_admission_failure"
    elif stop_reason in {"menu_unavailable", "no_available_options"}:
        category = "missing_executable_option"
    elif row.get("ordinary_setback"):
        category = "normal_game_setback"
    elif row.get("failure_phase") in {"execution", "verification"}:
        category = "control_or_verification_failure"
    else:
        category = "unclassified_requires_evidence"
    return dict(
        schema="pokemon.red.player-stop-diagnostics.v1", diagnostic_only=True,
        stop_reason=stop_reason, category=category, safe_terminal=row.get("safe_terminal"),
        failure_reason=row.get("failure_reason"), error_chain=row.get("error_chain"),
        **({"error_type": row.get("error_type"), "error": row.get("error")}
           if row.get("failure_phase") == "admission" else {}),
        resume_authorized=False, additional_inputs_authorized=False,
    )


def summarize_player_diagnostic_events(events):
    """Compact coverage from the same retained journal, never a control signal."""
    kinds = Counter(row["kind"] for row in events)
    throws, search, casts = [], [], []
    for row in events:
        payload = row.get("payload", {})
        if row["kind"] == "capture_throw_completed":
            conditions = payload.get("conditions", {})
            throws.append(dict(
                event_ordinal=row.get("ordinal"), source=payload.get("source"),
                ball_id=conditions.get("ball_id"), outcome=payload.get("outcome"),
                measured_cost=payload.get("measured_cost"),
            ))
        elif row["kind"] in {"survey_action_returned", "survey_action_failed"}:
            if payload.get("operation") == "seek_encounter":
                search.append(payload.get("diagnostic_review", {}))
        elif row["kind"] == "fishing_cast_observed":
            casts.append(payload)
    known_steps = [r.get("measured", {}).get("eligible_search_steps") for r in search]
    return dict(
        schema="pokemon.red.player-diagnostic-coverage.v1", diagnostic_only=True,
        event_counts=dict(sorted(kinds.items())),
        capture=dict(
            started=kinds["capture_throw_started"], completed=len(throws),
            incomplete=max(0, kinds["capture_throw_started"] - len(throws)),
            by_source=dict(Counter(row["source"] for row in throws)), throws=throws,
        ),
        search=dict(
            observed_operations=len(search), operations_with_known_tile_exposure=sum(
                type(n) is int for n in known_steps
            ), known_tile_exposure=sum(n for n in known_steps if type(n) is int),
            total_eligible_search_steps=(
                sum(known_steps) if search and all(type(n) is int for n in known_steps) else None
            ),
            actual_rng_checks=None, step_probability=None,
        ),
        fishing=dict(
            observed_casts=len(casts), selected_target_sightings=sum(
                row.get("selected_target_seen") is True for row in casts
            ),
            no_bites=sum(row.get("outcome") == "no_bite" for row in casts),
        ),
        training_admission=False, automatic_fit=False,
    )


def player_control_diagnostics(reader):
    """Semantic control and visible text at sparse boundaries, never inputs."""
    methods = {
        "bottom_dialogue_visible": "read_bottom_dialogue_box_visible",
        "start_menu_visible": "read_overworld_start_menu_visible",
        "trainer_engagement_active": "trainer_engagement_active",
        "screen_text_rows": "read_screen_text_rows",
    }
    return {
        key: (list(value()) if key == "screen_text_rows" else value())
        if callable(value := getattr(reader, method, None))
        else None
        for key, method in methods.items()
    }


def observe_native_player_boundary(
    runtime, *, battle, combat_specimen_refs, remaining_budget, include_live_pp_readiness=False
):
    """Read current resources/readiness without input or stale target projections."""
    if type(include_live_pp_readiness) is not bool:
        raise TypeError("live PP readiness permission must be an explicit boolean")
    start_state = runtime.emulator.save_state_bytes()
    observation, snapshot = capture_player_lesson_snapshot(runtime)
    before = project_registered_observation(observation, runtime.registration_policy)
    members = validate_snapshot(snapshot, before.public_dict())
    if include_live_pp_readiness:
        from dataclasses import replace

        from .red_pp_observation import observe_pp_resources

        pp = observe_pp_resources(observation.raw)
        if len(pp.party_slots) != len(members):
            raise ValueError("live PP readiness party differs from the authenticated snapshot")
        members = {
            ref: replace(
                member,
                moves=tuple(
                    replace(move, max_pp=maximum)
                    for move, (current, maximum) in zip(member.moves, slots, strict=True)
                    if current == move.current_pp
                ),
            )
            for (ref, member), slots in zip(members.items(), pp.party_slots, strict=True)
        }
        if any(len(member.moves) != 4 for member in members.values()):
            raise ValueError("live PP readiness differs from current move quantities")
    if (
        not isinstance(combat_specimen_refs, tuple)
        or not combat_specimen_refs
        or len(set(combat_specimen_refs)) != len(combat_specimen_refs)
        or not set(combat_specimen_refs) <= members.keys()
    ):
        raise ValueError("native player requires declared observed combat members")
    party = tuple(
        PreparationMember(
            key,
            member,
            PreparationPurpose.COMBAT
            if key in combat_specimen_refs
            else PreparationPurpose.UNDECIDED,
            purpose_reason="declared player combat role" if key in combat_specimen_refs else "",
        )
        for key, member in members.items()
    )
    readiness = (
        PlayerReadiness.without_battle_history(party, remaining_budget)
        if battle is None
        else PlayerReadiness.from_context(context_after_recovery(battle, party), remaining_budget)
    )
    raw = observation.raw
    if raw.player_money is None or raw.bag_items is None:
        raise ValueError("native player requires observed resources")
    economy = EconomySnapshot(
        raw.player_money, tuple(sorted((f"red-item-{i:03d}", n) for i, n in raw.bag_items))
    )
    if runtime.emulator.save_state_bytes() != start_state:
        raise ValueError("native player observation changed state")
    return NativePlayerBoundary(observation, before, snapshot, readiness, economy, start_state)


def _declared_loan_control_support(
    runtime, actions, *, combat_specimen_refs, remaining_budget, enumerate_bindings,
    include_live_pp_readiness,
):
    """A boxed combat anchor must not block its own compulsory return.

    Only a unique hash-bound ordinary wild exit or exact named PC return may
    bypass active-combat readiness. No guest is promoted to combat, no history
    is erased and this support record never becomes a policy question.
    """
    from .goal_manager_runtime import GoalBindingSet
    from .red_player_party_guard import RedPlayerPartyGuard

    if type(include_live_pp_readiness) is not bool:
        raise TypeError("live PP readiness permission must be an explicit boolean")

    guard = getattr(getattr(runtime, "adapter", None), "party_guard", None)
    if not isinstance(guard, RedPlayerPartyGuard) or enumerate_bindings is None:
        return None
    if (type(combat_specimen_refs) is not tuple or not combat_specimen_refs
            or len(set(combat_specimen_refs)) != len(combat_specimen_refs)):
        return None
    active = set(guard.reader.preparation_specimen_refs())
    missing = set(combat_specimen_refs) - active
    if not missing:
        return None
    if (len(guard.loanable_refs) != 1 or not missing <= guard.loanable_refs
            or set(guard.refs) - active != set(guard.loanable_refs)
            or guard.storage_reader is None):
        return None
    guard.verify()
    state, frames = runtime.emulator.save_state_bytes(), runtime.emulator.frame_count
    observation, snapshot = capture_player_lesson_snapshot(runtime)
    raw = observation.raw
    registered = project_registered_observation(observation, runtime.registration_policy)
    members = validate_snapshot(snapshot, registered.public_dict())
    bindings = enumerate_bindings(runtime, actions, observation)
    expected = (
        "pokemon.red:interrupted-wild:" if raw.battle_state == 1 else
        "pokemon.red:retained-loan-return:"
        if raw.battle_state == 0 and observation.input_ready else None
    )
    if (expected is None or type(bindings) is not GoalBindingSet or len(bindings.bindings) != 1
            or bindings.bindings[0].kind is not GoalKind.RECOVER_CONTROL
            or bindings.bindings[0].binding_ref != expected + sha256(state).hexdigest()):
        raise ValueError("boxed combat anchor permits only its exact compulsory loan recovery")
    if set(members) != active:
        raise ValueError("loan control snapshot differs from its retained active roster")
    boxed = {m.preparation_ref: m for m in guard.storage_reader.read_box_specimen_identities()}
    levels = [members[ref].level if ref in members else boxed[ref].level
              for ref in combat_specimen_refs]
    hp, maximum = sum(m.hp for m in members.values()), sum(m.max_hp for m in members.values())
    current = {
        "current.combat_level_spread": (max(levels) - min(levels)) / 100,
        "current.hp_fraction": hp / maximum if maximum else 0.0,
        "current.fainted_fraction": sum(m.is_fainted for m in members.values()) / len(members),
        "current.status_fraction": sum(m.status.value != "healthy" for m in members.values())
            / len(members),
    }
    if include_live_pp_readiness:
        from .red_pp_observation import observe_pp_resources

        slots = observe_pp_resources(raw).party_slots
        pp_max = sum(maximum for member in slots for _, maximum in member)
        current.update({"current.pp_known": float(pp_max > 0), "current.pp_fraction":
            sum(pp for member in slots for pp, _ in member) / pp_max if pp_max else 0.0})
    from .player_readiness import CONTEXT_NAMES

    readiness = PlayerReadiness(
        tuple(current.get(name, 0.0) for name in CONTEXT_NAMES) + remaining_budget,
        history_observed=False,
    )
    if runtime.emulator.save_state_bytes() != state or runtime.emulator.frame_count != frames:
        raise ValueError("declared loan control inventory changed state")
    record = getattr(actions, "record_diagnostic_event", None)
    if callable(record):
        record("declared_loan_control", dict(model_queries=0, active_combat_role_deferred=True,
            guest_promoted_to_combat=False, history_retained=True))
    return RedPlayerSupport(bindings, readiness)


def observe_native_player_options(
    runtime,
    actions,
    *,
    battle,
    combat_specimen_refs,
    remaining_budget,
    target_cash,
    ordering_seed_sha256,
    supplements=(),
    allow_support=False,
    enumerate_bindings=None,
    enumerate_supplements=None,
    observe_challenges=None,
    observe_preparations=None,
    observe_matchups=None,
    observe_preparation_party=None,
    model_feature_version=5,
    curriculum=None,
    capture_reserve=None,
    force_resource_safety=True,
    include_live_pp_readiness=False,
):
    """Build the actual V5 actor menu from the same live boundary as native lessons.

    Invoke anew after each settled goal. The runtime owns executable capabilities;
    neither this observer nor the lesson target chooses the next action. Caller
    supplies observed aftermath and authenticated remaining-budget fractions.
    """
    if observe_preparation_party is not None and (not callable(observe_preparation_party) or model_feature_version!=15):
        raise ValueError("party-count observer requires explicit V15 boundary")
    if observe_matchups is not None and (
        not callable(observe_matchups) or model_feature_version != 15
    ):
        raise ValueError("native matchup observer requires V15 and a callable")
    if type(force_resource_safety) is not bool:
        raise TypeError("resource safety authority must be an explicit boolean")
    if allow_support:
        loan_control = _declared_loan_control_support(
            runtime, actions, combat_specimen_refs=combat_specimen_refs,
            remaining_budget=remaining_budget, enumerate_bindings=enumerate_bindings,
            include_live_pp_readiness=include_live_pp_readiness,
        )
        if loan_control is not None:
            return loan_control
    boundary = observe_native_player_boundary(
        runtime,
        battle=battle,
        combat_specimen_refs=combat_specimen_refs,
        remaining_budget=remaining_budget,
        include_live_pp_readiness=include_live_pp_readiness,
    )
    record = getattr(actions, "record_diagnostic_event", None)
    if callable(record):
        record(
            "player_boundary",
            dict(
                state=player_diagnostic_state(boundary.observation),
                readiness=boundary.readiness.public_dict(),
                recent_battle_observed=battle is not None,
                live_pp_readiness_enabled=include_live_pp_readiness,
                control=player_control_diagnostics(getattr(runtime, "reader", None)),
            ),
        )
    if curriculum is not None:
        if not allow_support or not isinstance(curriculum, NativePlayerCurriculum):
            raise ValueError("curriculum completion needs an explicit native player declaration")
        # Input readiness also holds inside some nurse/field dialogue boxes.
        # Let control recovery run instead of claiming a settled completion
        # that the native snapshot verifier must then reject.
        completion = (
            curriculum.completion(boundary)
            if not runtime.reader.read_bottom_dialogue_box_visible()
            and not runtime.emulator.pressed_buttons
            else None
        )
        if runtime.emulator.save_state_bytes() != boundary.state:
            raise ValueError("curriculum observation changed state")
        if completion is not None:
            return completion
    bindings = (
        runtime.enumerator(actions).enumerate(boundary.registered)
        if enumerate_bindings is None
        else enumerate_bindings(runtime, actions, boundary.registered)
    )
    if callable(record):
        record(
            "ordinary_goal_inventory",
            dict(
                opportunities=[
                    dict(
                        binding_ref=o.binding_ref,
                        kind=o.kind.value,
                        availability=o.availability.value,
                        unavailable_reason=None
                        if o.unavailable_reason is None
                        else o.unavailable_reason.value,
                        estimated_effort=o.estimated_effort,
                        estimated_risk=o.estimated_risk,
                    )
                    for o in bindings.opportunities
                ]
            ),
        )
    if enumerate_supplements is not None:
        if supplements or not callable(enumerate_supplements):
            raise ValueError("dynamic supplemental inventory must be exclusive and callable")
        # Control recovery is compulsory, never a competing story choice.
        supplements = (
            ()
            if any(b.kind is GoalKind.RECOVER_CONTROL for b in bindings.bindings)
            else enumerate_supplements(runtime, actions, boundary.registered, bindings)
        )
        if not isinstance(supplements, tuple):
            raise ValueError("dynamic supplemental inventory must be immutable")
        if runtime.emulator.save_state_bytes() != boundary.state:
            raise ValueError("supplemental inventory changed native state")
    blocked_restoration = False
    if allow_support and remaining_budget[4] == 0:
        blocked_restoration = any(s.binding.kind is GoalKind.RESTORE_TEAM for s in supplements)
        supplements = tuple(s for s in supplements if s.binding.kind is not GoalKind.RESTORE_TEAM)
        blocked_refs = {b.binding_ref for b in bindings.bindings if b.kind is GoalKind.RESTORE_TEAM}
        blocked_restoration = blocked_restoration or bool(blocked_refs)
        bindings = replace(
            bindings,
            bindings=tuple(b for b in bindings.bindings if b.binding_ref not in blocked_refs),
            opportunities=tuple(
                replace(
                    o,
                    availability=GoalAvailability.UNAVAILABLE,
                    unavailable_reason=GoalUnavailableReason.MISSING_RESOURCE,
                    estimated_effort=None,
                    estimated_risk=None,
                    resource_quote=None,
                )
                if o.binding_ref in blocked_refs
                else o
                for o in bindings.opportunities
            ),
        )
    if blocked_restoration and not bindings.bindings and not supplements:
        if runtime.emulator.save_state_bytes() != boundary.state:
            raise ValueError("native budget observation changed state")
        return PlayerBudgetStop(sha256(boundary.state).hexdigest())
    storage_masks_acquisitions = (
        boundary.registered.situation.storage_pressure > CompletionFirstGoalTeacher().storage_gate
        and not any(b.kind is GoalKind.MANAGE_STORAGE for b in bindings.bindings)
    )
    if allow_support and storage_masks_acquisitions:
        # The mixed menu applies this same storage guard. Apply it before
        # counting support alternatives too: masked acquisitions cannot turn
        # a sole real supply/escape option into a comparative model question.
        supplements = tuple(
            s for s in supplements if s.binding.kind is not GoalKind.ACQUIRE_SPECIES
        )
    if (
        allow_support
        and not bindings.bindings
        and len(supplements) == 1
        and supplements[0].binding.kind is GoalKind.ACQUIRE_SPECIES
    ):
        # A sole native acquisition is not a comparative model question.
        # Reuse the existing storage/economy guards, then keep its execution
        # explicitly attributed to support. Never fabricate a second choice.
        forced = build_red_live_forced_singleton(
            situation=boundary.registered.situation,
            binding_set=bindings,
            supplements=supplements,
            economy_snapshot=boundary.economy,
            target_cash=target_cash,
        )
        if runtime.emulator.save_state_bytes() != boundary.state:
            raise ValueError("native player support inventory changed state")
        return RedPlayerSupport(forced.binding_set, boundary.readiness)
    if (
        allow_support
        and not bindings.bindings
        and len(supplements) == 1
        and supplements[0].binding.kind in {
            GoalKind.EVOLVE_SPECIES, GoalKind.RESUPPLY,
            GoalKind.DEVELOP_TEAM, GoalKind.MANAGE_STORAGE,
        }
    ):
        # A sole executable supplement is not a comparative model question.
        # Reuse the existing support path without inventing another candidate.
        evolution = supplements[0].binding
        if sum(o.kind is evolution.kind for o in bindings.opportunities) != 1:
            raise ValueError("singleton support needs one masked ordinary opportunity")
        rebound = replace(
            bindings,
            opportunities=tuple(
                evolution.opportunity if o.kind is evolution.kind else o
                for o in bindings.opportunities
            ),
            bindings=(evolution,),
        )
        if runtime.emulator.save_state_bytes() != boundary.state:
            raise ValueError("native player support inventory changed state")
        return RedPlayerSupport(rebound, boundary.readiness)
    if (
        allow_support
        and not supplements
        and (
            len(bindings.bindings) == 1
            or any(binding.kind is GoalKind.RECOVER_CONTROL for binding in bindings.bindings)
        )
        and not (
            storage_masks_acquisitions
            and len(bindings.bindings) == 1
            and bindings.bindings[0].kind is GoalKind.ACQUIRE_SPECIES
        )
    ):
        if runtime.emulator.save_state_bytes() != boundary.state:
            raise ValueError("native player support inventory changed state")
        return RedPlayerSupport(bindings, boundary.readiness)
    situation = boundary.registered.situation
    if capture_reserve is not None:
        from .red_capture_readiness import assess_capture_readiness, capture_preparation_situation

        situation = capture_preparation_situation(
            boundary.registered, assess_capture_readiness(boundary.registered, capture_reserve)
        )
    challenges = (
        None
        if observe_challenges is None
        else observe_challenges(
            runtime,
            bindings,
            supplements,
            boundary,
        )
    )
    options = build_red_live_option_set(
        situation=situation,
        binding_set=bindings,
        model_feature_version=model_feature_version,
        ordering_seed_sha256=ordering_seed_sha256,
        economy_snapshot=boundary.economy,
        target_cash=target_cash,
        readiness=boundary.readiness,
        supplements=supplements,
        challenges=challenges,
        preparations=None
        if observe_preparations is None
        else observe_preparations(
            runtime,
            bindings,
            supplements,
            boundary,
        ),
        matchups=None if observe_matchups is None else observe_matchups(
            runtime, bindings, supplements, boundary,
        ),
        force_resource_safety=force_resource_safety,
    )
    if observe_preparation_party is not None:
        from .player_preparation_party_context import PreparationPartyWitness
        witness=observe_preparation_party(runtime,bindings,supplements,boundary)
        if type(witness) is not PreparationPartyWitness:
            raise ValueError("complete observed party witness required")
        witness.validate_lesson(boundary.lesson_snapshot,sha256(boundary.state).hexdigest())
        options=replace(options,preparation_party_witness=witness)
    if runtime.emulator.save_state_bytes() != boundary.state:
        raise ValueError("native player menu changed state")
    return options


def native_action_record_id(kind: str, declaration: str, ordinal: int) -> str:
    """Keep historical IDs, hashing oversized ones within the artifact name limit."""
    if (
        kind not in {"action", "trace"}
        or not isinstance(declaration, str)
        or len(declaration) != 64
        or any(char not in "0123456789abcdef" for char in declaration)
        or type(ordinal) is not int
        or ordinal < 0
    ):
        raise ValueError("native action record identity is invalid")
    legacy = f"rnl-{kind}-{declaration}-{ordinal}"
    if len(legacy) <= 80:
        return legacy
    return f"rnl-{kind}-{sha256(legacy.encode('ascii')).hexdigest()}"


class _RecordedActions:
    def __init__(self, controller, store, declaration, maximum_actions, *, timing=None):
        self.controller, self.store = controller, store
        self.declaration, self.maximum_actions = declaration, maximum_actions
        self.delegate = FrameSafeExecutor(
            controller,
            timing=DEFAULT_NEW_GAME_TIMING.controller_timing() if timing is None else timing,
        )
        self.trace = []
        self.diagnostic_events = []
        self.diagnostic_journal_seconds = 0.0
        self.enabled = False

    def record_diagnostic_event(self, kind, payload):
        """Use the existing sealed journal, never a lesson or policy input."""
        if not isinstance(kind, str) or not kind or not isinstance(payload, dict):
            raise TypeError("native diagnostic event requires a kind and dictionary")
        ordinal = len(self.diagnostic_events)
        row = dict(
            schema="pokemon.red.player-diagnostic-event.v1",
            ordinal=ordinal,
            action_ordinal=len(self.trace),
            frame=self.controller.frames_executed,
            kind=kind,
            payload=deepcopy(payload),
            diagnostic_only=True,
            automatic_fit=False,
        )
        identity = canonical_sha256(dict(declaration=self.declaration, ordinal=ordinal))
        started = monotonic()
        self.store.publish_sealed_record(
            "rnp-diagnostic-" + identity,
            kind="red_native_player_diagnostic",
            record=row,
        )
        self.diagnostic_journal_seconds += monotonic() - started
        self.diagnostic_events.append(row)

    def execute(self, action):
        if not self.enabled:
            raise RuntimeError("recorded input outside declared goal execution")
        if len(self.trace) >= self.maximum_actions:
            raise ControllerActionBudgetExhausted(
                maximum_actions=self.maximum_actions,
                attempted_actions=len(self.trace),
            )
        ordinal = len(self.trace)
        before = self.controller.frames_executed
        # An interrupted macro remains durably visible even after process loss.
        self.store.publish_sealed_record(
            native_action_record_id("action", self.declaration, ordinal),
            kind="red_native_lesson_action",
            record=dict(
                ordinal=ordinal,
                before_frame=before,
                action=action.kind.value,
                value=action.value,
                repeat=action.repeat,
            ),
        )
        succeeded = False
        self.controller.input_enabled = True
        try:
            result = self.delegate.execute(action)
            succeeded = True
            return result
        finally:
            self.controller.input_enabled = False
            row = dict(
                ordinal=ordinal,
                before_frame=before,
                after_frame=self.controller.frames_executed,
                succeeded=succeeded,
            )
            self.trace.append(row)
            self.store.publish_sealed_record(
                native_action_record_id("trace", self.declaration, ordinal),
                kind="red_native_lesson_trace",
                record=row,
            )


def record_native_player_lesson(
    store,
    *,
    emulator,
    runtime_factory,
    source,
    selected_index,
    target,
    battle,
    combat_specimen_refs,
    remaining_budget,
    target_cash,
    maximum_actions=1000,
    maximum_frames=80000,
    enumerate_bindings=None,
    observe_challenge=None,
    observe_preparation=None,
    story_unit_target=None,
    preflight_only=False,
    include_live_pp_readiness=False,
):
    """Record one teacher-selected native player offer and verify it.

    Existing runtime.enumerator binds executors to our counted action port.
    Readiness is reconstructed from the measured current party and the supplied
    observed aftermath, never from the selected target or future outcome.
    Source partition/provenance remains the caller's authentication obligation;
    declared state bytes are independently matched before any execution.
    preflight_only validates this exact declaration without claiming/publishing
    an attempt or opening the action port. It creates no outcome or model label.
    """
    if type(preflight_only) is not bool:
        raise TypeError("native lesson preflight mode must be boolean")
    if type(include_live_pp_readiness) is not bool:
        raise TypeError("native lesson PP readiness must be an explicit boolean")
    controller = NativeLessonController(emulator, maximum_frames=maximum_frames)
    start_state = controller.save_state_bytes()
    if (
        source.get("partition") != "train"
        or source.get("state_sha256") != sha256(start_state).hexdigest()
    ):
        raise ValueError("native lesson requires the exact declared TRAIN state")
    runtime = runtime_factory(controller)
    if runtime.emulator is not controller or runtime.registration_policy is None:
        raise ValueError("native lesson requires the controlled registered runtime")
    boundary = observe_native_player_boundary(
        runtime,
        battle=battle,
        combat_specimen_refs=combat_specimen_refs,
        remaining_budget=remaining_budget,
        include_live_pp_readiness=include_live_pp_readiness,
    )
    before, snapshot, readiness = (
        boundary.registered,
        boundary.lesson_snapshot,
        boundary.readiness,
    )
    before_doc = before.public_dict()
    # Initially input remains closed; the declaration binds the fresh provider menu.
    recorder = _RecordedActions(controller, store, "unarmed", maximum_actions)
    actions = CountingExecutor(recorder)
    bindings = (
        runtime.enumerator(actions).enumerate(before)
        if enumerate_bindings is None
        else enumerate_bindings(runtime, actions, before)
    )
    question = bindings.question(before.situation)
    if type(selected_index) is not int or selected_index not in question.available_indices:
        raise ValueError("native lesson selected unavailable binding")
    binding = bindings.require(question.opportunities[selected_index].binding_ref)
    resource = binding.kind in RESOURCE_LESSON_KINDS
    challenge = None
    if observe_challenge is not None:
        from .player_option_challenge import OptionChallenge

        if resource or not callable(observe_challenge):
            raise ValueError(
                "challenge lesson currently requires a nonresource observation callback"
            )
        challenge = observe_challenge(runtime, binding, boundary)
        if not isinstance(challenge, OptionChallenge):
            raise TypeError("challenge lesson requires typed prospective measurements")
    preparation = None
    preparation_lesson = observe_preparation is not None
    if preparation_lesson:
        from .player_option_preparation import OptionPreparation

        if resource or story_unit_target is not None or not callable(observe_preparation):
            raise ValueError("preparation facts require an ordinary player lesson callback")
        preparation = observe_preparation(runtime, binding, boundary)
        if (
            binding.kind is GoalKind.DEVELOP_TEAM
            and not isinstance(preparation, OptionPreparation)
            or binding.kind is not GoalKind.DEVELOP_TEAM
            and preparation is not None
        ):
            raise TypeError("preparation lesson requires typed selected-member facts")
    story_unit = None
    if story_unit_target is not None:
        from .red_player_story_unit import capture_story_unit

        if binding.kind is not GoalKind.ADVANCE_STORY or challenge is None:
            raise ValueError("story unit requires a prospective story challenge")
        story_unit = dict(
            target=deepcopy(story_unit_target),
            before=capture_story_unit(runtime, story_unit_target),
        )
    plan = dict(
        schema=(
            PREPARATION_PLAN_SCHEMA
            if preparation_lesson
            else STORY_UNIT_PLAN_SCHEMA
            if story_unit is not None
            else CHALLENGE_PLAN_SCHEMA
            if challenge is not None
            else RESOURCE_PLAN_SCHEMA
            if resource
            else READINESS_PLAN_SCHEMA
        ),
        contract=(
            PREPARATION_CONTRACT
            if preparation_lesson
            else STORY_UNIT_CONTRACT
            if story_unit is not None
            else CHALLENGE_CONTRACT
            if challenge is not None
            else RESOURCE_CONTRACT
            if resource
            else READINESS_CONTRACT
        ),
        partition="train",
        objective=REGISTERED_OBJECTIVE,
        question=dict(
            schema=question.policy_input["schema"],
            situation=question.situation.policy_dict(),
            candidates=[o.policy_dict() for o in question.opportunities],
        ),
        selected_index=selected_index,
        before=before_doc,
        economy_before=snapshot_document(boundary.economy),
        target_cash=target_cash,
        source=deepcopy(source),
        maximum_actions=maximum_actions,
        maximum_frames=maximum_frames,
        teacher_selected=True,
        comparative_choice=False,
        player_lesson=dict(before=snapshot, target=deepcopy(target)),
        readiness=readiness.public_dict(),
    )
    if challenge is not None:
        plan["challenge"] = challenge.public_dict()
    if preparation_lesson:
        plan["preparation"] = None if preparation is None else preparation.public_dict()
        plan["challenge"] = None if challenge is None else challenge.public_dict()
    if story_unit is not None:
        plan["story_unit"] = story_unit
    declaration = canonical_sha256(plan)
    curriculum_projection(plan)
    if controller.frames_executed or controller.save_state_bytes() != start_state:
        raise ValueError("native lesson boundary changed during preparation")
    if preflight_only:
        return dict(
            schema="pokemon.red.native-player-lesson-preflight.v1",
            declaration_sha256=declaration,
            declaration=plan,
            input_frames=0,
            admitted=False,
            attempted=False,
        )
    with store.collection_session("rnl-" + declaration):
        if (
            store.find_sealed_record(
                "rnc-plan-" + declaration, expected_kind="red_native_curriculum_plan"
            )
            is not None
        ):
            raise ValueError("native lesson declaration already attempted")
        if controller.frames_executed or controller.save_state_bytes() != start_state:
            raise ValueError("native lesson boundary changed during preparation")
        publish_declaration(store, plan)
        recorder.declaration = declaration
        started = monotonic()
        succeeded, stage, error_type, item = False, "execute", None, None
        terminal = after_doc = terminal_sha = None
        try:
            recorder.enabled = True
            try:
                report = binding.execute()
            finally:
                recorder.enabled = False
            stage = "verify"
            if not isinstance(report, GoalExecutionReport) or (
                report.actions_executed != actions.actions_executed
                or report.frames_executed != controller.frames_executed
            ):
                raise ValueError("native lesson execution costs differ from trace")
            verdict = binding.verify(report)
            if not isinstance(verdict, GoalVerification):
                raise ValueError("native lesson verifier returned an invalid verdict")
            succeeded = verdict.status is GoalDecisionOutcome.SUCCEEDED
        except Exception as error:
            # Store the class only, never private exception messages/paths.
            error_type = type(error).__name__
        finally:
            controller.input_enabled = False
            recorder.enabled = False
        try:
            terminal_state = controller.save_state_bytes()
            terminal_sha = sha256(terminal_state).hexdigest()
            after_observation, terminal = capture_player_lesson_snapshot(runtime)
            after_doc = project_registered_observation(
                after_observation, runtime.registration_policy
            ).public_dict()
            unit_terminal = None
            if story_unit is not None:
                unit_terminal = capture_story_unit(runtime, story_unit["target"])
            if controller.save_state_bytes() != terminal_state:
                raise ValueError("native lesson terminal audit changed state")
            result = dict(
                schema=(
                    PREPARATION_OUTCOME_SCHEMA
                    if preparation_lesson
                    else STORY_UNIT_OUTCOME_SCHEMA
                    if story_unit is not None
                    else CHALLENGE_OUTCOME_SCHEMA
                    if challenge is not None
                    else RESOURCE_OUTCOME_SCHEMA
                    if resource
                    else READINESS_OUTCOME_SCHEMA
                ),
                declaration_sha256=declaration,
                after=after_doc,
                succeeded=succeeded,
                trace=recorder.trace,
                terminal_state_sha256=terminal_sha,
                interventions_during_execution=[],
                native_audit=dict(
                    before_sha256=source["state_sha256"],
                    terminal_sha256=terminal_sha,
                    input_frames=0,
                    passed=True,
                ),
                player_lesson=terminal,
            )
            if story_unit is not None:
                result["story_unit"] = unit_terminal
            if resource:
                raw = after_observation.raw
                result["economy_after"] = snapshot_document(
                    EconomySnapshot(
                        raw.player_money,
                        tuple(sorted((f"red-item-{i:03d}", n) for i, n in raw.bag_items)),
                    )
                )
            # An unreadable verifier is infrastructure failure, not a negative
            # gameplay label. Still preserve its snapshots and measured costs.
            if not (stage == "verify" and error_type is not None):
                item = publish_outcome(store, declaration, result)
        except Exception as error:
            stage, error_type = "terminal_admission", type(error).__name__
        diagnostic = dict(
            schema="pokemon.red.native-player-lesson-attempt.v1",
            declaration_sha256=declaration,
            admitted=item is not None,
            outcome=None if item is None else item.public_dict(),
            goal_kind=binding.kind.value,
            selected_index=selected_index,
            succeeded=succeeded if item is not None else False,
            execution_or_verification_failed=error_type is not None,
            error_stage=stage if error_type else None,
            error_type=error_type,
            actions_attempted=len(recorder.trace),
            actions_completed=actions.actions_executed,
            frames=controller.frames_executed,
            elapsed_seconds=monotonic() - started,
            trace=recorder.trace,
            terminal_state_sha256=terminal_sha,
            after=after_doc,
            player_lesson=terminal,
            independent_evaluation=False,
            authority_promotions=0,
            selection_context=dict(
                diagnostic_only=True,
                source_sha256=canonical_sha256(source),
                source_state_sha256=source["state_sha256"],
                source_partition=source["partition"],
                declared_interventions=deepcopy(source.get("interventions")),
                question_sha256=canonical_sha256(plan["question"]),
                alternatives=[
                    dict(
                        candidate_index=i, kind=option.kind.value,
                        available=i in question.available_indices,
                        execution_status=("attempted" if i == selected_index else "unexecuted"),
                        outcome_reference_sha256=(
                            None if i != selected_index or item is None
                            else canonical_sha256(item.public_dict())
                        ),
                    )
                    for i, option in enumerate(question.opportunities)
                ],
                unexecuted_outcomes_are_unknown=True,
                comparative_labels_created=False,
                automatic_training_admission=False,
            ),
        )
        store.publish_sealed_record(
            "rnl-attempt-" + declaration, kind="red_native_lesson_attempt", record=diagnostic
        )
        return diagnostic


def review_player_progress_retention(
    outcomes, *, stall_window, repeat_window, required_objectives=(),
    required_owned_species=(), resource_target=None, training_specimen_refs=(),
):
    """Review one closed episode; never choose an action or control a live player.

    Caller declares endpoints and review windows before a policy comparison.
    A warning requests evidence review, not an automatic stop or a label that
    legitimate travel, recovery or income was wasted. Targeted trainee XP may
    count; incidental carry XP during earning must not conceal a support loop.
    """
    for value in (stall_window, repeat_window):
        if type(value) is not int or value < 1:
            raise ValueError("progress review windows must be positive integers")
    if resource_target is not None and (type(resource_target) is not int or resource_target < 0):
        raise ValueError("progress review resource target must be nonnegative")
    declared = []
    for values in (required_objectives, required_owned_species, training_specimen_refs):
        if not isinstance(values, (tuple, list)) or any(not isinstance(v, str) or not v for v in values):
            raise ValueError("progress review declarations must contain names")
        declared.append(frozenset(values))
    objectives, species, trainees = declared
    rows = tuple(outcomes)
    if any(not isinstance(row, Mapping) for row in rows):
        raise TypeError("progress review needs outcome mappings")

    def names(facts, key):
        value = facts.get(key)
        return (frozenset(value) if isinstance(value, (tuple, list))
                and all(isinstance(v, str) for v in value) else None)

    def training_xp(facts):
        lesson = facts.get("player_lesson")
        party = lesson.get("party") if isinstance(lesson, Mapping) else None
        if not isinstance(party, (tuple, list)):
            return None
        found = {v.get("specimen_ref"): v.get("experience") for v in party if isinstance(v, Mapping)}
        if not trainees.issubset(found) or any(type(found[v]) is not int for v in trainees):
            return None
        return sum(found[v] for v in trainees)

    events, warnings = [], []
    idle = support = errors = unsafe = chain_breaks = unknown = 0
    longest_idle = longest_support = 0
    prior_terminal = None
    for index, row in enumerate(rows):
        before, after = row.get("before"), row.get("after")
        if not isinstance(before, Mapping) or not isinstance(after, Mapping):
            before, after = {}, {}
        old_o, new_o = names(before, "completed_objectives"), names(after, "completed_objectives")
        old_s, new_s = names(before, "owned_species"), names(after, "owned_species")
        known = old_o is not None and new_o is not None and old_s is not None and new_s is not None
        signals = []
        if old_o is not None and new_o is not None and new_o - old_o:
            signals.append("objective_added")
        if old_s is not None and new_s is not None and new_s - old_s:
            signals.append("registration_added")
        kind = row.get("selected_kind")
        if kind in {"evolve_species", "develop_team"}:
            old_x, new_x = training_xp(before), training_xp(after)
            if trainees and old_x is not None and new_x is not None:
                if new_x > old_x:
                    signals.append("declared_trainee_xp")
            elif not signals:
                known = False
        old_cash, new_cash = before.get("cash"), after.get("cash")
        if resource_target is not None:
            if type(old_cash) is int and type(new_cash) is int:
                if max(0, resource_target - new_cash) < max(0, resource_target - old_cash):
                    signals.append("declared_funding_gap_reduced")
            else:
                known = False
        safe = row.get("safe_terminal") is True
        verdict = row.get("verification")
        errors += (row.get("error_type") is not None or row.get("error") is not None
                   or verdict != "succeeded" and not (verdict == "failed"
                   and row.get("ordinary_setback") is True and safe))
        unsafe += not safe
        initial, terminal = row.get("before_state_sha256"), row.get("terminal_state_sha256")
        hashes_known = all(isinstance(v, str) and len(v) == 64
                           and all(char in "0123456789abcdef" for char in v)
                           for v in (initial, terminal))
        if not hashes_known or (prior_terminal is not None and initial != prior_terminal):
            chain_breaks += 1
        prior_terminal = terminal if hashes_known else None
        if not known:
            unknown += 1
        if signals:
            idle = support = 0
        elif known:
            idle += 1
            support = support + 1 if kind in {"restore_team", "resupply"} else 0
        else:
            idle = support = 0
        longest_idle, longest_support = max(longest_idle, idle), max(longest_support, support)
        if idle == stall_window:
            warnings.append(dict(index=index,kind="no_verified_declared_progress_window"))
        if support == repeat_window:
            warnings.append(dict(index=index,kind="support_only_without_declared_progress_window"))
        events.append(dict(index=index,selected_kind=kind,progress_signals=signals,
                           progress_known=known,ordinary_setback=bool(row.get("ordinary_setback"))))

    final = rows[-1].get("after", {}) if rows else {}
    if not isinstance(final, Mapping):
        final = {}
    final_o, final_s = names(final, "completed_objectives"), names(final, "owned_species")
    endpoints_declared = bool(objectives or species or resource_target is not None)
    endpoint_known = bool(rows) and (not objectives or final_o is not None) and (not species or final_s is not None)
    endpoints_met = (endpoint_known and (not objectives or objectives.issubset(final_o))
                     and (not species or species.issubset(final_s)))
    if resource_target is not None:
        cash = final.get("cash")
        endpoint_known = endpoint_known and type(cash) is int
        endpoints_met = endpoints_met and type(cash) is int and cash >= resource_target
    eligible = bool(endpoints_declared and endpoints_met and not errors and not unsafe
                    and not chain_breaks and not unknown and not warnings)
    return dict(
        schema="pokemon.red.player-progress-retention-review.v1",diagnostic_only=True,
        outcomes=len(rows),endpoints_declared=endpoints_declared,
        endpoints_met=bool(endpoints_met) if endpoints_declared and endpoint_known else None,
        eligible_for_declared_retention_review=eligible,
        review_status="criteria_met" if eligible else "needs_evidence_review",
        required_objectives=sorted(objectives),required_owned_species=sorted(species),
        resource_target=resource_target,training_specimen_refs=sorted(trainees),
        stall_window=stall_window,repeat_window=repeat_window,
        longest_known_no_progress_run=longest_idle,longest_support_only_no_progress_run=longest_support,
        unknown_progress_rows=unknown,state_chain_breaks=chain_breaks,
        execution_or_verification_errors=errors,unsafe_or_unverified_terminals=unsafe,
        ordinary_setbacks=sum(v["ordinary_setback"] for v in events),
        warnings=warnings,events=events,
        progress_is_not_defined_by_frames_or_inputs=True,
        warnings_are_not_proof_of_waste=True,training_admission=False,automatic_fit=False,
        native_qualification_required_separately=True,
        additional_inputs_authorized=False,automatic_stop=False,automatic_resume=False,
    )
