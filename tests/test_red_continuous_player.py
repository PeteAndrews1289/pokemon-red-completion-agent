"""Continuous orchestration checks, not native qualification or model learning."""

import json
from dataclasses import replace
from types import SimpleNamespace as N

import pytest
from test_post_battle_strategy import menu
from test_red_integrated_play import _facts
from test_red_live_option_menu import _binding, _model, _situation

import pokemon_red_completion.red_autonomous_player as runner
from pokemon_red_completion.goal_manager import GoalFailureReason, GoalKind
from pokemon_red_completion.goal_manager_runtime import (
    GoalBindingSet,
    GoalExecutionReport,
    GoalVerification,
)
from pokemon_red_completion.living_dex_option_value import upgrade_option_value_model_for_readiness
from pokemon_red_completion.player_readiness import PlayerReadiness
from pokemon_red_completion.red_autonomous_player import AutonomousSnapshot
from pokemon_red_completion.red_integrated_play import ordinary_player_setback
from pokemon_red_completion.red_live_option_menu import (
    RedLiveOptionChoice,
    RedLiveOptionSelectionMode,
    build_red_live_option_set,
)
from pokemon_red_completion.resource_economy_observation import EconomySnapshot


def facts(n=0):
    return {**_facts(n), "completed_objectives": ["first"], "cash": 5000 - 20 * n}


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "error",
        "reason",
        "captures",
        "sighting",
        "unready",
        "battle",
        "partial",
        "story_lost",
        "stock_lost",
    ],
)
def test_continuous_discovery_miss_replans_only_with_measured_settled_evidence(fault):
    before = runner.AutonomousSnapshot(b"0", facts(), True)
    after = runner.AutonomousSnapshot(b"1", facts(1), True)
    evidence = dict(
        bounded=True,
        search_exhausted=True,
        captures=0,
        new_sighting_count=0,
        search_stop_reason="survey_leg_limit_exceeded",
    )
    if fault in {"reason", "captures", "sighting"}:
        key = {
            "reason": "search_stop_reason",
            "captures": "captures",
            "sighting": "new_sighting_count",
        }[fault]
        evidence[key] = "unknown" if fault == "reason" else 1
    if fault in {"unready", "battle", "partial", "story_lost", "stock_lost"}:
        key, value = {
            "unready": ("input_ready", False),
            "battle": ("battle_state", 1),
            "partial": ("completed_actions", 0),
            "story_lost": ("completed_objectives", []),
            "stock_lost": ("specimen_counts", {}),
        }[fault]
        after = replace(after, facts={**after.facts, key: value})
    assert ordinary_player_setback(
        _binding(GoalKind.EXPLORE, binding_ref="discovery", calls=[]),
        before,
        after,
        GoalExecutionReport(1, 10, evidence),
        GoalVerification.failed(GoalFailureReason.SEARCH_EXHAUSTED),
        RuntimeError("controller") if fault == "error" else None,
    ) is (fault is None)


