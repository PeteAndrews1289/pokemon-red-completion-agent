"""Narrow, opt-in contract for continuous paid-search / native-exchange play.

This is a referee, never a destination selector. Unknown mechanics stop rather
than disappearing from the menu. Failed searches remain failed examples.
"""

from collections import Counter
from collections.abc import Mapping
from dataclasses import replace

from .goal_manager import GoalDecisionOutcome, GoalFailureReason, GoalKind
from .goal_manager_runtime import GoalExecutionReport, GoalVerification
from .goal_search_memory import GoalSearchMemory
from .provenance import canonical_sha256
from .route_executor import (
    ExecutedRouteStep,
    RouteExecutionError,
    RouteExecutionFailureReason,
    RouteExecutionFailureReport,
    TraversalSnapshot,
)
from .route_plan import RoutePlanningError

PAID_SEARCH = "pokemon.red:paid-safari:"
NATIVE_EXCHANGE = "pokemon.red:npc-trade:"


def observable_player_boundary(snapshot):
    """Field control, not full health: fainted team members may need recovery.

    The native adapter still owns `safe` and protected-item/story checks. These
    explicit independent facts exclude battle and missing progress evidence.
    Unsettled input is observable here, but the runner permits only an explicit
    control-recovery support action until settled_player_boundary passes.
    """
    facts = snapshot.facts
    if (
        not snapshot.safe
        or type(facts.get("battle_state")) is not int
        or facts["battle_state"] != 0
        or facts.get("buttons_released") is not True
    ):
        return False
    for name in ("owned_species", "completed_objectives"):
        values = facts.get(name)
        if (
            not isinstance(values, (list, tuple))
            or any(not isinstance(value, str) or not value for value in values)
            or len(set(values)) != len(values)
        ):
            return False
    counts = facts.get("specimen_counts")
    return (
        isinstance(counts, Mapping)
        and bool(counts)
        and all(
            isinstance(key, str) and bool(key) and type(value) is int and value > 0
            for key, value in counts.items()
        )
    )


def settled_player_boundary(snapshot):
    return observable_player_boundary(snapshot) and snapshot.facts.get("input_ready") is True


