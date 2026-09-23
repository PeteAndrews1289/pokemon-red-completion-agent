from copy import deepcopy
from dataclasses import replace

import numpy as np
import pytest
from red_outcome_value_learning import (
    OFFSETS,
    empirical_preferences,
    extend_problem,
    fit_once,
    outcome_gate,
    validate_offsets,
)
from test_red_effect_selector import effect
from test_red_status_readout_learning import problem_inputs

from pokemon_red_completion.red_effect_selector_head import augment_head
from pokemon_red_completion.red_effect_selector_learning import prepare_combination
from pokemon_red_completion.red_status_win_conditioned_returns import RETURN_SCHEMA


def setup():
    frozen, initial, originals = problem_inputs()
    groups = deepcopy(originals)
    for g in groups:
        g[0]["return_schema"] = RETURN_SCHEMA
    old = prepare_combination(groups, initial, frozen, initial, originals, effect())
    actor = replace(initial, move=augment_head(initial.move, effect()["weights"], "a"*64))
    target = deepcopy(groups[1][0])
    target.update(capture_id="new", offsets=OFFSETS)
    target["timing_returns"] = {str(s): [target["returns"][i]]*8
                                for i, s in enumerate(target["slots"])}
    return old, actor, [target], groups, initial


def test_extended_objective_preserves_constraints_and_gradient():
    old, actor, targets, _, _ = setup()
    p = extend_problem(old, actor, targets)
    assert np.array_equal(p.constraints, old.constraints)
    assert p.protected == old.protected
    x, eps = p.anchor+.1, 1e-6
    numerical = [(p.objective(x+eps*e)[0]-p.objective(x-eps*e)[0])/(2*eps)
                 for e in np.eye(len(x))]
    assert p.objective(x)[1] == pytest.approx(numerical, abs=1e-8)


def test_one_fit_learns_new_values_without_mutating_frozen_heads():
    old, actor, targets, groups, initial = setup()
    p = extend_problem(old, actor, targets)
    candidate, report = fit_once(p, actor, targets, groups, initial)
    assert report["passed"] and report["retention_regressions"] == 0
    assert candidate.move.predict_index(targets[0]["vectors"]) == 1
    assert np.array_equal(candidate.move.weights1, actor.move.weights1)
    assert candidate.move.effect_weights == actor.move.effect_weights
    assert candidate.control.to_dict() == actor.control.to_dict()
    assert candidate.switch.to_dict() == actor.switch.to_dict()
    assert "new" in candidate.train_capture_ids


@pytest.mark.parametrize("mutation", ["root", "role", "mean", "offset", "nan", "duplicate"])
def test_new_targets_fail_closed(mutation):
    old, actor, targets, _, _ = setup()
    t = targets[0]
    if mutation == "root":
        t["root"] = "unknown"
    elif mutation == "role":
        t["role"] = "holdout"
    elif mutation == "mean":
        t["returns"][0] += 1
    elif mutation == "offset":
        t["offsets"] = [0]*8
    elif mutation == "nan":
        t["timing_returns"][str(t["slots"][0])][0] = float("nan")
    else:
        targets.append(deepcopy(t))
    with pytest.raises(ValueError):
        extend_problem(old, actor, targets)


def rows():
    base = [{"case": "x", "won": True, "decisions": 8, "return": 9.,
             "metrics": {"invalid_action_failures": 0}, "status_choices": []}]
    candidate = deepcopy(base)
    candidate[0]["return"] = 10.
    candidate[0]["status_choices"] = [{"concerns": []}, {"concerns": ["occupied"]}]
    return candidate, base


def test_new_gate_retains_raw_flags_and_old_verdict():
    report = outcome_gate(*rows())
    assert report["passed"] and report["concerning_selections"] == 1
    assert not report["original_zero_flag_passed"]


@pytest.mark.parametrize("failure", ["wins", "decisions", "invalid", "improvement"])
def test_outcome_gate_preserves_other_requirements(failure):
    chosen, base = rows()
    if failure == "wins":
        chosen[0]["won"] = False
    elif failure == "decisions":
        chosen[0]["decisions"] = 11
    elif failure == "invalid":
        chosen[0]["metrics"]["invalid_action_failures"] = 1
    else:
        chosen[0]["return"] = 9.
    assert not outcome_gate(chosen, base)["passed"]


def test_empty_or_duplicate_evaluation_cannot_pass():
    chosen, base = rows()
    with pytest.raises(ValueError):
        outcome_gate([], [])
    with pytest.raises(ValueError):
        outcome_gate(chosen+chosen, base)


@pytest.mark.parametrize("bad", [-1, True, 0.0])
def test_invalid_counts_cannot_cancel_or_masquerade_as_success(bad):
    chosen, base = rows()
    chosen[0]["metrics"]["invalid_action_failures"] = bad
    with pytest.raises(ValueError):
        outcome_gate(chosen, base)