def test_continuous_search_history_reaches_policy_and_survives_resume(tmp_path):
    from test_red_integrated_play import _options, _report

    from pokemon_red_completion.goal_search_memory import GoalSearchMemory
    from pokemon_red_completion.red_integrated_play import objective_key

    state = {"n": 0}
    prior = menu()
    readiness = PlayerReadiness.from_context(prior.context, prior.remaining_budget)
    memory = GoalSearchMemory()

    def execute():
        state["n"] += 1
        return _report()

    def observe(_ordinal):
        options = _options(
            execute, lambda _: GoalVerification.failed(GoalFailureReason.SEARCH_EXHAUSTED)
        )
        return replace(
            options,
            menu=replace(
                options.menu,
                candidates=tuple(
                    replace(candidate, readiness=readiness) for candidate in options.menu.candidates
                ),
            ),
        )

    def run(name, decisions, retained):
        return runner.run_autonomous_options(
            model=upgrade_option_value_model_for_readiness(_model()),
            output=tmp_path / name,
            snapshot=lambda: runner.AutonomousSnapshot(
                str(state["n"]).encode(), facts(state["n"]), True
            ),
            observe=observe,
            seed=17,
            maximum_decisions=decisions,
            continuous_player=True,
            maximum_cash_spent=None,
            initial_search_memory=retained,
            provenance={"test_only": True},
        )

    first = run("first", 2, memory)
    assert first["executed_decisions"] == first["ordinary_setbacks"] == 2
    assert first["accounted_cash_spent"] == 40
    for ordinal in range(2):
        intent = json.loads((tmp_path / f"first/step-{ordinal:03d}/intent.json").read_text())
        histories = [c["search_history"] for c in intent["menu"]["menu"]["candidates"]]
        assert all(h["attempts"] == h["exhausted"] == ordinal for h in histories)
    restored = GoalSearchMemory.from_private_dict(first["search_memory"])
    second = run("second", 1, restored)
    intent = json.loads((tmp_path / "second/step-000/intent.json").read_text())
    assert all(c["search_history"]["attempts"] == 2 for c in intent["menu"]["menu"]["candidates"])
    source = observe(0).bindings[0].search_memory_source
    history = restored.lookup(source, objective_key(facts()))
    assert (history.attempts, history.exhausted, history.actions, history.frames) == (3, 3, 3, 30)
    assert second["search_memory"] == restored.private_dict()


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "ref",
        "support",
        "source",
        "terminal",
        "progress",
        "reward",
        "battle",
        "ready",
        "cash",
        "delta",
        "unknown",
        "error",
        "partial",
    ],
)
def test_only_exact_retained_trainer_blackout_continues_failed_control_recovery(fault):
    before = runner.AutonomousSnapshot(b"0", facts(), True)
    after = runner.AutonomousSnapshot(b"1", {**facts(1), "cash": 2500}, True)
    evidence = dict(
        support="already_engaged_native_trainer",
        source_sha256=before.sha256,
        terminal_sha256=after.sha256,
        objective_completed=False,
        reward=None,
        battle=dict(
            schema="pokemon.red.learned-trainer-completion.v1",
            outcome="lost",
            field_ready=True,
            money_delta=-2500,
        ),
    )
    changes = {
        "support": ("support", "unknown"),
        "source": ("source_sha256", "unknown"),
        "terminal": ("terminal_sha256", "unknown"),
        "progress": ("objective_completed", True),
        "reward": ("reward", {}),
    }
    if fault in changes:
        key, value = changes[fault]
        evidence[key] = value
    if fault == "battle":
        evidence["battle"]["outcome"] = "unresolved"
    if fault == "ready":
        evidence["battle"]["field_ready"] = False
    if fault == "delta":
        evidence["battle"]["money_delta"] = 0
    if fault == "cash":
        after = replace(after, facts={**after.facts, "cash": 2499})
    if fault == "partial":
        after = replace(after, facts={**after.facts, "completed_actions": 0})
    binding = _binding(
        GoalKind.RECOVER_CONTROL,
        calls=[],
        binding_ref="unknown"
        if fault == "ref"
        else "pokemon.red:retained-engagement:" + before.sha256,
    )
    report = GoalExecutionReport(1, 10, evidence)
    verdict = GoalVerification.failed(
        GoalFailureReason.OUTCOME_NOT_VERIFIED
        if fault == "unknown"
        else GoalFailureReason.RESOURCE_LOST
    )
    assert ordinary_player_setback(
        binding,
        before,
        after,
        report,
        verdict,
        RuntimeError("failed input") if fault == "error" else None,
    ) is (fault is None)