def ordinary_player_setback(binding, before, terminal, report, verification, error):
    """Continue only after a measured settled game setback, never unknown failure.

    No new success label, replay, heal, or target substitution occurs here. The
    next iteration must observe and select again. Partial macros, unverified
    progress, loss of registrations/specimens/story facts and exceptions stop.
    """
    if (
        error is not None
        or not isinstance(report, GoalExecutionReport)
        or not isinstance(verification, GoalVerification)
        or verification.status is not GoalDecisionOutcome.FAILED
        or not settled_player_boundary(before)
        or not settled_player_boundary(terminal)
        or measured_cost(before.facts, terminal.facts, report) is None
    ):
        return False
    reasons = {
        GoalKind.EXPLORE: {GoalFailureReason.SEARCH_EXHAUSTED},
        GoalKind.ADVANCE_STORY: {
            GoalFailureReason.RECOVERY_REQUIRED,
            GoalFailureReason.RESOURCE_LOST,
        },
        GoalKind.DEVELOP_TEAM: {
            GoalFailureReason.RECOVERY_REQUIRED,
            GoalFailureReason.RESOURCE_LOST,
        },
        GoalKind.ACQUIRE_SPECIES: {
            GoalFailureReason.SEARCH_EXHAUSTED,
            GoalFailureReason.CAPTURE_ITEMS_EXHAUSTED,
            GoalFailureReason.RESOURCE_LOST,
        },
    }
    route_loss = _settled_route_trainer_loss(binding, terminal, report)
    route_recovery = (_settled_route_trainer_recovery(binding, terminal, report)
                      or _settled_route_field_recovery(binding, terminal, report))
    route_stop = route_loss or route_recovery
    destination_unavailable = _settled_evolution_destination_unavailable(
        binding, before, terminal, report
    )
    if binding.kind is GoalKind.DEVELOP_TEAM and _settled_partial_preparation(
        binding, before, terminal, report
    ):
        reasons[GoalKind.DEVELOP_TEAM].add(GoalFailureReason.EXECUTION_BUDGET_EXHAUSTED)
    if binding.kind is GoalKind.RESUPPLY and _settled_field_delivery_stop(
        binding, before, terminal, report
    ):
        reasons[GoalKind.RESUPPLY] = {GoalFailureReason.OUTCOME_NOT_VERIFIED}
    if binding.kind is GoalKind.RESUPPLY and _settled_league_funding_loss(binding, terminal, report):
        reasons[GoalKind.RESUPPLY] = {GoalFailureReason.RESOURCE_LOST}
    if "route_setback" in report.evidence and not route_stop:
        return False
    if route_loss:
        reasons[binding.kind] = reasons.get(binding.kind, set()) | {GoalFailureReason.RESOURCE_LOST}
    if route_recovery:
        reasons[binding.kind] = {GoalFailureReason.RECOVERY_REQUIRED}
    if destination_unavailable:
        reasons[GoalKind.EVOLVE_SPECIES] = {GoalFailureReason.BINDING_FAILED}
    if binding.kind is GoalKind.EVOLVE_SPECIES and not (route_stop or destination_unavailable):
        # A finite dose stopped at its declared bound with a verified PC return. It
        # remains a failed evolution, not a success or a command to retry it.
        # The next model choice may resume, heal, earn, or choose another goal.
        if not settled_evolution_partial(binding, report):
            return False
        reasons[GoalKind.EVOLVE_SPECIES] = {GoalFailureReason.OUTCOME_NOT_VERIFIED}
    if binding.kind is GoalKind.ACQUIRE_SPECIES and settled_evolution_partial(binding, report):
        reasons[GoalKind.ACQUIRE_SPECIES] = {GoalFailureReason.OUTCOME_NOT_VERIFIED}
    if binding.kind is GoalKind.EXPLORE and not (
        report.evidence.get("bounded") is True
        and report.evidence.get("search_exhausted") is True
        and type(report.evidence.get("new_sighting_count")) is int
        and report.evidence["new_sighting_count"] == 0
        and type(report.evidence.get("captures")) is int
        and report.evidence["captures"] == 0
        and report.evidence.get("search_stop_reason")
        in {"survey_leg_limit_exceeded", "encounter_limit_reached", "seek_step_limit_reached"}
    ):
        return False
    if binding.kind is GoalKind.RESTORE_TEAM and not route_stop:
        blackout = report.evidence.get("native_blackout_during_selected_restoration")
        if (
            not isinstance(blackout, Mapping)
            or blackout.get("blackout_verified") is not True
            or blackout.get("learned_recovery") is not False
            or blackout.get("nurse_interaction") is not False
            or type(before.facts.get("cash")) is not int
            or blackout.get("cash_before") != before.facts["cash"]
            or blackout.get("cash_after") != terminal.facts.get("cash")
            or terminal.facts.get("cash") != before.facts["cash"] // 2
            or blackout.get("cash_lost") != before.facts["cash"] - terminal.facts["cash"]
        ):
            return False
        reasons[GoalKind.RESTORE_TEAM] = {GoalFailureReason.RESOURCE_LOST}
    if binding.kind is GoalKind.RECOVER_CONTROL:
        battle = report.evidence.get("battle")
        if (
            binding.binding_ref != "pokemon.red:retained-engagement:" + before.sha256
            or report.evidence.get("support") != "already_engaged_native_trainer"
            or report.evidence.get("source_sha256") != before.sha256
            or report.evidence.get("terminal_sha256") != terminal.sha256
            or report.evidence.get("objective_completed") is not False
            or report.evidence.get("reward") is not None
            or not isinstance(battle, Mapping)
            or battle.get("schema") != "pokemon.red.learned-trainer-completion.v1"
            or battle.get("outcome") != "lost"
            or battle.get("field_ready") is not True
            or type(before.facts.get("cash")) is not int
            or type(terminal.facts.get("cash")) is not int
            or terminal.facts["cash"] != before.facts["cash"] // 2
            or type(battle.get("money_delta")) is not int
            or battle["money_delta"] != terminal.facts["cash"] - before.facts["cash"]
        ):
            return False
        reasons[GoalKind.RECOVER_CONTROL] = {GoalFailureReason.RESOURCE_LOST}
    if verification.failure_reason not in reasons.get(binding.kind, set()):
        return False
    return (
        set(before.facts["owned_species"]) <= set(terminal.facts["owned_species"])
        and set(before.facts["completed_objectives"]) <= set(terminal.facts["completed_objectives"])
        and (
            (before.facts["specimen_counts"] == terminal.facts["specimen_counts"]
             and (not route_stop or set(before.facts["owned_species"])
                  == set(terminal.facts["owned_species"])))
            or (
                (
                    route_stop
                    or binding.kind in {GoalKind.DEVELOP_TEAM, GoalKind.EVOLVE_SPECIES}
                    or (
                        binding.kind is GoalKind.ACQUIRE_SPECIES
                        and verification.failure_reason is GoalFailureReason.RESOURCE_LOST
                        and _settled_capture_trip_stop(report)
                    )
                    or (
                        binding.kind is GoalKind.ACQUIRE_SPECIES
                        and verification.failure_reason is GoalFailureReason.SEARCH_EXHAUSTED
                        and _settled_capture_trip_stop(report, exhausted=True)
                    )
                )
                and _retained_evolution_census(
                    before.facts, terminal.facts,
                    require_exact_owned=route_stop or binding.kind is GoalKind.ACQUIRE_SPECIES,
                )
            )
            or (
                binding.kind is GoalKind.ACQUIRE_SPECIES
                and (captures := _settled_partial_capture_events(
                    report, native_local_source=_native_local_capture_source(
                        binding, before, terminal,
                    ),
                )) is not None
                and _retained_evolution_census(
                    before.facts, terminal.facts, captures=captures
                )
            )
        )
    )


def settled_evolution_partial(binding, report):
    """Recognize the dose receipt; callers still verify costs and native custody.

    A trade prerequisite remains an incomplete trade. Only its independently
    verified partial evolution may renew the same finite execution boundary.
    """
    evidence = report.evidence
    if binding.kind is GoalKind.ACQUIRE_SPECIES:
        if (
            not getattr(binding, "binding_ref", "").startswith("red-npc-trade-dependency:")
            or evidence.get("mechanic") != "trade_level_dependency"
            or evidence.get("complete") is not False
            or evidence.get("intermediate_verification") != {
                "status": GoalDecisionOutcome.FAILED.value,
                "failure_reason": GoalFailureReason.OUTCOME_NOT_VERIFIED.value,
            }
        ):
            return False
        evidence = evidence.get("intermediate")
    elif binding.kind is not GoalKind.EVOLVE_SPECIES:
        return False
    if not isinstance(evidence, Mapping):
        return False
    routed = (
        evidence.get("schema") == "pokemon.core.routed-semantic-goal-report.v1"
        and evidence.get("destination_kind") == GoalKind.EVOLVE_SPECIES.value
        and all(
            evidence.get(name) is True
            for name in (
                "budget_reconciled",
                "destination_bound",
                "destination_executed",
                "route_verified",
                "within_budget",
            )
        )
    )
    native = (
        evidence.get("schema") == "pokemon.red.native-evolution-partial.v1"
        and evidence.get("bounded") is True
        and all(
            type(evidence.get(name)) is str and evidence[name].startswith("pokemon:national:")
            for name in ("source_species_ref", "target_species_ref")
        )
        and evidence["source_species_ref"] != evidence["target_species_ref"]
    )
    quantum_stop = (
        evidence.get("quantum_limit_reached") is True
        and type(evidence.get("completed_training_quanta")) is int
        and type(evidence.get("maximum_training_quanta")) is int
        and 1 <= evidence["maximum_training_quanta"] <= 512
        and evidence["completed_training_quanta"] == evidence["maximum_training_quanta"]
    )
    if (
        not (routed or native)
        or evidence.get("evolution_partial") is not True
        or evidence.get("retained_active_roster_restored") is not True
        or not (
            evidence.get("settlement_reserve_reached") is True
            or evidence.get("wall_limit_reached") is True
            or quantum_stop
        )
        or type(evidence.get("completed_training_battles")) is not int
        or evidence["completed_training_battles"] <= 0
    ):
        return False
    return True


