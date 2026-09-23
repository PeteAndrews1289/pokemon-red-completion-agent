import json
from dataclasses import replace

import pytest
from test_red_live_option_menu import (
    _binding,
    _fishing_candidate,
    _model,
    _no_ordinary_bindings,
    _situation,
)

from pokemon_red_completion.goal_manager import GoalFailureReason, GoalKind
from pokemon_red_completion.goal_manager_runtime import (
    GoalExecutionReport,
    GoalManagerRuntimeError,
    GoalVerification,
)
from pokemon_red_completion.goal_search_memory import GoalSearchMemory
from pokemon_red_completion.red_autonomous_player import AutonomousSnapshot, run_autonomous_options
from pokemon_red_completion.red_integrated_play import (
    menu_with_search_history,
    objective_key,
    ordinary_paid_search_setback,
    search_objective_key,
    spending_bound,
)
from pokemon_red_completion.red_live_option_menu import (
    build_red_live_option_set,
    supplemental_live_option,
)


def _facts(n=0):
    return dict(actions=n, completed_actions=n, frames=10*n, cash=5000-500*n,
                owned_species=["pokemon:national:001"], specimen_counts={"one": 1}, specimens=1,
                party_training=[[1, 1, 125]], party_hp=[20], party_pp=[[20]], party_status=[0],
                bag_items=[[1, 2]], battle_state=0, input_ready=True, buttons_released=True,
                session=dict(in_safari_zone=False, safari_game_over=False))


def _report():
    return GoalExecutionReport(1, 10, dict(
        admission=dict(status="ok", single_admission=True),
        paid_session_departure=dict(passed=True), captures=0,
        search_safety_stopped=False, search_resource_stopped=True, search_exhausted=False,
    ))


def _paid_binding():
    return replace(_binding(GoalKind.ACQUIRE_SPECIES, binding_ref="origin:one", calls=[]),
                   search_source_ref="pokemon.red:paid-safari:source-a")


@pytest.mark.parametrize("value", [True, 12, "", "a" * 63, "A" * 64, "a" * 64 + "\n"])
def test_binding_rejects_invalid_search_target_fingerprint(value):
    with pytest.raises(GoalManagerRuntimeError, match="search objective"):
        replace(_paid_binding(), search_objective_sha256=value)


def test_target_fingerprint_requires_acquisition_binding():
    with pytest.raises(GoalManagerRuntimeError, match="search objective"):
        replace(_paid_binding(), kind=GoalKind.RESTORE_TEAM, search_source_ref=None,
                search_objective_sha256="a" * 64)


def test_strict_setback_requires_complete_receipts_and_unchanged_reserves():
    before = AutonomousSnapshot(b"0", _facts(), True)
    after = AutonomousSnapshot(b"1", _facts(1), True)
    failed = GoalVerification.failed(GoalFailureReason.SEARCH_EXHAUSTED)
    report = _report()

    def accepted(b=before, t=after, r=report, v=failed, e=None):
        return ordinary_paid_search_setback(_paid_binding(), b, t, r, v, e)

    assert accepted()
    assert not accepted(e=RuntimeError("controller failed"))
    assert not accepted(t=replace(after, safe=False))
    assert not accepted(v=GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED))
    assert not accepted(r=None)
    for field, value in {
        "cash": 4000, "actions": 2, "completed_actions": 0, "frames": 11,
        "party_hp": [19], "party_status": [8], "party_pp": [[19]], "bag_items": [],
        "specimen_counts": {}, "owned_species": [], "party_training": [[1, 1, 126]],
        "buttons_released": False, "input_ready": False, "battle_state": 1,
        "session": dict(in_safari_zone=True, safari_game_over=False),
    }.items():
        assert not accepted(t=replace(after, facts={**after.facts, field: value})), field
    for field in before.facts:
        facts = dict(before.facts)
        facts.pop(field)
        assert not accepted(b=replace(before, facts=facts)), field
    for field, value in {
        "admission": {}, "paid_session_departure": {"passed": False},
        "captures": True, "search_safety_stopped": True, "search_resource_stopped": False,
    }.items():
        assert not accepted(r=replace(_report(), evidence={**_report().evidence, field: value}))


