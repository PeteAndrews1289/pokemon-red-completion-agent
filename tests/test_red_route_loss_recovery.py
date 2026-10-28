"""A native route blackout returns a failed goal, never destination success."""

from copy import deepcopy
from dataclasses import replace

import pytest
from test_red_fresh_party_recovery import earned_trip, fresh_session
from test_red_live_option_menu import _binding

from pokemon_red_completion.goal_manager import GoalFailureReason, GoalKind
from pokemon_red_completion.goal_manager_runtime import GoalExecutionReport, GoalVerification
from pokemon_red_completion.red_integrated_play import ordinary_player_setback
from pokemon_red_completion.red_player_engaged_story import SETTLED_ROUTE_TRAINER_LOSS_SCHEMA
from pokemon_red_completion.red_player_engaged_story import SETTLED_ROUTE_TRAINER_RECOVERY_SCHEMA


def route_loss(monkeypatch, kind=GoalKind.ACQUIRE_SPECIES):
    session, state, permanent = fresh_session(monkeypatch)
    state.cash = 946
    before = session.snapshot()
    earned_trip(session, state)
    state.cash = 945  # Three route wins add945; native blackout halves1891.
    state.members = tuple(replace(m, hp=m.max_hp) for m in state.members)
    after = session.snapshot()
    report = GoalExecutionReport(401, 25548, dict(
        schema="pokemon.core.routed-semantic-goal-report.v1",
        destination_kind=kind.value, route_verified=False, destination_bound=False,
        destination_executed=False, budget_reconciled=True, within_budget=True,
        route_setback=dict(schema=SETTLED_ROUTE_TRAINER_LOSS_SCHEMA, verified=True,
            learned_combat=True, support="already_engaged_native_trainer",
            source_sha256="a" * 64, terminal_sha256=after.sha256,
            cash_before=1891, cash_after=945, cash_lost=946, actions=17, frames=400,
            objective_completed=False, reward=None, battle=dict(
                schema="pokemon.red.learned-trainer-completion.v1", outcome="lost",
                field_ready=True, money_delta=-946))))
    binding = _binding(kind, binding_ref="native:route-loss", calls=[])
    return permanent, before, after, report, binding


@pytest.mark.parametrize("kind", [GoalKind.ACQUIRE_SPECIES, GoalKind.RESUPPLY,
    GoalKind.RESTORE_TEAM, GoalKind.DEVELOP_TEAM, GoalKind.EVOLVE_SPECIES,
    GoalKind.ADVANCE_STORY])
def test_settled_route_loss_preserves_earned_evolution_and_returns_to_model(monkeypatch, kind):
    permanent, before, after, report, binding = route_loss(monkeypatch, kind)
    assert after.facts["cash"] != before.facts["cash"] // 2
    assert ordinary_player_setback(binding, before, after, report,
        GoalVerification.failed(GoalFailureReason.RESOURCE_LOST), None)
    assert report.evidence["destination_executed"] is False
    assert permanent.refs == ("starter",)


@pytest.mark.parametrize("fault", ["missing", "schema", "unverified", "terminal", "cash",
    "cash_lost", "money_delta", "won", "unsettled_battle", "counts", "route_success",
    "destination_bound", "destination_executed", "budget", "within_budget", "kind",
    "unready", "unsafe", "exception", "reason", "meter", "census", "identity",
    "xp_regression", "registration", "boolean_cash"])