def _settled_partial_preparation(binding, before, terminal, report):
    """Admit one verified productive dose, never a global budget exception.

    The native binding independently validates the entire report and boundary.
    Here the receipt must also match actual terminal identity, target/XP facts,
    exact dose allowance and the existing outer cost/custody checks.
    """
    evidence = report.evidence
    if binding.binding_ref.startswith((
        "pokemon.red:routed-preparation:", "pokemon.red:member-preparation:",
    )):
        # Member selection wraps the same routed executor with an identity for
        # its exact trainee/target; it does not change the report or verifier.
        if (evidence.get("mechanic") != "routed_preparation"
                or evidence.get("support") != "cartridge_route_then_fresh_binding"):
            return False
        evidence = evidence.get("preparation")
    elif not binding.binding_ref.startswith("pokemon.red:bounded-preparation:"):
        return False
    if not isinstance(evidence, Mapping):
        return False
    partial = evidence.get("bounded_partial_preparation")
    if not isinstance(partial, Mapping):
        return False
    if (
        partial.get("schema") != "pokemon.red.preparation-partial.v1"
        or partial.get("terminal_sha256") != terminal.sha256
        or partial.get("target_reached") is not False
        or partial.get("fully_restored") is not True
        or partial.get("stop_reason") != "encounter_limit"
        or any(type(partial.get(k)) is not int for k in (
            "target_level", "initial_level", "terminal_level", "initial_xp", "terminal_xp",
            "encounter_allowance", "encounters",
        ))
        or not (1 <= partial["initial_level"] <= partial["terminal_level"]
                < partial["target_level"] <= 100)
        or not 0 <= partial["initial_xp"] < partial["terminal_xp"]
        or not 1 <= partial["encounters"] == partial["encounter_allowance"] <= 128
        or not isinstance(partial.get("trainee_ref"), str)
    ):
        return False
    members = []
    for snapshot in (before, terminal):
        lesson = snapshot.facts.get("player_lesson")
        if (not isinstance(lesson, Mapping)
                or lesson.get("schema") != "pokemon.red.player-lesson-snapshot.v1"):
            return False
        party = lesson.get("party")
        if not isinstance(party, (list, tuple)) or not all(isinstance(m, Mapping) for m in party):
            return False
        match = [m for m in party if m.get("specimen_ref") == partial["trainee_ref"]]
        if len(match) != 1:
            return False
        members.append(match[0])
    old, new = members
    return (
        type(old.get("experience")) is int
        and type(old.get("level")) is int
        and 0 <= old["experience"] <= partial["initial_xp"]
        and 1 <= old["level"] <= partial["initial_level"]
        and new.get("experience") == partial["terminal_xp"]
        and new.get("level") == partial["terminal_level"]
    )


def _settled_field_delivery_stop(binding, before, terminal, report):
    """One certified failed free delivery, not unknown exceptions or stock credit."""
    e = report.evidence
    lessons = [s.facts.get("player_lesson") for s in (before, terminal)]
    if not all(isinstance(lesson, Mapping)
               and lesson.get("schema") == "pokemon.red.player-lesson-snapshot.v1"
               for lesson in lessons):
        return False
    parties = [lesson.get("party") for lesson in lessons]
    bags = []
    for snapshot in (before, terminal):
        diagnostic = snapshot.facts.get("diagnostics")
        bag = snapshot.facts.get("bag_items")
        if bag is None and isinstance(diagnostic, Mapping):
            bag = diagnostic.get("bag_items")
        bags.append(bag)
    return (
        e.get("schema") == "pokemon.red.field-delivery-route-stop.v1"
        and e.get("support") == "cartridge_finite_field_resupply_stop"
        and e.get("route_unavailable") is True
        and e.get("protected_native_state_unchanged") is True
        and e.get("item_acquired") is False
        and e.get("complete_delivery") is False
        and e.get("objective_completed") is False
        and all(type(e.get(k)) is int and e[k] == 0
                for k in ("quantity_acquired", "purchases", "cash_debit"))
        and type(e.get("item")) is int and 1 <= e["item"] <= 250
        and binding.binding_ref
        == "pokemon.red:field-resupply:" + before.sha256 + ":" + str(e["item"])
        and type(e.get("quoted_navigation_transitions")) is int
        and e["quoted_navigation_transitions"] > 1
        and e.get("source_sha256") == before.sha256
        and e.get("terminal_sha256") == terminal.sha256
        and report.actions_executed > 0 and report.frames_executed > 0
        and before.facts.get("cash") == terminal.facts.get("cash")
        and isinstance(parties[0], (tuple, list)) and 1 <= len(parties[0]) <= 6
        and parties[0] == parties[1]
        and isinstance(bags[0], (tuple, list)) and bags[0] == bags[1]
        and before.facts.get("specimen_counts") == terminal.facts.get("specimen_counts")
        and set(before.facts.get("owned_species", ()))
        == set(terminal.facts.get("owned_species", ()))
        and set(before.facts.get("completed_objectives", ()))
        == set(terminal.facts.get("completed_objectives", ()))
    )