def _options(execute, verify):
    bindings = tuple(replace(_paid_binding(), binding_ref=f"origin:{i}",
                             execute=execute, verify=verify) for i in range(2))
    return build_red_live_option_set(
        situation=_situation(resources=0.1), binding_set=_no_ordinary_bindings(),
        supplements=tuple(supplemental_live_option(
            b, _fishing_candidate(b.binding_ref, travel=0.1 + 0.5*i)
        ) for i, b in enumerate(bindings)), model_feature_version=4,
        ordering_seed_sha256="a" * 64,
    )


@pytest.mark.parametrize("failure", [None, "exception", "unsafe", "unknown", "cost"])
def test_contiguous_episode_keeps_failed_labels_and_replans(tmp_path, failure):
    state = {"n": 0}
    observed = []

    def execute():
        assert (tmp_path / "run" / f"step-{state['n']:03d}" / "decision.json").exists()
        state["n"] += 1
        if failure == "exception":
            raise RuntimeError("stop after input")
        return _report()

    def verify(report):
        if failure == "unknown":
            return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        return (GoalVerification.succeeded() if state["n"] == 5 else
                GoalVerification.failed(GoalFailureReason.SEARCH_EXHAUSTED))

    def snapshot():
        facts = _facts(state["n"])
        if failure == "cost" and state["n"]:
            facts["cash"] -= 1
        return AutonomousSnapshot(str(state["n"]).encode(), facts,
                                  not (failure == "unsafe" and state["n"]))

    def observe(ordinal):
        observed.append(state["n"])
        return _options(execute, verify)

    result = run_autonomous_options(
        model=_model(), output=tmp_path / "run", snapshot=snapshot, observe=observe,
        seed=17, maximum_decisions=5, provenance={}, integrated_play=True,
        maximum_cash_spent=2500,
    )
    if failure:
        assert observed == [0]
        assert result["executed_decisions"] == 1
        assert (tmp_path / "run/step-000/terminal.state").read_bytes() == b"1"
    else:
        assert observed == [0, 1, 2, 3, 4]
        assert result["model_decisions"] == 5
        assert result["ordinary_setbacks"] == 4
        assert result["successful_decisions"] == 1
        assert result["accounted_cash_spent"] == 2500
        assert [r["verification"] for r in result["outcomes"]] == ["failed"]*4 + ["succeeded"]
        for i in range(5):
            step = tmp_path / "run" / f"step-{i:03d}"
            before = json.loads((step / "search-memory-before.json").read_text())
            after = json.loads((step / "search-memory-after.json").read_text())
            GoalSearchMemory.from_private_dict(after["memory"]).require_extension(
                GoalSearchMemory.from_private_dict(before["memory"]))
            intent = json.loads((step / "intent.json").read_text())
            histories = [c["search_history"] for c in intent["menu"]["menu"]["candidates"]]
            assert all(h["attempts"] == i for h in histories)
            assert all(h["exhausted"] == i for h in histories)


def test_history_neither_masks_nor_reorders_and_survives_origin_change():
    options = _options(lambda: _report(), lambda _: GoalVerification.succeeded())
    memory = GoalSearchMemory()
    objective = objective_key(_facts())
    memory.record(_paid_binding().search_memory_source, objective,
                  exhausted=True, actions=10, frames=100)
    changed = menu_with_search_history(options, memory, objective)
    assert changed.bindings == options.bindings
    assert changed.menu.available_indices == options.menu.available_indices
    assert all(c.search_history.attempts == 1 for c in changed.menu.candidates)
    assert "source-a" not in json.dumps(changed.public_dict())
    assert changed.menu.candidate_vector(0) != options.menu.candidate_vector(0)
    assert spending_bound(_paid_binding()) == 500
    assert spending_bound(replace(_paid_binding(), search_source_ref="unknown")) is None