@pytest.mark.parametrize("kind", [GoalKind.ADVANCE_STORY, GoalKind.DEVELOP_TEAM])
def test_fainting_is_recoverable_but_unknown_failures_and_missing_evidence_are_not(kind):
    binding = _binding(kind, binding_ref="story", calls=[])
    before = runner.AutonomousSnapshot(b"0", facts(), True)
    after = runner.AutonomousSnapshot(b"1", {**facts(1), "party_hp": [0]}, True)
    report = GoalExecutionReport(1, 10, {})
    verdict = GoalVerification.failed(GoalFailureReason.RESOURCE_LOST)

    def accepted(terminal=after, verification=verdict, error=None):
        return ordinary_player_setback(binding, before, terminal, report, verification, error)

    assert accepted()
    for reason in (
        GoalFailureReason.OUTCOME_NOT_VERIFIED,
        GoalFailureReason.WORLD_STATE_DIVERGED,
        GoalFailureReason.EXECUTION_BUDGET_EXHAUSTED,
    ):
        assert not accepted(verification=GoalVerification.failed(reason))
    assert not accepted(error=RuntimeError("partial input"))
    for key, value in {
        "completed_actions": 0,
        "frames": 11,
        "completed_objectives": [],
        "owned_species": [],
        "specimen_counts": {},
        "battle_state": 1,
        "buttons_released": False,
        "input_ready": False,
    }.items():
        assert not accepted(replace(after, facts={**after.facts, key: value})), key


@pytest.mark.parametrize("kind", [GoalKind.DEVELOP_TEAM, GoalKind.ACQUIRE_SPECIES])
@pytest.mark.parametrize(
    "fault",
    [
        None,
        "absent",
        "identity",
        "guard",
        "census",
        "xp",
        "level",
        "unearned",
        "box",
        "story",
        "unknown",
    ],
)
def test_failed_development_may_rejoin_after_guard_verified_earned_evolution(fault, kind):
    import copy

    def evidence(species, level, xp):
        return dict(
            schema="pokemon.red.retained-party-continuation.v1",
            guard_sha256="a" * 64,
            native_identity_verified=True,
            individuals={"individual": dict(species_ref=species, level=level, experience=xp)},
            other_specimen_counts={},
        )

    a, b = evidence("old", 17, 3000), evidence("new", 18, 4000)
    if fault == "identity":
        b["individuals"] = {"substitute": b["individuals"]["individual"]}
    if fault == "guard":
        b["guard_sha256"] = "b" * 64
    if fault == "census":
        b["individuals"]["individual"]["species_ref"] = "other"
    if fault == "xp":
        b["individuals"]["individual"]["experience"] = 2999
    if fault == "level":
        b["individuals"]["individual"]["level"] = 16
    if fault == "unearned":
        b["individuals"]["individual"].update(level=17, experience=3000)
    if fault == "box":
        b["other_specimen_counts"] = {"box": 1}
    before = runner.AutonomousSnapshot(
        b"0",
        {
            **facts(),
            "owned_species": ["old"],
            "specimen_counts": {"old": 1},
            "retained_party_continuation": copy.deepcopy(a),
        },
        True,
    )
    after = runner.AutonomousSnapshot(
        b"1",
        {
            **facts(1),
            "owned_species": ["old", "new"],
            "specimen_counts": {"new": 1},
            **({} if fault == "absent" else {"retained_party_continuation": b}),
        },
        True,
    )
    kind = GoalKind.ADVANCE_STORY if fault == "story" else kind
    binding = _binding(kind, binding_ref="preparation", calls=[])
    report = GoalExecutionReport(1, 10, _capture_trip_receipt())
    verdict = GoalVerification.failed(
        GoalFailureReason.OUTCOME_NOT_VERIFIED
        if fault == "unknown"
        else GoalFailureReason.RESOURCE_LOST
    )
    assert ordinary_player_setback(binding, before, after, report, verdict, None) is (fault is None)


def _capture_trip_receipt():
    return dict(
        schema="pokemon.core.routed-semantic-goal-report.v1",
        budget_reconciled=True,
        destination_bound=True,
        destination_executed=True,
        route_verified=True,
        within_budget=True,
        destination_kind="acquire_species",
        capture_survey=dict(
            captures=0,
            encounters_seen=0,
            flees=0,
            semantic_actions=0,
            safety_stopped=True,
            search_exhausted=False,
        ),
    )


