from copy import deepcopy
from dataclasses import replace

import pytest
from test_red_switch_control_examples import composed_case

from pokemon_red_completion import red_switch_control_curriculum as curriculum


def event(mode="main", hp=(40, 30, 20), index=1, status=(0, 0, 0)):
    return {
        "event": "decision_started",
        "mode": mode,
        "decision_index": index,
        "state_before": {"party_hp": list(hp), "party_status": list(status)},
        "legal_party_slots": [2, 3],
    }


@pytest.mark.parametrize("family", curriculum.FAMILIES[:3])
def test_opening_selected_before_any_outcome(family):
    assert curriculum.capture_matches(family, event())
    assert not curriculum.capture_matches(family, event(index=2))
    assert not curriculum.capture_matches(family, event(mode="switch_prompt"))


def test_native_status_requires_later_affliction_not_truthy_zero_list():
    assert not curriculum.capture_matches("status_attrition", event(index=2))
    assert not curriculum.capture_matches("status_attrition", event(status=(8, 0, 0)))
    assert curriculum.capture_matches("status_attrition", event(index=2, status=(8, 0, 0)))


def test_forced_replacement_requires_comparison_and_declared_faint_bucket():
    e = event("forced_switch", (0, 0, 40, 50, 20, 15), 5)
    assert curriculum.capture_matches("forced_replacement", e, faint_count=2)
    assert not curriculum.capture_matches("forced_replacement", e, faint_count=1)
    e["legal_party_slots"] = [3]
    assert not curriculum.capture_matches("forced_replacement", e, faint_count=2)


def test_optional_decline_control_and_non_decision_events():
    assert curriculum.capture_matches("optional_prompt", event("switch_prompt"))
    assert not curriculum.capture_matches("optional_prompt", {"event": "episode_finished"})
    with pytest.raises(ValueError):
        curriculum.capture_matches("unknown", event())


@pytest.mark.parametrize("faints", range(5))
def test_optional_prompt_any_faint_bucket_is_explicit(faints):
    e = event("switch_prompt", (0,) * faints + (40,) * (6 - faints), 9)
    assert curriculum.capture_matches("optional_prompt", e, faint_count=None)
    assert curriculum.capture_matches("optional_prompt", e) is (faints == 0)
    e["legal_party_slots"] = []
    assert not curriculum.capture_matches("optional_prompt", e, faint_count=None)


@pytest.mark.parametrize("family", [*curriculum.FAMILIES[:-1], "unknown"])
def test_any_faint_bucket_cannot_weaken_other_strata(family):
    with pytest.raises(ValueError):
        curriculum.capture_matches(family, event(), faint_count=None)


@pytest.mark.parametrize("mode", ["main", "forced_switch"])
def test_any_prompt_bucket_still_requires_native_prompt(mode):
    assert not curriculum.capture_matches("optional_prompt", event(mode), faint_count=None)
    assert not curriculum.capture_matches(
        "optional_prompt", {"event": "episode_finished"}, faint_count=None
    )


def test_one_fit_preserves_frozen_components_and_rebuilds_after_switch(monkeypatch):
    target, model = composed_case()
    original = deepcopy(model.to_dict())
    changed = replace(model.switch, weights2=-model.switch.weights2)
    calls = []

    def fake_fit(initial, terminal, anchors, budgets, **kw):
        calls.append((initial, terminal, anchors, budgets, kw))
        return (changed if len(calls) == 1 else initial), {"epochs": kw["epochs"]}

    monkeypatch.setattr(curriculum, "fit_budgeted_head", fake_fit)
    candidate, report = curriculum.fit_switch_control_once(
        model, [target], {"anchors": [target]}, epochs=1, learning_rate=0.005
    )
    assert len(calls) == 2
    expected = curriculum.build_switch_control_examples([target], replace(model, switch=changed))
    assert calls[1][1] == tuple(expected["control"])
    assert candidate.move.to_dict() == original["move"]
    assert candidate.damage_reference.to_dict() == original["damage_reference"]
    assert model.to_dict() == original and report["fits"] == 1


def test_infeasible_switch_stage_stops_before_control(monkeypatch):
    target, model = composed_case()
    calls = []

    def reject(*args, **kw):
        calls.append(kw)
        return None, {"epochs": 1}

    monkeypatch.setattr(curriculum, "fit_budgeted_head", reject)
    candidate, report = curriculum.fit_switch_control_once(
        model, [target], {"anchors": [target]}, epochs=1, learning_rate=0.005
    )
    assert candidate is None and not report["passed"] and len(calls) == 1


@pytest.mark.parametrize("update_rule", ["adam", "joint_ranking_v1"])
def test_real_bounded_fit_cannot_modify_damage_or_status(update_rule):
    target, model = composed_case()
    candidate, report = curriculum.fit_switch_control_once(
        model, [target], {"anchors": [target]}, epochs=2, learning_rate=0.005,
        update_rule=update_rule,
    )
    assert report["fits"] == 1
    if candidate is not None:
        assert candidate.move.to_dict() == model.move.to_dict()
        assert candidate.damage_reference.to_dict() == model.damage_reference.to_dict()