def _settled_evolution_destination_unavailable(binding, before, terminal, report):
    """A completed route may invalidate an evolution offer; reobserve, never retry.

    The original destination remains failed. Only its typed no-target refusal,
    measured settled route and exact guarded census permit another model choice.
    """
    from .destination_unavailable import DestinationUnavailableSummary
    from .goal_manager import GoalUnavailableReason

    e = report.evidence
    if (
        binding.kind is not GoalKind.EVOLVE_SPECIES
        or e.get("schema") != "pokemon.core.routed-semantic-goal-report.v1"
        or e.get("destination_kind") != binding.kind.value
        or not all(e.get(name) is True for name in (
            "route_verified", "budget_reconciled", "within_budget"))
        or not all(e.get(name) is False for name in (
            "destination_bound", "destination_executed", "route_is_policy_kind"))
        or any(type(e.get(name)) is not int or e[name] != 0 for name in (
            "private_binding_fields", "private_route_fields"))
    ):
        return False
    try:
        unavailable = DestinationUnavailableSummary.from_evidence(e)
    except ValueError:
        return False
    return (
        unavailable is not None
        and unavailable.reason is GoalUnavailableReason.NO_LEGAL_TARGET
        and _retained_evolution_census(
            before.facts, terminal.facts, require_exact_owned=True, require_progress=False
        )
    )


def _settled_route_trainer_loss(binding, terminal, report):
    """A proven route blackout is not arrival or completion of its destination."""
    from .red_player_engaged_story import settled_route_trainer_loss_evidence

    return _settled_route_trainer_stop(binding, terminal, report, settled_route_trainer_loss_evidence)


def _settled_route_trainer_recovery(binding, terminal, report):
    from .red_player_engaged_story import settled_route_trainer_recovery_evidence

    if not _settled_route_trainer_stop(binding, terminal, report, settled_route_trainer_recovery_evidence):
        return False
    hp = (terminal.facts.get("diagnostics") or {}).get("party_hp")
    return isinstance(hp, (tuple, list)) and list(hp) == report.evidence["route_setback"]["party_hp"]


def _settled_route_field_recovery(binding, terminal, report):
    from .red_routed_recovery import settled_route_field_recovery_evidence

    if not _settled_route_trainer_stop(binding, terminal, report, settled_route_field_recovery_evidence):
        return False
    hp = (terminal.facts.get("diagnostics") or {}).get("party_hp")
    return isinstance(hp, (tuple, list)) and list(hp) == report.evidence["route_setback"]["party_hp"]


def _settled_route_trainer_stop(binding, terminal, report, validator):
    evidence = report.evidence
    loss = evidence.get("route_setback")
    chain = evidence.get("route_setback_destination_chain", ())
    if (not isinstance(chain, (tuple, list)) or len(chain) > 8
        or any(not isinstance(node, Mapping) for node in chain)):
        return False
    actions, frames = report.actions_executed, report.frames_executed
    nodes = [evidence, *chain]
    for index, node in enumerate(nodes):
        if (node.get("schema") != "pokemon.core.routed-semantic-goal-report.v1"
            or node.get("destination_kind") != binding.kind.value
            or node.get("budget_reconciled") is not True
            or node.get("within_budget") is not True):
            return False
        # Every outer transport succeeded and invoked a routed destination.
        # Only the final route stopped before its semantic destination ran.
        expected = index < len(nodes) - 1
        if any(node.get(key) is not expected for key in (
            "route_verified", "destination_bound", "destination_executed"
        )):
            return False
        if index:
            child_actions, child_frames = node.get("actions"), node.get("frames")
            if (type(child_actions) is not int or type(child_frames) is not int
                or not 0 <= child_actions <= actions or not 0 <= child_frames <= frames):
                return False
            actions, frames = child_actions, child_frames
    return (
        validator(loss)
        and loss["terminal_sha256"] == terminal.sha256
        and loss["cash_after"] == terminal.facts.get("cash")
        and actions >= loss["actions"]
        and frames >= loss["frames"]
    )