@pytest.mark.parametrize(
    "field",
    [
        "schema",
        "budget_reconciled",
        "destination_bound",
        "destination_executed",
        "route_verified",
        "within_budget",
        "destination_kind",
        "capture_survey",
        "captures",
        "encounters_seen",
        "semantic_actions",
        "flees",
        "safety_stopped",
        "search_exhausted",
        "counter_bool",
        "diagnostics_only",
    ],
)
def test_evolved_capture_trip_requires_exact_settled_health_stop_receipt(field):
    proof = dict(
        schema="pokemon.red.retained-party-continuation.v1",
        guard_sha256="a" * 64,
        native_identity_verified=True,
        other_specimen_counts={},
    )
    before = runner.AutonomousSnapshot(
        b"0",
        {
            **facts(),
            "owned_species": ["old"],
            "specimen_counts": {"old": 1},
            "retained_party_continuation": {
                **proof,
                "individuals": {"same": dict(species_ref="old", level=19, experience=7000)},
            },
        },
        True,
    )
    after = runner.AutonomousSnapshot(
        b"1",
        {
            **facts(1),
            "owned_species": ["old", "new"],
            "specimen_counts": {"new": 1},
            "retained_party_continuation": {
                **proof,
                "individuals": {"same": dict(species_ref="new", level=20, experience=8000)},
            },
        },
        True,
    )
    receipt = _capture_trip_receipt()
    if field in receipt:
        receipt.pop(field)
    elif field == "diagnostics_only":
        receipt = dict(capture_diagnostics=dict(diagnostic_only=True, safety_stopped=True))
    elif field == "counter_bool":
        receipt["capture_survey"]["captures"] = False
    else:
        receipt["capture_survey"].pop(field)
    binding = _binding(GoalKind.ACQUIRE_SPECIES, binding_ref="capture", calls=[])
    verdict = GoalVerification.failed(GoalFailureReason.RESOURCE_LOST)
    assert not ordinary_player_setback(
        binding, before, after, GoalExecutionReport(1, 10, receipt), verdict, None
    )


@pytest.mark.parametrize(
    "fault", [None, "missing", "cash", "learned", "nurse", "success", "error", "partial"]
)
def test_only_verified_paid_blackout_can_continue_a_failed_restoration(fault):
    binding = _binding(GoalKind.RESTORE_TEAM, binding_ref="restore", calls=[])
    before = runner.AutonomousSnapshot(b"0", facts(), True)
    terminal = runner.AutonomousSnapshot(b"1", {**facts(1), "cash": 2500}, True)
    proof = dict(
        blackout_verified=True,
        learned_recovery=False,
        nurse_interaction=False,
        cash_before=5000,
        cash_after=2500,
        cash_lost=2500,
    )
    if fault == "cash":
        proof["cash_lost"] = 2499
    if fault == "learned":
        proof["learned_recovery"] = True
    if fault == "nurse":
        proof["nurse_interaction"] = True
    report = GoalExecutionReport(
        1, 10, {} if fault == "missing" else dict(native_blackout_during_selected_restoration=proof)
    )
    verdict = (
        GoalVerification.succeeded()
        if fault == "success"
        else GoalVerification.failed(GoalFailureReason.RESOURCE_LOST)
    )
    if fault == "partial":
        terminal = replace(terminal, facts={**terminal.facts, "completed_actions": 0})
    assert ordinary_player_setback(
        binding,
        before,
        terminal,
        report,
        verdict,
        RuntimeError("partial") if fault == "error" else None,
    ) is (fault is None)