@pytest.mark.parametrize("bad", [(0, 3, 5, 7, 11, 13, 17, 23),
                                 (0, 1, 2, 3, 5, 7, 11, 13),
                                 (-1, 1, 2, 3, 5, 7, 11, 12),
                                 (0, 1, 2, 3, 5, 7, 11, True),
                                 (0, 1, 2, 3, 5, 7, 11, 11)])
def test_timing_preflight_rejects_retired_and_out_of_bound_schedules(bad):
    with pytest.raises(ValueError, match="offsets"):
        validate_offsets(bad)
    validate_offsets(OFFSETS)


def test_invalid_schedule_stops_before_rom_packet_or_output_access(monkeypatch):
    from types import SimpleNamespace

    import run_red_outcome_value_pilot as pilot

    monkeypatch.setattr(pilot, "OFFSETS", (0, 3, 5, 7, 11, 13, 17, 23))
    with pytest.raises(ValueError, match="offsets"):
        pilot.run(SimpleNamespace())  # no root, output, ROM or native session exists


def test_corrected_packet_requires_explicit_successor_switch():
    from types import SimpleNamespace

    import run_red_outcome_value_pilot as pilot

    with pytest.raises(ValueError, match="approval"):
        pilot.run(SimpleNamespace())


def test_broad_curriculum_balances_every_family_without_using_screen_rows(monkeypatch):
    import run_red_outcome_value_pilot as pilot
    from red_status_root_coverage import FAMILIES

    seeds = []

    def crossed(cartridge, roots, *, seed):
        seeds.append(seed)
        return [{"id": f"balanced-{f}-{v}-{c}", "family": f, "contrast": c,
                 "source_index": i, "root": roots[i],
                 "role": "holdout" if i == 3 else "train"}
                for i in range(4) for f in sorted(FAMILIES)
                for v in ((2,) if i == 3 else (0, 1)) for c in range(4)]

    monkeypatch.setattr(pilot, "crossed_recipes", crossed)
    train, screen = pilot.recipes(None, list("abcd"), broad=True)
    assert len(train) == 64 and len(screen) == 32
    assert {r["family"] for r in train} == FAMILIES
    assert {r["contrast"] for r in train} == set(range(4))
    assert {r["root"] for r in train} == {"a", "b"}
    assert {r["role"] for r in train} == {"train"}
    assert {r["root"] for r in screen} == {"d"}
    assert seeds == [2026092235, 2026092236]
    assert not {r["id"] for r in train} & {r["id"] for r in screen}


def test_cumulative_measured_targets_preserve_original_constraints():
    old, actor, targets, groups, initial = setup()
    prior = extend_problem(old, actor, targets)
    new = deepcopy(targets)
    new[0]["capture_id"] = "fresh-next"
    p = extend_problem(prior, actor, new)
    assert np.array_equal(p.constraints, old.constraints)
    assert p.protected == old.protected
    assert len(p.contrast) == len(old.contrast)+2
    _, report = fit_once(p, actor, new, [*groups, targets], initial)
    assert report["passed"]


def test_one_lucky_timing_does_not_become_a_near_certain_preference():
    old, actor, targets, groups, _ = setup()
    t = targets[0]
    t["timing_returns"] = {"1": [0.]*8, "2": [0.]*7+[20.]}
    t["returns"] = [0., 2.5]
    p = extend_problem(old, actor, targets)
    empirical = empirical_preferences(p, [*(t for g in groups for t in g), *targets])
    assert p.desired[-1] > .999
    assert empirical.desired[-1] == pytest.approx(.5625)
    assert np.array_equal(empirical.constraints, p.constraints)
    assert np.array_equal(empirical.weights, p.weights)
    assert empirical.protected == p.protected


def test_empirical_objective_does_not_relabel_or_change_native_returns():
    old, actor, targets, groups, _ = setup()
    p = extend_problem(old, actor, targets)
    all_targets = [*(t for g in groups for t in g), *targets]
    before = deepcopy(all_targets)
    assert empirical_preferences(p, all_targets).desired[-1] > .99
    assert all_targets == before
    all_targets[-1]["role"] = "holdout"
    with pytest.raises(ValueError, match="TRAIN"):
        empirical_preferences(p, all_targets)


def test_finishing_readout_uses_explicit_whole_model_baseline_and_feasible_start():
    old, actor, targets, groups, initial = setup()
    p = extend_problem(old, actor, targets)
    pretrained, _ = fit_once(p, actor, targets, groups, initial)
    start = np.append(pretrained.move.weights2, pretrained.move.effect_readout)
    final, report = fit_once(p, pretrained, targets, groups, initial,
                             start=start, reference_actor=actor)
    assert report["passed"] and report["new_group"]["actor"]["errors"] == 1
    assert report["new_group"]["candidate"]["errors"] == 0
    assert np.array_equal(final.move.weights1, pretrained.move.weights1)
    with pytest.raises(ValueError, match="start"):
        fit_once(p, pretrained, targets, groups, initial, start=np.full_like(start, np.nan))