def test_composed_regret_keeps_cost_of_excluded_best_action():
    from pokemon_red_completion.red_trainer_practice_head import TrainerHeadExample

    target = {
        "heads": {
            "control": {
                "choice_refs": [
                    "pokemon.core:battle:move:1",
                    "pokemon.core:battle:switch:2",
                    "pokemon.core:battle:switch:3",
                ],
                "returns": [5.0, 0.0, 10.0],
            }
        }
    }
    row = TrainerHeadExample(((0.0,), (1.0,)), (0,), mean_returns=(5.0, 0.0))
    assert curriculum.control_proposal_regret_offset([target], [row]) == 5.0
    # Choosing the better of two inferior proposals still incurs5units of
    # whole-action regret. A conditional perfect score must not erase that.
    better = replace(row, mean_returns=(5.0, 10.0), best_indices=(1,))
    assert curriculum.control_proposal_regret_offset([target], [better]) == 0.0
    target["heads"]["control"]["timing_returns"] = [[1, 0, 3], [3, 0, 7]]
    timed = replace(row, mean_returns=(2.0, 0.0))
    assert curriculum.control_proposal_regret_offset([target], [timed]) == 3.0


def test_control_retention_budgets_include_changed_proposal_cost(monkeypatch):
    target, model = composed_case()
    changed = replace(model.switch, weights2=-model.switch.weights2)
    calls = []

    def fit(initial, terminal, anchors, budgets, **kw):
        calls.append(budgets)
        return (changed if len(calls) == 1 else initial), {}

    monkeypatch.setattr(curriculum, "fit_budgeted_head", fit)
    curriculum.fit_switch_control_once(
        model, [target], {"anchors": [target]}, epochs=1, learning_rate=0.005
    )
    before = curriculum.build_switch_control_examples([target], model)["control"]
    after = curriculum.build_switch_control_examples([target], replace(model, switch=changed))[
        "control"
    ]
    budget = calls[1][0]
    assert budget.offset == curriculum.control_proposal_regret_offset([target], after)
    assert budget.maximum == pytest.approx(
        curriculum.selected_regret(model.control, tuple(before))
        + curriculum.control_proposal_regret_offset([target], before)
        + 1e-10
    )


def comparison():
    return [
        dict(
            case=f"{family}-{i}",
            family=family,
            offset=offset,
            actor=actor,
            win=i < 3,
            stop="battle_won" if i < 3 else "party_defeated",
            decisions=10,
            pp_spent=5,
            invalid=0,
            teacher_interventions=0,
            type_immune_attacks=1 if actor == "baseline" else 0,
            zero_power_choices_with_covered_alternative=0,
        )
        for family in curriculum.FAMILIES
        for i in range(4)
        for offset in (0, 6, 12)
        for actor in ("baseline", "candidate")
    ]


def test_comparison_accepts_learning_without_perfect_wins():
    report = curriculum.summarize_switch_comparison(comparison())
    assert report["passed"] and report["totals"]["candidate"]["win"] == 54
    assert report["common_wins"] == 54 and report["authority_promotions"] == 0


@pytest.mark.parametrize(
    "fault", ["missing", "duplicate", "censored", "family", "inconsistent_win"]
)
def test_comparison_rejects_incomplete_or_corrupt_inventory(fault):
    rows = comparison()
    if fault == "missing":
        rows.pop()
    elif fault == "duplicate":
        rows.append(deepcopy(rows[0]))
    elif fault == "censored":
        rows[0]["stop"] = "decision_budget"
    elif fault == "family":
        rows[0]["family"] = "unknown"
    else:
        rows[0]["win"] = False
    with pytest.raises(ValueError):
        curriculum.summarize_switch_comparison(rows)


@pytest.mark.parametrize("fault", ["wins", "pp", "decisions", "risk", "invalid", "teacher"])
def test_comparison_preserves_each_original_gate(fault):
    rows = comparison()
    r = next(r for r in rows if r["actor"] == "candidate" and r["win"])
    if fault == "wins":
        r.update(win=False, stop="party_defeated")
    elif fault in ("pp", "decisions"):
        r["pp_spent" if fault == "pp" else fault] += 1
    elif fault == "risk":
        for row in rows:
            if row["actor"] == "candidate":
                row["type_immune_attacks"] = 1
    else:
        r["invalid" if fault == "invalid" else "teacher_interventions"] = 1
    assert not curriculum.summarize_switch_comparison(rows)["passed"]


def test_forced_mechanics_cannot_dilute_policy_risk_or_hide_costs():
    rows = comparison()
    for row in rows:
        row["forced_mechanics"] = 5
    result = curriculum.summarize_switch_comparison(rows)
    assert result["totals"]["baseline"]["decisions"] == 720
    assert result["totals"]["baseline"]["learned_decisions"] == 360
    assert result["totals"]["baseline"]["risk_rate"] == 0.2
    assert result["common_win_costs"]["decisions"]["baseline"] == 540


@pytest.mark.parametrize("forced", [-1, True, 10, 11])
def test_malformed_forced_counts_fail_closed(forced):
    rows = comparison()
    rows[0]["forced_mechanics"] = forced
    with pytest.raises(ValueError, match="forced"):
        curriculum.summarize_switch_comparison(rows)