def test_route_blackout_does_not_waive_proof_control_or_budget(monkeypatch, fault):
    _, before, after, report, binding = route_loss(monkeypatch)
    evidence, facts = deepcopy(dict(report.evidence)), deepcopy(dict(after.facts))
    loss, error, reason = evidence["route_setback"], None, GoalFailureReason.RESOURCE_LOST
    if fault == "missing":
        loss.pop("cash_before")
    elif fault == "schema":
        loss["schema"] = "unknown"
    elif fault == "unverified":
        loss["verified"] = False
    elif fault == "terminal":
        loss["terminal_sha256"] = "b" * 64
    elif fault == "cash":
        facts["cash"] = 944
    elif fault == "cash_lost":
        loss["cash_lost"] = 945
    elif fault == "money_delta":
        loss["battle"]["money_delta"] = -945
    elif fault == "won":
        loss["battle"]["outcome"] = "won"
    elif fault == "unsettled_battle":
        facts["battle_state"] = 2
    elif fault == "counts":
        loss["actions"] = 402
    elif fault == "route_success":
        evidence["route_verified"] = True
    elif fault in {"destination_bound", "destination_executed"}:
        evidence[fault] = True
    elif fault in {"budget", "within_budget"}:
        evidence["budget_reconciled" if fault == "budget" else fault] = False
    elif fault == "kind":
        evidence["destination_kind"] = GoalKind.RESUPPLY.value
    elif fault == "unready":
        facts["input_ready"] = False
    elif fault == "exception":
        error = RuntimeError("unknown route defect")
    elif fault == "reason":
        reason = GoalFailureReason.OUTCOME_NOT_VERIFIED
    elif fault == "meter":
        report = replace(report, actions_executed=400)
    elif fault == "census":
        facts["specimen_counts"]["pokemon:national:025"] = 1
    elif fault == "identity":
        facts["retained_party_continuation"]["individuals"].pop("caught-b")
    elif fault == "xp_regression":
        facts["retained_party_continuation"]["individuals"]["caught-a"]["experience"] = 315
    elif fault == "registration":
        facts["owned_species"] += ["pokemon:national:025"]
    elif fault == "boolean_cash":
        loss["cash_before"] = True
    after = replace(after, facts=facts, safe=fault != "unsafe")
    assert not ordinary_player_setback(binding, before, after, replace(report, evidence=evidence),
        GoalVerification.failed(reason), error)


@pytest.mark.parametrize('kind', [GoalKind.ACQUIRE_SPECIES, GoalKind.RESUPPLY,
    GoalKind.EVOLVE_SPECIES, GoalKind.DEVELOP_TEAM, GoalKind.ADVANCE_STORY])
@pytest.mark.parametrize('fault', [None, 'healthy', 'all_fainted', 'hp_mismatch',
    'terminal', 'payout', 'destination', 'budget', 'unknown_error', 'wrong_reason'])
def test_verified_route_win_with_faints_is_a_measured_recovery_setback(monkeypatch, kind, fault):
    _, before, after, report, binding = route_loss(monkeypatch, kind)
    evidence, facts = deepcopy(dict(report.evidence)), deepcopy(dict(after.facts))
    hp = [0, 25]
    if fault == 'healthy': hp = [30, 25]
    if fault == 'all_fainted': hp = [0, 0]
    facts.setdefault('diagnostics', {})['party_hp'] = [0, 20] if fault == 'hp_mismatch' else hp
    stop = evidence['route_setback']
    stop.update(schema=SETTLED_ROUTE_TRAINER_RECOVERY_SCHEMA,
                cash_before=935, cash_after=945, party_hp=hp,
                battle=dict(schema='pokemon.red.learned-trainer-completion.v1',
                            outcome='won', field_ready=True, money_delta=10))
    stop.pop('cash_lost')
    if fault == 'terminal': stop['terminal_sha256'] = 'b' * 64
    if fault == 'payout': stop['battle']['money_delta'] = 11
    if fault == 'destination': evidence['destination_executed'] = True
    if fault == 'budget': evidence['within_budget'] = False
    after = replace(after, facts=facts)
    reason = GoalFailureReason.RESOURCE_LOST if fault == 'wrong_reason' else GoalFailureReason.RECOVERY_REQUIRED
    error = RuntimeError('unknown') if fault == 'unknown_error' else None
    assert ordinary_player_setback(binding, before, after, replace(report, evidence=evidence),
        GoalVerification.failed(reason), error) is (fault is None)


