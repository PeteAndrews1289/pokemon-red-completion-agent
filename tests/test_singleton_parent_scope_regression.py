"""ROM-free guard regressions; no game or learned model execution."""

from dataclasses import replace

from test_red_branch_recovery import menu, parent_choice
from test_red_consequence_choice import progress_head, provisional_args

import pokemon_red_completion.red_consequence_choice as composition
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.red_live_option_menu import RedLiveOptionSelectionMode


def test_absent_scope_with_multiple_actual_alternatives_keeps_full_parent(tmp_path, monkeypatch):
    options, combat, state, runtime = menu(tmp_path, monkeypatch)
    args, _ = provisional_args(tmp_path / "model", monkeypatch)
    options = replace(
        options,
        menu=replace(
            options.menu,
            candidates=tuple(
                replace(c, challenge=None) if b.kind is GoalKind.DEVELOP_TEAM else c
                for b, c in zip(options.bindings, options.menu.candidates, strict=True)
            ),
        ),
    )
    prep = next(i for i, b in enumerate(options.bindings) if b.kind is GoalKind.DEVELOP_TEAM)
    assert (
        sum(not composition._unbound_level_dose(options, i) for i in options.menu.available_indices)
        >= 2
    )
    seen = []

    def parent(model, observed, **kwargs):
        seen.append(observed)
        return parent_choice(
            observed, prep, model, seed=kwargs["seed"], mode=RedLiveOptionSelectionMode.MODEL_GREEDY
        )

    monkeypatch.setattr(composition, "select_red_live_option", parent)
    choice = composition.select_branch_recovery_live_option(
        args["model"],
        options,
        progress_head("kind.develop"),
        objective_ref="absent-scope",
        seed=3,
        greedy_selection=True,
        refine_preparation=True,
        defer_unbound_preparation=True,
        allow_singleton_parent_support=True,
    )
    assert seen == [options] and seen[0] is options
    assert choice.selected_binding is options.binding(prep)
    assert choice.branch_recovery.child is None
    assert choice.branch_recovery.parent.mode is RedLiveOptionSelectionMode.MODEL_GREEDY
    assert not runtime.recorder.trace