@pytest.mark.parametrize("fault", [None, "unverified", "partial", "verdict", "budget"])
@pytest.mark.parametrize(
    "selected_kind,reason",
    [
        (GoalKind.ADVANCE_STORY, GoalFailureReason.RESOURCE_LOST),
        (GoalKind.DEVELOP_TEAM, GoalFailureReason.RECOVERY_REQUIRED),
    ],
)
def test_setback_then_safety_recovery_then_fresh_choice(
    tmp_path, monkeypatch, fault, selected_kind, reason
):
    state, observed = {"n": 0}, []
    output = tmp_path / "run"
    prior = menu()
    readiness = PlayerReadiness.from_context(prior.context, prior.remaining_budget)

    def snapshot():
        n = state["n"]
        doc = facts(n)
        if n == 1:
            doc["party_hp"] = [0 if reason is GoalFailureReason.RESOURCE_LOST else 5]
        if fault == "partial" and n == 1:
            doc["completed_actions"] = 0
        return runner.AutonomousSnapshot(str(n).encode(), doc, True)

    def observe(ordinal):
        observed.append(state["n"])

        def execute():
            assert (output / f"step-{ordinal:03d}" / "decision.json").is_file()
            state["n"] += 1
            return GoalExecutionReport(1, 10, {})

        def verify(report):
            if fault == "verdict":
                return object()
            if ordinal == 0:
                return GoalVerification.failed(
                    GoalFailureReason.OUTCOME_NOT_VERIFIED if fault == "unverified" else reason,
                )
            return GoalVerification.succeeded()

        kinds = (
            (GoalKind.RESTORE_TEAM, GoalKind.RESUPPLY)
            if ordinal == 1
            else (GoalKind.ADVANCE_STORY, GoalKind.DEVELOP_TEAM)
        )
        bindings = tuple(
            replace(
                _binding(kind, binding_ref=kind.value, calls=[]),
                execute=execute,
                verify=verify,
            )
            for kind in kinds
        )
        return build_red_live_option_set(
            supplements=(),
            situation=_situation(resources=0.1, safety=0.9 if ordinal == 1 else 0.1),
            binding_set=GoalBindingSet(tuple(b.opportunity for b in bindings), bindings),
            model_feature_version=5,
            ordering_seed_sha256="a" * 64,
            readiness=readiness,
            economy_snapshot=EconomySnapshot(facts(ordinal)["cash"], ()),
            target_cash=5000,
        )

    real_select = runner.select_red_live_option

    def select(model, options, *, seed, **kwargs):
        if state["n"] == 1:
            return real_select(model, options, seed=seed, **kwargs)
        index = next(i for i, b in enumerate(options.bindings) if b.kind is selected_kind)
        return RedLiveOptionChoice(
            options,
            index,
            RedLiveOptionSelectionMode.MODEL_EXPLORATION,
            (0.0, 0.0),
            (0.5, 0.5),
            seed,
            model.model_sha256,
        )

    monkeypatch.setattr(runner, "select_red_live_option", select)
    result = runner.run_autonomous_options(
        model=upgrade_option_value_model_for_readiness(_model()),
        output=output,
        snapshot=snapshot,
        observe=observe,
        seed=17,
        maximum_decisions=3,
        continuous_player=True,
        maximum_cash_spent=4999 if fault == "budget" else 10000,
        provenance={"test_only": True},
    )
    if fault == "budget":
        assert result["executed_decisions"] == 0 and state["n"] == 0
        assert result["stop_reason"] == "continuous_spending_boundary"
    elif fault:
        assert observed == [0] and result["executed_decisions"] == 1
        assert (output / "step-000/terminal.state").read_bytes() == b"1"
    else:
        assert observed == [0, 1, 2]
        assert result["ordinary_setbacks"] == 1
        assert result["successful_decisions"] == 2
        assert result["model_decisions"] == 2 and result["support_decisions"] == 1
        assert result["accounted_cash_spent"] == 60
        recovery = json.loads((output / "step-001/outcome.json").read_text())
        assert recovery["support_role"] == "deterministic_player_safety"
        assert not recovery["learning_eligible"]
        assert result["outcomes"][0]["verification"] == "failed"