def test_target_context_survives_unrelated_progress_but_not_changed_targets_or_source():
    options = _options(lambda: _report(), lambda _: GoalVerification.succeeded())
    options = replace(options, bindings=tuple(
        replace(b, search_objective_sha256="a" * 64) for b in options.bindings))
    memory = GoalSearchMemory()
    memory.record(options.bindings[0].search_memory_source, "a" * 64,
                  exhausted=True, actions=10, frames=100)
    retained = memory.private_dict()
    old_fallback = objective_key(_facts())
    new_fallback = objective_key({**_facts(), "cash": 12,
                                 "owned_species": ["pokemon:national:001", "pokemon:122"]})
    assert old_fallback != new_fallback
    before = menu_with_search_history(options, memory, old_fallback)
    after = menu_with_search_history(options, memory, new_fallback)
    assert before == after
    assert all(c.search_history.attempts == 1 for c in after.menu.candidates)
    assert "a" * 64 not in json.dumps(after.public_dict())
    for changed in (
        replace(options.bindings[0], search_objective_sha256="b" * 64),
        replace(options.bindings[0], search_source_ref="pokemon.red:paid-safari:other"),
    ):
        changed_options = replace(options, bindings=(changed, options.bindings[1]))
        menu = menu_with_search_history(changed_options, memory, new_fallback).menu
        assert menu.candidates[0].search_history.attempts == 0
        assert menu.candidates[1].search_history.attempts == 1
        assert menu.available_indices == options.menu.available_indices
    assert memory.private_dict() == retained
    assert search_objective_key(_paid_binding(), new_fallback) == new_fallback


def test_runner_uses_same_target_context_before_and_after_unrelated_success(tmp_path):
    state = {"n": 0}

    def execute():
        state["n"] += 1
        return _report()

    def snapshot():
        n = state["n"]
        facts = _facts(n)
        if n >= 2:
            facts["owned_species"] += ["pokemon:national:122"]
            facts["cash"] += 500
        return AutonomousSnapshot(str(n).encode(), facts, True)

    def observe(_):
        trading = state["n"] == 1
        options = _options(execute, lambda _: GoalVerification.succeeded() if trading else
                           GoalVerification.failed(GoalFailureReason.SEARCH_EXHAUSTED))
        return replace(options, bindings=tuple(replace(
            b, search_source_ref="pokemon.red:npc-trade:1" if trading else b.search_source_ref,
            search_objective_sha256=None if trading else "a" * 64,
        ) for b in options.bindings))

    result = run_autonomous_options(
        model=_model(), output=tmp_path / "run", snapshot=snapshot, observe=observe,
        seed=17, maximum_decisions=4, provenance={}, integrated_play=True,
        maximum_cash_spent=1500,
    )
    assert result["executed_decisions"] == 4
    assert result["successful_decisions"] == 1
    assert result["ordinary_setbacks"] == 3
    assert result["accounted_cash_spent"] == 1500
    for i, expected in ((0, 0), (2, 1), (3, 2)):
        step = tmp_path / "run" / f"step-{i:03d}"
        intent = json.loads((step / "intent.json").read_text())
        assert all(c["search_history"]["attempts"] == expected
                   for c in intent["menu"]["menu"]["candidates"])
        before = json.loads((step / "search-memory-before.json").read_text())
        after = json.loads((step / "search-memory-after.json").read_text())
        assert set(before["objectives_by_binding"].values()) == {"a" * 64}
        assert after["objective_sha256"] == "a" * 64
        GoalSearchMemory.from_private_dict(after["memory"]).require_extension(
            GoalSearchMemory.from_private_dict(before["memory"]))


def test_spending_bound_stops_before_another_execution(tmp_path):
    state = {"n": 0}

    def execute():
        state["n"] += 1
        return _report()

    result = run_autonomous_options(
        model=_model(), output=tmp_path / "run", seed=17, provenance={},
        snapshot=lambda: AutonomousSnapshot(str(state["n"]).encode(), _facts(state["n"]), True),
        observe=lambda _: _options(execute, lambda _: GoalVerification.failed(
            GoalFailureReason.SEARCH_EXHAUSTED)),
        integrated_play=True, maximum_cash_spent=500,
    )
    assert state["n"] == 1
    assert result["stop_reason"] == "integrated_scope_or_spending_boundary"
    assert not (tmp_path / "run/step-001/execution-started.json").exists()