@pytest.mark.parametrize('recovery', [False, True])
@pytest.mark.parametrize('depth', [1, 2, 8])
def test_nested_routed_destination_preserves_verified_stop(monkeypatch, recovery, depth):
    from test_routed_semantic_goal import _composer
    from pokemon_red_completion.routed_semantic_goal import RoutedSemanticGoalLimits

    _, before, after, report, binding = route_loss(monkeypatch)
    evidence = deepcopy(dict(report.evidence))
    reason = GoalFailureReason.RESOURCE_LOST
    if recovery:
        reason = GoalFailureReason.RECOVERY_REQUIRED
        facts = deepcopy(dict(after.facts))
        facts.setdefault('diagnostics', {})['party_hp'] = [0, 25]
        after = replace(after, facts=facts)
        stop = evidence['route_setback']
        stop.update(schema=SETTLED_ROUTE_TRAINER_RECOVERY_SCHEMA,
                    cash_before=935, cash_after=945, party_hp=[0, 25],
                    battle=dict(schema='pokemon.red.learned-trainer-completion.v1',
                                outcome='won', field_ready=True, money_delta=10))
        stop.pop('cash_lost')
    for index in range(depth):
        # The complete outer report still reconciles with the observed401inputs.
        child_actions = 401 - depth + index
        child_frames = 25548 - 100 * (depth - index)
        _, composed, _, events = _composer(
            offered_kind=binding.kind, destination_kind=binding.kind,
            route_spend=(1, 100), destination_spend=(child_actions, child_frames),
            limits=RoutedSemanticGoalLimits(1000, 50000),
            destination_evidence=evidence,
            destination_verification=GoalVerification.failed(reason))
        report = composed.execute()
        assert composed.verify(report) == GoalVerification.failed(reason)
        assert events[-1] == 'destination_verify'
        evidence = dict(report.evidence)
    assert report.actions_executed == 401 and report.frames_executed == 25548
    assert evidence['route_verified'] and evidence['destination_executed']
    chain = evidence['route_setback_destination_chain']
    assert len(chain) == depth and chain[-1]['destination_executed'] is False
    assert not any('private_route' in node or 'semantic_destination' in node for node in chain)
    assert ordinary_player_setback(binding, before, after, report,
                                  GoalVerification.failed(reason), None)


@pytest.mark.parametrize('fault', [
    'chain_type', 'node_type', 'depth', 'outer_route', 'outer_destination',
    'child_kind', 'child_schema', 'child_budget', 'child_within_budget',
    'child_executed', 'child_actions', 'child_frames', 'boolean_actions',
    'negative_frames', 'child_cost_under_stop', 'terminal', 'missing_chain',
])
def test_nested_stop_does_not_bypass_composition_or_native_proof(monkeypatch, fault):
    _, before, after, report, binding = route_loss(monkeypatch)
    evidence = deepcopy(dict(report.evidence))
    child = {key: value for key, value in evidence.items() if key != 'route_setback'}
    child.update(actions=400, frames=25448)
    evidence.update(route_verified=True, destination_bound=True, destination_executed=True,
                    route_setback_destination_chain=[child])
    if fault == 'chain_type': evidence['route_setback_destination_chain'] = {}
    elif fault == 'node_type': evidence['route_setback_destination_chain'] = [None]
    elif fault == 'depth': evidence['route_setback_destination_chain'] *= 9
    elif fault == 'outer_route': evidence['route_verified'] = False
    elif fault == 'outer_destination': evidence['destination_bound'] = False
    elif fault == 'child_kind': child['destination_kind'] = GoalKind.RESUPPLY.value
    elif fault == 'child_schema': child['schema'] = 'unknown'
    elif fault == 'child_budget': child['budget_reconciled'] = False
    elif fault == 'child_within_budget': child['within_budget'] = False
    elif fault == 'child_executed': child['destination_executed'] = True
    elif fault == 'child_actions': child['actions'] = 402
    elif fault == 'child_frames': child['frames'] = 25549
    elif fault == 'boolean_actions': child['actions'] = True
    elif fault == 'negative_frames': child['frames'] = -1
    elif fault == 'child_cost_under_stop': child['actions'] = 16
    elif fault == 'terminal': evidence['route_setback']['terminal_sha256'] = 'c' * 64
    elif fault == 'missing_chain': evidence.pop('route_setback_destination_chain')
    assert not ordinary_player_setback(binding, before, after,
        replace(report, evidence=evidence), GoalVerification.failed(GoalFailureReason.RESOURCE_LOST), None)