def _settled_capture_trip_stop(report, *, exhausted=False):
    """A completed route and certified uncaptured health/search stop.

    An earned evolution during that route is not a lost specimen. The separate
    individual guard must still prove the entire census. After search begins,
    every completed search/flee/failed throw must reconcile with its diagnostics.
    This never grants capture credit or admits a partial action/route/error.
    """
    evidence = report.evidence
    survey = evidence.get("capture_survey")
    admitted = (
        evidence.get("schema") == "pokemon.core.routed-semantic-goal-report.v1"
        and all(
            evidence.get(name) is True
            for name in (
                "budget_reconciled",
                "destination_bound",
                "destination_executed",
                "route_verified",
                "within_budget",
            )
        )
        and evidence.get("destination_kind") == GoalKind.ACQUIRE_SPECIES.value
        and isinstance(survey, Mapping)
        and survey.get("safety_stopped") is (not exhausted)
        and survey.get("search_exhausted") is exhausted
        and (
            not exhausted
            or (
                survey.get("search_stop_reason") == "survey_leg_limit_exceeded"
                and survey.get("capture_items_exhausted", False) is False
            )
        )
        and all(
            type(survey.get(name)) is int and survey[name] >= 0
            for name in ("captures", "encounters_seen", "semantic_actions", "flees")
        )
        and survey["captures"] == 0
    )
    if not admitted:
        return False
    if not exhausted and all(
        survey[name] == 0 for name in ("encounters_seen", "semantic_actions", "flees")
    ):
        return True
    diagnostics = evidence.get("capture_diagnostics")
    if (not isinstance(diagnostics, Mapping)
            or diagnostics.get("schema") != "pokemon.red.capture-survey-diagnostics.v1"
            or diagnostics.get("diagnostic_only") is not True
            or not isinstance(diagnostics.get("events"), (list, tuple))):
        return False
    events = diagnostics["events"]
    if not events or any(not isinstance(event, Mapping) for event in events):
        return False
    source = events[0].get("source_id")
    if not isinstance(source, str) or not source:
        return False
    last_ordinal = -1
    actions = []
    for event in events:
        ordinal = event.get("event_ordinal")
        if (type(ordinal) is not int or ordinal <= last_ordinal
                or event.get("source_id") != source
                or event.get("selection_authority") != "deterministic_capture_support"
                or event.get("kind") == "capture_verified"):
            return False
        last_ordinal = ordinal
        if event.get("kind") == "survey_action_failed" and not (
            exhausted
            and event is events[-1]
            and event.get("operation") == "seek_encounter"
            and event.get("error_type") == "RedAreaExecutionError"
            and event.get("reason_code") == "survey_leg_limit_exceeded"
        ):
            return False
        if event.get("kind") == "survey_action_returned":
            operation = event.get("operation")
            expected = False if operation == "capture_encounter" else None
            if (operation not in {"seek_encounter", "flee_encounter", "capture_encounter"}
                    or event.get("returned") is not expected):
                return False
            actions.append(operation)
    failed = actions.count("capture_encounter")
    flees = actions.count("flee_encounter")
    final_review = events[-1].get("diagnostic_review")
    no_input_search_stop = (
        isinstance(final_review, Mapping)
        and final_review.get("schema") == "pokemon.red.survey-operation-diagnostics.v1"
        and final_review.get("diagnostic_only") is True
        and final_review.get("operation") == "seek_encounter"
        and isinstance(final_review.get("measured"), Mapping)
        and all(
            type(final_review["measured"].get(name)) is int
            and final_review["measured"][name] == 0
            for name in ("native_actions", "native_frames")
        )
    )
    return (
        len(actions) + int(exhausted) == survey["semantic_actions"]
        and failed + flees == survey["encounters_seen"] == survey["flees"]
        and all(type(diagnostics.get(name)) is int and diagnostics[name] == count
                for name, count in (("capture_attempts", failed),
                                    ("failed_capture_attempts", failed),
                                    ("direct_flees", flees)))
        and sum(event.get("kind") == "capture_not_retained" for event in events) == failed
        and (
            (
                exhausted
                and events[-1].get("kind") == "survey_action_failed"
                and events[-1].get("operation") == "seek_encounter"
                and events[-1].get("error_type") == "RedAreaExecutionError"
                and events[-1].get("reason_code") == "survey_leg_limit_exceeded"
                and no_input_search_stop
            )
            or (
                not exhausted
                and events[-1].get("kind") == "survey_stopped"
                and events[-1].get("reason") == "safety_check_failed"
                and events[-1].get("semantic_actions") == survey["semantic_actions"]
            )
        )
    )


def _native_local_capture_source(binding, before, terminal):
    """Identify an existing local wild skill at one unchanged observed map."""
    prefix = "pokemon.red:acquisition:"
    ref = binding.binding_ref
    if not isinstance(ref, str) or not ref.startswith(prefix):
        return None
    head, separator, _ = ref.partition(":profile-")
    source = head[len(prefix):]
    if not separator or not source.startswith("wild:"):
        return None
    maps = []
    for snapshot in (before, terminal):
        diagnostics = snapshot.facts.get("diagnostics")
        if not isinstance(diagnostics, Mapping):
            return None
        map_id = diagnostics.get("map_id")
        if type(map_id) is not int or map_id < 0:
            return None
        maps.append(map_id)
    return source if maps[0] == maps[1] else None


def _native_local_partial_capture_report(evidence, survey, source):
    """Recognize the existing bounded local report, not an unknown wrapper."""
    if (not isinstance(source, str) or not source.startswith("wild:")
            or "schema" in evidence or evidence.get("bounded") is not True
            or type(evidence.get("source_normalized")) is not bool
            or not isinstance(survey, Mapping)):
        return False
    for name in ("captures", "encounters_seen", "semantic_actions", "flees"):
        if type(evidence.get(name)) is not int or evidence[name] != survey.get(name):
            return False
    for name in ("safety_stopped", "search_exhausted"):
        if type(evidence.get(name)) is not bool or evidence[name] is not survey.get(name):
            return False
    names = ("initial_missing", "final_missing", "initial_missing_specimens", "final_missing_specimens")
    if any(type(evidence.get(name)) is not int for name in names):
        return False
    return (
        0 < evidence["final_missing"] <= evidence["initial_missing"]
        and 0 < evidence["final_missing_specimens"] < evidence["initial_missing_specimens"]
        and evidence["initial_missing_specimens"] - evidence["final_missing_specimens"]
        == survey.get("captures")
    )