@pytest.mark.parametrize(
    "mode",
    [
        "certified",
        "unknown",
        "overspend",
        "broken_certificate",
        "ordinary",
        "ordinary_debit",
        "ordinary_broken_certificate",
    ],
)
def test_earned_money_healing_uses_exposure_not_wallet(tmp_path, monkeypatch, mode):
    state = {"n": 0}
    readiness = PlayerReadiness.from_context(menu().context, menu().remaining_budget)
    debit = mode in {"broken_certificate", "ordinary_debit", "ordinary_broken_certificate"}
    wallets = [427, 507, 506 if debit else 507]
    observed = []

    def snapshot():
        n = state["n"]
        return runner.AutonomousSnapshot(str(n).encode(), {**facts(n), "cash": wallets[n]}, True)

    def observe(ordinal):
        def execute():
            state["n"] += 1
            return GoalExecutionReport(1, 10, {})

        bindings = tuple(
            replace(
                _binding(kind, binding_ref=kind.value, calls=[]),
                execute=execute,
                verify=lambda _: GoalVerification.succeeded(),
                maximum_cash_debit=(
                    None
                    if mode in {"unknown", "ordinary", "ordinary_debit"}
                    else 428
                    if mode == "overspend"
                    else 0
                )
                if ordinal == 1
                else 214,
            )
            for kind in (
                (GoalKind.RESTORE_TEAM, GoalKind.RESUPPLY)
                if ordinal
                else (GoalKind.ADVANCE_STORY, GoalKind.DEVELOP_TEAM)
            )
        )
        options = build_red_live_option_set(
            supplements=(),
            situation=_situation(resources=0.1, safety=0.1),
            binding_set=GoalBindingSet(tuple(b.opportunity for b in bindings), bindings),
            model_feature_version=5,
            ordering_seed_sha256="a" * 64,
            readiness=readiness,
            economy_snapshot=EconomySnapshot(wallets[ordinal], ()),
            target_cash=0,
        )
        observed.append(options)
        return options

    def select(model, options, *, seed, **kwargs):
        # Fixture-controlled decisions only; production selection is unchanged.
        kind = GoalKind.RESTORE_TEAM if state["n"] else GoalKind.ADVANCE_STORY
        i = next(i for i, b in enumerate(options.bindings) if b.kind is kind)
        return RedLiveOptionChoice(
            options,
            i,
            RedLiveOptionSelectionMode.MODEL_EXPLORATION,
            (0.0, 0.0),
            (0.5, 0.5),
            seed,
            model.model_sha256,
        )

    monkeypatch.setattr(runner, "select_red_live_option", select)
    result = runner.run_autonomous_options(
        model=upgrade_option_value_model_for_readiness(_model()),
        output=tmp_path / "run",
        snapshot=snapshot,
        observe=observe,
        seed=17,
        maximum_decisions=2,
        continuous_player=True,
        maximum_cash_spent=None if mode.startswith("ordinary") else 427,
        provenance={"test_only": True},
    )
    if mode in {"unknown", "overspend"}:
        assert result["executed_decisions"] == 1
        assert result["stop_reason"] == "continuous_spending_boundary"
    else:
        assert result["executed_decisions"] == 2
        assert result["accounted_cash_spent"] == int(debit)
        assert result["stop_reason"] == (
            "cash_exposure_exceeded"
            if mode in {"broken_certificate", "ordinary_broken_certificate"}
            else "decision_budget"
        )
    admission = json.loads((tmp_path / "run/step-001/cash-admission.json").read_text())
    assert admission["cash"] == 507 and admission["prior_debits"] == 0
    assert admission["ordinary_game_economy"] == mode.startswith("ordinary")


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "exception",
        "unsettled",
        "census",
        "registration",
        "missing_return",
        "unmeasured",
        "not_partial",
        "no_reserve",
        "no_battles",
    ],
)
@pytest.mark.parametrize("composed", [False, True])
@pytest.mark.parametrize("report_form", ["routed", "native"])
@pytest.mark.parametrize("stop", ["reserve", "wall", "quantum"])
def test_returned_partial_evolution_dose_requeries_model_without_claiming_success(
    fault, report_form, stop, composed
):
    before_facts = dict(
        actions=0,
        completed_actions=0,
        frames=0,
        cash=10,
        owned_species=["one"],
        completed_objectives=["story"],
        specimen_counts={"one": 1},
        battle_state=0,
        input_ready=True,
        buttons_released=True,
    )
    after_facts = dict(before_facts, actions=2, completed_actions=2, frames=20)
    evidence = dict(
        schema="pokemon.core.routed-semantic-goal-report.v1",
        destination_kind="evolve_species",
        evolution_partial=True,
        budget_reconciled=True,
        destination_bound=True,
        destination_executed=True,
        route_verified=True,
        within_budget=True,
        retained_active_roster_restored=True,
        settlement_reserve_reached=True,
        completed_training_battles=3,
    )
    if report_form == "native":
        evidence = dict(
            schema="pokemon.red.native-evolution-partial.v1",
            bounded=True,
            source_species_ref="pokemon:national:010",
            target_species_ref="pokemon:national:011",
            evolution_partial=True,
            retained_active_roster_restored=True,
            settlement_reserve_reached=True,
            completed_training_battles=3,
        )
    if stop != "reserve":
        evidence["settlement_reserve_reached"] = False
        evidence["wall_limit_reached"] = stop == "wall"
    if stop == "quantum":
        evidence.update(
            quantum_limit_reached=True,
            completed_training_quanta=3,
            maximum_training_quanta=3,
        )
    if fault == "unsettled":
        after_facts["input_ready"] = False
    elif fault == "census":
        after_facts["specimen_counts"] = {"other": 1}
    elif fault == "registration":
        after_facts["owned_species"] = []
    elif fault == "missing_return":
        evidence["retained_active_roster_restored"] = False
    elif fault == "not_partial":
        evidence["evolution_partial"] = False
    elif fault == "no_reserve":
        evidence["settlement_reserve_reached"] = False
        evidence["wall_limit_reached"] = False
        evidence["quantum_limit_reached"] = False
    elif fault == "no_battles":
        evidence["completed_training_battles"] = 0
    binding = N(kind=GoalKind.EVOLVE_SPECIES)
    if composed:
        binding = N(kind=GoalKind.ACQUIRE_SPECIES, binding_ref="red-npc-trade-dependency:1:77")
        evidence = dict(mechanic="trade_level_dependency", complete=False,
            intermediate=evidence, intermediate_verification=dict(
                status="failed", failure_reason="outcome_not_verified"))
    report = GoalExecutionReport(1 if fault == "unmeasured" else 2, 20, evidence)
    verdict = GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
    assert ordinary_player_setback(
        binding,
        AutonomousSnapshot(b"before", before_facts, True),
        AutonomousSnapshot(b"after", after_facts, True),
        report,
        verdict,
        RuntimeError("unknown failure") if fault == "exception" else None,
    ) is (fault is None)
    assert verdict.status.value == "failed"


