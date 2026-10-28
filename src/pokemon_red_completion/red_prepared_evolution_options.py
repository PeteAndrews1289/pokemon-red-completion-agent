"""Model-selected compositions of existing machine and evolution executors.

The selected recipient/machine/replacement and existing evolution are fixed
before input. Re-enumeration refreshes that exact executor after the lesson;
it cannot choose a substitute goal or an ambiguous physical precursor.
"""

from collections import Counter, defaultdict
from dataclasses import asdict, replace
from hashlib import sha256

from .goal_manager import GoalFailureReason, GoalKind
from .goal_manager_runtime import ExecutableGoalBinding, GoalExecutionReport, GoalVerification
from .living_dex_option_value import LivingDexOptionKind
from .provenance import canonical_sha256
from .red_collection import red_internal_species_number
from .red_live_option_menu import supplemental_live_option
from .red_player_field_goals import _field_ready
from .red_player_party_loan import _stock


class PreparedEvolutionError(RuntimeError):
    """A declared component failed; no other goal is substituted."""


def prepared_stock_progress(before, after):
    """Retain individual multiplicity and every observed individual's XP."""
    old = Counter(ref for ref, _, _, _ in before.elements())
    new = Counter(ref for ref, _, _, _ in after.elements())
    identities = bool(old) and old == new
    old_xp, new_xp = defaultdict(list), defaultdict(list)
    for ref, _, _, xp in before.elements():
        old_xp[ref].append(xp)
    for ref, _, _, xp in after.elements():
        new_xp[ref].append(xp)
    xp = identities and all(
        all(new >= old for old, new in zip(sorted(values), sorted(new_xp[ref]), strict=True))
        for ref, values in old_xp.items())
    return dict(identities_preserved=identities, earned_xp_retained=bool(xp))


def prepared_evolution_options(runtime, actions, observation, *, machine_choices,
                               evolution_options, enumerate_collection, admits):
    """Add only recipes whose unique recipient and evolution already exist."""
    if not callable(enumerate_collection) or not callable(admits):
        raise TypeError("prepared evolution needs the existing admitted collection observer")
    guard = runtime.adapter.party_guard
    if not machine_choices or not _field_ready(runtime):
        return ()
    source = runtime.emulator.save_state_bytes()
    counters = actions.actions_executed, runtime.emulator.frame_count
    stock = _stock(runtime)
    result = []
    for machine in machine_choices:
        bundle = machine.bundle
        species = bundle.lesson.species_id
        sources = [row for row in stock.elements() if row[1] == species]
        # The existing executor selects by observed species. A unique physical
        # source proves that its selection is the recipe's prepared individual.
        if len(sources) != 1 or sources[0][0] != bundle.target_ref:
            continue
        for old, target, _ in sorted(guard.edges):
            if old != species:
                continue
            source_number, target_number = map(red_internal_species_number, (old, target))
            evolution_ref = (f"pokemon.red:evolution:national-{source_number:03d}"
                             f"-to-national-{target_number:03d}")
            rows = [row for row in evolution_options
                    if row.binding.kind is GoalKind.EVOLVE_SPECIES
                    and row.candidate.features.kind is LivingDexOptionKind.EVOLVE
                    and row.binding.binding_ref == evolution_ref and admits(row.binding)]
            if len(rows) != 1:
                continue
            ordinary = rows[0]
            binding = _prepared_binding(runtime, actions, machine, ordinary,
                enumerate_collection, admits, source, stock)
            a, b = ordinary.candidate.features, machine.option.candidate.features
            features = replace(a,
                dependency_unlock_gain=max(a.dependency_unlock_gain, b.dependency_unlock_gain),
                travel_effort=min(1., a.travel_effort + b.travel_effort),
                execution_effort=min(1., a.execution_effort + b.execution_effort),
                resource_cost=min(1., a.resource_cost + b.resource_cost),
                storage_cost=min(1., a.storage_cost + b.storage_cost),
                party_risk=max(a.party_risk, b.party_risk),
                irreversibility_risk=min(1., a.irreversibility_risk + b.irreversibility_risk),
                uncertainty=max(a.uncertainty, b.uncertainty))
            candidate = replace(ordinary.candidate, binding_ref=binding.binding_ref,
                                features=features)
            result.append(supplemental_live_option(binding, candidate))
    if (runtime.emulator.save_state_bytes() != source
            or (actions.actions_executed, runtime.emulator.frame_count) != counters):
        raise ValueError("prepared evolution discovery changed native state")
    if len({row.binding.binding_ref for row in result}) != len(result):
        raise ValueError("prepared evolution repeats a recipe")
    return tuple(result)