def _settled_partial_capture_events(report, *, native_local_source=None):
    """Completed failed survey receipts, not a waiver for unexplained stock gains."""
    evidence = report.evidence
    survey, diagnostics = evidence.get("capture_survey"), evidence.get("capture_diagnostics")
    routed = (
        evidence.get("schema") == "pokemon.core.routed-semantic-goal-report.v1"
        and evidence.get("destination_kind") == GoalKind.ACQUIRE_SPECIES.value
        and all(evidence.get(name) is True for name in (
            "budget_reconciled", "destination_bound", "destination_executed",
            "route_verified", "within_budget"))
    )
    native_local = _native_local_partial_capture_report(evidence, survey, native_local_source)
    if (
        not (routed or native_local)
        or not isinstance(survey, Mapping)
        or any(type(survey.get(name)) is not int or survey[name] < 0 for name in (
            "captures", "encounters_seen", "semantic_actions", "flees"))
        or survey["captures"] <= 0
        or survey["encounters_seen"] < survey["captures"]
        or survey["semantic_actions"] < survey["captures"]
        or type(survey.get("safety_stopped")) is not bool
        or type(survey.get("search_exhausted")) is not bool
        or survey["safety_stopped"] == survey["search_exhausted"]
        or not isinstance(diagnostics, Mapping)
        or diagnostics.get("schema") != "pokemon.red.capture-survey-diagnostics.v1"
        or diagnostics.get("diagnostic_only") is not True
        or not isinstance(diagnostics.get("events"), (list, tuple))
        or any(not isinstance(event, Mapping) for event in diagnostics["events"])
    ):
        return None
    captures = tuple(event for event in diagnostics["events"]
                     if event.get("kind") == "capture_verified")
    if len(captures) != survey["captures"]:
        return None
    last_ordinal, source_id = -1, None
    for event in captures:
        if (
            event.get("selection_authority") != "deterministic_capture_support"
            or not isinstance(event.get("source_id"), str) or not event["source_id"]
            or type(event.get("event_ordinal")) is not int
            or event["event_ordinal"] <= last_ordinal
            or not isinstance(event.get("species_ref"), str) or not event["species_ref"]
            or any(type(event.get(name)) is not int or event[name] < 0 for name in (
                "specimen_count_before", "specimen_count_after"))
            or event["specimen_count_after"] != event["specimen_count_before"] + 1
            or not isinstance(event.get("new_owned_species"), (list, tuple))
        ):
            return None
        if source_id is not None and event["source_id"] != source_id:
            return None
        if native_local and event["source_id"] != native_local_source:
            return None
        last_ordinal, source_id = event["event_ordinal"], event["source_id"]
    return captures


def _retained_evolution_census(
    before, after, *, captures=(), require_exact_owned=False, require_progress=True
):
    """Exact retained individuals plus earned evolution and verified capture stock."""
    a, b = (facts.get("retained_party_continuation") for facts in (before, after))
    if (
        not isinstance(a, Mapping)
        or not isinstance(b, Mapping)
        or a.get("schema") != "pokemon.red.retained-party-continuation.v1"
        or b.get("schema") != a["schema"]
        or a.get("native_identity_verified") is not True
        or b.get("native_identity_verified") is not True
        or not isinstance(a.get("guard_sha256"), str)
        or len(a["guard_sha256"]) != 64
        or b.get("guard_sha256") != a["guard_sha256"]
        or not isinstance(a.get("individuals"), Mapping)
        or not isinstance(b.get("individuals"), Mapping)
        or not a["individuals"]
        or a["individuals"].keys() != b["individuals"].keys()
        or not isinstance(a.get("other_specimen_counts"), Mapping)
        or not isinstance(b.get("other_specimen_counts"), Mapping)
    ):
        return False
    for proof, facts in ((a, before), (b, after)):
        census = Counter(proof["other_specimen_counts"])
        if any(
            not isinstance(k, str) or not k or type(v) is not int or v <= 0
            for k, v in census.items()
        ):
            return False
        for ref, m in proof["individuals"].items():
            if (
                not isinstance(ref, str)
                or not ref
                or not isinstance(m, Mapping)
                or not isinstance(m.get("species_ref"), str)
                or not m["species_ref"]
                or type(m.get("level")) is not int
                or not 1 <= m["level"] <= 100
                or type(m.get("experience")) is not int
                or m["experience"] < 0
            ):
                return False
            census[m["species_ref"]] += 1
        if dict(census) != facts["specimen_counts"]:
            return False
    changed = False
    for ref, old in a["individuals"].items():
        new = b["individuals"][ref]
        if new["level"] < old["level"] or new["experience"] < old["experience"]:
            return False
        if old["species_ref"] != new["species_ref"]:
            if new["level"] <= old["level"] or new["experience"] <= old["experience"]:
                return False
            changed = True
    # Only actual capture receipts can explain newly counted unreserved stock.
    # Route-time evolution changes the guarded individuals, not the other stock.
    additions = Counter()
    running = Counter(a["other_specimen_counts"])
    running.update(m["species_ref"] for m in b["individuals"].values())
    owned = set(before["owned_species"]) | {
        m["species_ref"] for m in b["individuals"].values()
    }
    for event in captures:
        ref = event["species_ref"]
        if event["specimen_count_before"] != running[ref]:
            return False
        expected_owned = [] if ref in owned else [ref]
        if list(event["new_owned_species"]) != expected_owned:
            return False
        additions[ref] += 1
        running[ref] += 1
        owned.add(ref)
    return (
        dict(Counter(a["other_specimen_counts"]) + additions) == b["other_specimen_counts"]
        and dict(running) == after["specimen_counts"]
        and (not (captures or require_exact_owned) or owned == set(after["owned_species"]))
        and (changed or bool(captures) or not require_progress)
    )