@pytest.mark.parametrize("composed", [False, True])
@pytest.mark.parametrize("quantum_stop", [False, True])
def test_returned_partial_dose_renews_before_starting_another_loan(
    tmp_path, monkeypatch, quantum_stop, composed
):
    target_kind = GoalKind.ACQUIRE_SPECIES if composed else GoalKind.EVOLVE_SPECIES
    state = {"n": 0}
    calls = []

    def snapshot():
        n = state["n"]
        return AutonomousSnapshot(str(n).encode(), facts(n), True)

    def execute():
        calls.append("dose")
        state["n"] += 1
        report = GoalExecutionReport(
            1,
            10,
            dict(
                schema="pokemon.core.routed-semantic-goal-report.v1",
                destination_kind="evolve_species",
                evolution_partial=True,
                budget_reconciled=True,
                destination_bound=True,
                destination_executed=True,
                route_verified=True,
                within_budget=True,
                retained_active_roster_restored=True,
                settlement_reserve_reached=not quantum_stop,
                quantum_limit_reached=quantum_stop,
                completed_training_quanta=3,
                maximum_training_quanta=3,
                completed_training_battles=3,
            ),
        )

        if composed:
            return GoalExecutionReport(1, 10, dict(mechanic="trade_level_dependency",
                complete=False, intermediate=dict(report.evidence),
                intermediate_verification=dict(status="failed", failure_reason="outcome_not_verified")))
        return report

    def observe(ordinal):
        bindings = tuple(
            replace(
                _binding(kind, binding_ref="red-npc-trade-dependency:1:77" if composed and kind is target_kind else kind.value, calls=[]),
                execute=execute,
                verify=lambda _: GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED),
            )
            for kind in (target_kind, GoalKind.DEVELOP_TEAM)
        )
        return build_red_live_option_set(
            supplements=(),
            situation=_situation(),
            binding_set=GoalBindingSet(tuple(b.opportunity for b in bindings), bindings),
            model_feature_version=5,
            ordering_seed_sha256="a" * 64,
            readiness=PlayerReadiness.from_context(menu().context, menu().remaining_budget),
            economy_snapshot=EconomySnapshot(facts(state["n"])["cash"], ()),
            target_cash=0,
        )

    def select(model, options, *, seed, **kwargs):
        index = next(i for i, b in enumerate(options.bindings) if b.kind is target_kind)
        return RedLiveOptionChoice(
            options,
            index,
            RedLiveOptionSelectionMode.MODEL_EXPLORATION,
            (0.0, 0.0),
            (0.5, 0.5),
            seed,
            model.model_sha256,
        )

    monkeypatch.setattr(runner, "select_red_live_option", select)
    result = runner.run_autonomous_options(
        model=upgrade_option_value_model_for_readiness(_model()),
        output=tmp_path / "run",
        snapshot=snapshot,
        observe=observe,
        seed=17,
        maximum_decisions=2,
        continuous_player=True,
        maximum_cash_spent=None,
        provenance={"test_only": True},
    )
    assert calls == ["dose"]
    assert result["stop_reason"] == "settlement_budget"
    assert result["executed_decisions"] == 1 and result["ordinary_setbacks"] == 1
    assert result["outcomes"][0]["verification"] == "failed"
    assert not (tmp_path / "run/step-001/execution-started.json").exists()