def _prepared_binding(runtime, actions, machine, ordinary, enumerate_collection,
                      admits, source, before_stock):
    guard = runtime.adapter.party_guard
    declared_ref = ordinary.binding.binding_ref
    identity = canonical_sha256(dict(machine=asdict(machine.bundle), evolution=declared_ref))
    binding_ref = "pokemon.red:prepared-evolution:" + sha256(source).hexdigest() + ":" + identity
    claimed, terminal, receipt, child, child_report, child_verdict = False, None, None, None, None, None
    cash_bounds = machine.option.binding.maximum_cash_debit, ordinary.binding.maximum_cash_debit
    cash_bound = None if None in cash_bounds else sum(cash_bounds)

    def safe_progress():
        guard.verify_active_roster_restored()
        progress = prepared_stock_progress(before_stock, _stock(runtime))
        return all(progress.values()) and _field_ready(runtime)

    def execute():
        nonlocal claimed, terminal, receipt, child, child_report, child_verdict
        if claimed or runtime.emulator.save_state_bytes() != source or not _field_ready(runtime):
            raise ValueError("prepared evolution is stale or consumed")
        guard.verify_active_roster_restored()
        if not admits(ordinary.binding):
            raise PreparedEvolutionError("declared evolution is excluded")
        claimed = True
        start_actions, start_frames = actions.actions_executed, runtime.emulator.frame_count
        lesson_report = machine.option.binding.execute()
        if machine.option.binding.verify(lesson_report).status.value != "succeeded":
            raise PreparedEvolutionError("selected machine lesson was not verified")
        guard.verify_active_roster_restored()
        if _stock(runtime) != before_stock or not _field_ready(runtime):
            raise PreparedEvolutionError("selected lesson changed source stock or readiness")
        observed = (runtime.emulator.save_state_bytes(), actions.actions_executed,
                    runtime.emulator.frame_count)
        rows = enumerate_collection(runtime, actions, runtime.adapter.observe())
        if observed != (runtime.emulator.save_state_bytes(), actions.actions_executed,
                        runtime.emulator.frame_count):
            raise PreparedEvolutionError("collection refresh changed native state")
        matches = [row.binding for row in rows
                   if row.binding.kind is GoalKind.EVOLVE_SPECIES
                   and row.binding.binding_ref == declared_ref and admits(row.binding)]
        if len(matches) != 1:
            raise PreparedEvolutionError("declared evolution is unavailable or ambiguous after lesson")
        child = matches[0]
        if (ordinary.binding.maximum_cash_debit is not None
                and (child.maximum_cash_debit is None
                     or child.maximum_cash_debit > ordinary.binding.maximum_cash_debit)):
            raise PreparedEvolutionError("refreshed evolution exceeds its declared cash exposure")
        if child.resource_quote != ordinary.binding.resource_quote:
            raise PreparedEvolutionError("refreshed evolution changed its declared resource quote")
        child_report = child.execute()
        # Verify before composing the receipt; a failed bounded partial retains
        # its original verdict and evidence instead of becoming a success.
        child_verdict = child.verify(child_report)
        if not safe_progress():
            raise PreparedEvolutionError("prepared evolution lost retained stock or field custody")
        terminal = runtime.emulator.save_state_bytes()
        evidence = dict(child_report.evidence)
        evidence["prepared_evolution"] = dict(
            selected_bundle_authority="model_or_disclosed_diagnostic",
            machine_lesson=dict(lesson_report.evidence),
            declared_evolution_binding_ref=declared_ref,
            exact_selected_evolution_refreshed=True,
            original_stock_and_xp_retained=True,
            implicit_replacement_goal=False)
        receipt = GoalExecutionReport(actions.actions_executed - start_actions,
            runtime.emulator.frame_count - start_frames, evidence)
        return receipt

    def verify(report):
        if (receipt is None or report is not receipt
                or terminal != runtime.emulator.save_state_bytes() or not safe_progress()):
            return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        return child_verdict

    return ExecutableGoalBinding(binding_ref, GoalKind.EVOLVE_SPECIES,
        min(1., ordinary.binding.estimated_effort
            + machine.option.binding.estimated_effort),
        min(1., ordinary.binding.estimated_risk
            + machine.option.binding.estimated_risk),
        execute, verify, maximum_cash_debit=cash_bound,
        resource_quote=ordinary.binding.resource_quote)