def safe_route_setback(binding, before, terminal, report, verification, error):
    """Certify a narrowly typed dead end or settled, unacknowledged land walk.

    This is accounting for a failed route, not a completed goal report or a
    successful verification. Unknown/wrapped errors, partial inputs, changed
    party/ledger/resources and missing native preservation evidence stay fatal.
    The runner must opt in and obtain a fresh model choice after this receipt.
    """
    if (
        report is not None
        or verification is not None
        or type(error) is not RouteExecutionError
        or type(error.failure) is not RouteExecutionFailureReport
        or error.failure.reason is not error.reason
        or not settled_player_boundary(before)
        or not settled_player_boundary(terminal)
    ):
        return None
    failed_step = None
    if error.reason is RouteExecutionFailureReason.PLANNER_NO_ROUTE:
        if (
            binding.kind is not GoalKind.ACQUIRE_SPECIES
            or type(error.__cause__) is not RoutePlanningError
            or error.__cause__.__cause__ is not None
        ):
            return None
    elif error.reason is RouteExecutionFailureReason.STEP_ACKNOWLEDGEMENT_EXHAUSTED:
        from .actions import MacroActionKind
        from .route_plan import RoutePlan, RouteStep

        failure = error.failure
        if (
            binding.kind not in {GoalKind.ACQUIRE_SPECIES, GoalKind.RESUPPLY}
            or error.__cause__ is not None
            or failure.replans
            or type(failure.initial_plan) is not RoutePlan
            or type(failure.executed_steps) is not tuple
            or any(type(receipt) is not ExecutedRouteStep for receipt in failure.executed_steps)
            or type(failure.movement_requests) is not int
            or failure.movement_requests <= 0
        ):
            return None
        try:
            steps = failure.initial_plan.steps
        except (AttributeError, IndexError, TypeError, ValueError):
            return None
        index = len(failure.executed_steps)
        if index >= len(steps) or any(
            receipt.step != step
            for receipt, step in zip(failure.executed_steps, steps[:index], strict=True)
        ):
            return None
        failed_step = steps[index]
        if (
            type(failed_step) is not RouteStep
            or not failed_step.can_discover_blocker
            or failed_step.kind != "walk"
            or failed_step.action_kind is not MacroActionKind.MOVE
            or failed_step.action not in {"up", "down", "left", "right"}
            or failed_step.source_mode != "land"
            or failed_step.expected_mode != "land"
        ):
            return None
    else:
        return None
    last = error.failure.last_observation
    if (
        type(last) is not TraversalSnapshot
        or last.ready is not True
        or last.interruption is not None
        or type(last.map_id) is not int
        or last.map_id < 0
        or not isinstance(last.at, tuple)
        or len(last.at) != 2
        or any(type(value) is not int or value < 0 for value in last.at)
        or last.mode not in {"land", "water"}
    ):
        return None
    if failed_step is not None and (
        last.mode != "land"
        or last.map_id != failed_step.source_map
        or last.at != failed_step.source_at
    ):
        return None
    for facts in (before.facts, terminal.facts):
        if facts.get("party_guard_verified") is not True:
            return None
        bag = facts.get("bag_items")
        if not isinstance(bag, (list, tuple)) or any(
            not isinstance(item, (list, tuple))
            or len(item) != 2
            or any(type(value) is not int or value <= 0 for value in item)
            for item in bag
        ):
            return None
        if type(facts.get("coins")) is not int or not 0 <= facts["coins"] <= 9999:
            return None
        lesson = facts.get("player_lesson")
        if not isinstance(lesson, Mapping) or (
            lesson.get("schema") != "pokemon.red.player-lesson-snapshot.v1"
        ):
            return None
        party = lesson.get("party")
        if not isinstance(party, (list, tuple)) or not 1 <= len(party) <= 6:
            return None
        refs = [
            member.get("specimen_ref") if isinstance(member, Mapping) else None for member in party
        ]
        if any(not isinstance(ref, str) or not ref for ref in refs) or len(set(refs)) != len(refs):
            return None
    unchanged = (
        "owned_species",
        "specimen_counts",
        "completed_objectives",
        "player_lesson",
        "bag_items",
        "coins",
    )
    if any(before.facts[name] != terminal.facts[name] for name in unchanged):
        return None
    route = terminal.facts.get("route_boundary")
    expected = dict(
        map_id=last.map_id, at=list(last.at), ready=True, interruption=None, mode=last.mode
    )
    if not isinstance(route, Mapping) or (
        type(route.get("map_id")) is not int
        or not isinstance(route.get("at"), list)
        or any(type(value) is not int for value in route["at"])
        or route.get("ready") is not True
        or dict(route) != expected
    ):
        return None
    counters = observed_cost(before.facts, terminal.facts)
    if counters is None or (
        counters["actions"] <= 0
        or counters["frames"] <= 0
        or counters["completed_actions"] != counters["actions"]
        or counters["cash_spent"] != 0
    ):
        return None
    if any(
        type(value) is not int or value < 0
        for value in (error.failure.movement_requests, error.failure.wait_actions)
    ):
        return None
    return dict(
        reason=error.reason.value,
        route_terminal=expected,
        cost=counters,
        **(
            {
                "failed_walk": dict(
                    source_map=failed_step.source_map,
                    source_at=list(failed_step.source_at),
                    expected_map=failed_step.expected_map,
                    expected_at=list(failed_step.expected_at),
                    action=failed_step.action,
                )
            }
            if failed_step is not None
            else {}
        ),
        movement_requests=error.failure.movement_requests,
        wait_actions=error.failure.wait_actions,
    )


def spending_bound(binding):
    """Known maximum cash debit, not an estimated reward or policy mask."""
    if binding.kind is not GoalKind.ACQUIRE_SPECIES:
        return None
    source = binding.search_memory_source
    if source.startswith(PAID_SEARCH):
        return 500
    if source.startswith(NATIVE_EXCHANGE):
        return 0
    return None