@pytest.mark.parametrize("fault", [None, "guard_changed", "boxed_stock_lost", "xp_lost"])
def test_partial_dose_accepts_earned_original_evolution_only_with_same_census_guard(fault):
    old, new = "pokemon:national:010", "pokemon:national:011"
    proof = dict(
        schema="pokemon.red.retained-party-continuation.v1",
        guard_sha256="a" * 64,
        native_identity_verified=True,
        other_specimen_counts={"pokemon:national:007": 1},
    )
    a = dict(proof, individuals={"original": dict(species_ref=old, level=6, experience=200)})
    b = dict(proof, individuals={"original": dict(species_ref=new, level=7, experience=343)})
    if fault == "guard_changed":
        b["guard_sha256"] = "b" * 64
    elif fault == "boxed_stock_lost":
        b["other_specimen_counts"] = {}
    elif fault == "xp_lost":
        b["individuals"]["original"]["experience"] = 199
    before = AutonomousSnapshot(
        b"0",
        dict(
            facts(),
            owned_species=[old],
            specimen_counts={old: 1, "pokemon:national:007": 1},
            retained_party_continuation=a,
        ),
        True,
    )
    after = AutonomousSnapshot(
        b"1",
        dict(
            facts(1),
            owned_species=[old, new],
            specimen_counts={new: 1, "pokemon:national:007": 1},
            retained_party_continuation=b,
        ),
        True,
    )
    report = GoalExecutionReport(
        1,
        10,
        dict(
            schema="pokemon.red.native-evolution-partial.v1",
            bounded=True,
            source_species_ref="pokemon:national:043",
            target_species_ref="pokemon:national:044",
            evolution_partial=True,
            retained_active_roster_restored=True,
            completed_training_battles=3,
            settlement_reserve_reached=True,
        ),
    )
    assert ordinary_player_setback(
        N(kind=GoalKind.EVOLVE_SPECIES),
        before,
        after,
        report,
        GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED),
        None,
    ) is (fault is None)