def objective_key(facts):
    """Legacy fallback for bindings without observed source-specific targets."""
    owned = facts.get("owned_species")
    if (
        not isinstance(owned, (list, tuple))
        or not owned
        or any(not isinstance(species, str) for species in owned)
    ):
        raise ValueError("integrated play requires observed registration context")
    return canonical_sha256({"registered": sorted(owned)})


def search_objective_key(binding, fallback: str) -> str:
    """Adapter-private target context; never a policy feature or availability rule."""
    return binding.search_objective_sha256 or fallback


def menu_with_search_history(options, memory: GoalSearchMemory, objective: str):
    """Only measured semantic counts reach the existing feature-v4 ranker."""
    candidates = tuple(
        replace(
            candidate,
            search_history=memory.lookup(
                binding.search_memory_source, search_objective_key(binding, objective)
            ),
        )
        if binding.kind is GoalKind.ACQUIRE_SPECIES
        else candidate
        for candidate, binding in zip(options.menu.candidates, options.bindings, strict=True)
    )
    return replace(options, menu=replace(options.menu, candidates=candidates))


def observed_cost(before, after):
    """Retain counter deltas even without a completed executor report.

    These are diagnostic costs, never proof of a completed macro or permission
    to recover from an exception. Attempted and completed inputs stay separate.
    """
    names = ("actions", "completed_actions", "frames", "cash")
    if any(
        type(facts.get(n)) is not int or facts[n] < 0 for facts in (before, after) for n in names
    ):
        return None
    actions = after["actions"] - before["actions"]
    completed = after["completed_actions"] - before["completed_actions"]
    frames = after["frames"] - before["frames"]
    if (
        actions < 0
        or not 0 <= completed <= actions
        or frames < 0
        or any(f["completed_actions"] > f["actions"] for f in (before, after))
    ):
        return None
    return dict(
        actions=actions,
        completed_actions=completed,
        frames=frames,
        cash_spent=before["cash"] - after["cash"],
    )


def measured_cost(before, after, report):
    if not isinstance(report, GoalExecutionReport):
        return None
    names = ("actions", "completed_actions", "frames", "cash")
    if any(
        type(facts.get(name)) is not int or facts[name] < 0
        for facts in (before, after)
        for name in names
    ):
        return None
    actions = after["actions"] - before["actions"]
    frames = after["frames"] - before["frames"]
    if (
        actions <= 0
        or frames <= 0
        or actions != after["completed_actions"] - before["completed_actions"]
        or actions != report.actions_executed
        or frames != report.frames_executed
    ):
        return None
    return {"actions": actions, "frames": frames, "cash_spent": before["cash"] - after["cash"]}


def ordinary_paid_search_setback(binding, before, terminal, report, verification, error):
    """Fail closed unless the entire unsuccessful paid visit settled normally."""
    if (
        error is not None
        or verification is None
        or report is None
        or not terminal.safe
        or not before.safe
        or not binding.search_memory_source.startswith(PAID_SEARCH)
        or verification.status.value != "failed"
        or verification.failure_reason is None
        or verification.failure_reason.value != "search_exhausted"
    ):
        return False
    cost = measured_cost(before.facts, terminal.facts, report)
    if cost is None or cost["cash_spent"] != 500:
        return False
    evidence = report.evidence
    admission = evidence.get("admission")
    departure = evidence.get("paid_session_departure")
    if (
        not isinstance(admission, Mapping)
        or admission.get("status") != "ok"
        or admission.get("single_admission") is not True
        or not isinstance(departure, Mapping)
        or departure.get("passed") is not True
        or type(evidence.get("captures")) is not int
        or evidence["captures"] != 0
        or evidence.get("search_safety_stopped") is not False
        or not (
            evidence.get("search_exhausted") is True
            or evidence.get("search_resource_stopped") is True
        )
    ):
        return False
    unchanged = (
        "owned_species",
        "specimen_counts",
        "specimens",
        "party_training",
        "party_hp",
        "party_pp",
        "party_status",
        "bag_items",
    )
    if any(
        name not in before.facts
        or name not in terminal.facts
        or before.facts[name] != terminal.facts[name]
        for name in unchanged
    ):
        return False
    for facts in (before.facts, terminal.facts):
        session = facts.get("session")
        if (
            facts.get("battle_state") != 0
            or facts.get("input_ready") is not True
            or facts.get("buttons_released") is not True
            or not isinstance(session, Mapping)
            or session.get("in_safari_zone") is not False
            or session.get("safari_game_over") is not False
        ):
            return False
    return True


def _settled_league_funding_loss(binding, terminal, report):
    """Admit only a bound, measured native funding loss; never generic errors."""
    proof = report.evidence.get("native_league_funding_loss")
    if not isinstance(proof, dict):
        return False
    battle = proof.get("completion")
    before, after = proof.get("money_before_battle"), proof.get("ending_money")
    return (
        binding.binding_ref.startswith("pokemon.red:funding:repeatable-league:")
        and report.evidence.get("status") == "lost"
        and report.evidence.get("no_income_credit") is True
        and proof.get("schema") == "pokemon.red.league-funding-native-loss.v1"
        and proof.get("terminal_sha256") == terminal.sha256
        and type(before) is int and type(after) is int and before >= 0
        and after == before // 2 and after == terminal.facts.get("cash")
        and isinstance(battle, dict)
        and battle.get("schema") == "pokemon.red.learned-trainer-completion.v1"
        and battle.get("outcome") == "lost" and battle.get("field_ready") is True
        and battle.get("money_delta") == after - before
    )
