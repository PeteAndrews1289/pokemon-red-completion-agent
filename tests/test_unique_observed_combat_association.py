"""ROM-free composition fixtures; no native learning or score accuracy claims."""

from dataclasses import replace

import pytest
from test_red_branch_recovery import menu
from test_red_consequence_choice import progress_head, provisional_args

import pokemon_red_completion.red_consequence_choice as C
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.living_dex_option_value import (
    LivingDexOptionAvailability,
    LivingDexOptionUnavailableReason,
)
from pokemon_red_completion.player_challenge_consequence import ChallengeConsequenceHead
from pokemon_red_completion.player_preparation_party_context import PreparationPartyWitness
from pokemon_red_completion.red_live_option_menu import (
    RedLiveOptionChoice,
    RedLiveOptionSelectionMode,
)

SOURCE = "b" * 64


def fixture(tmp_path, monkeypatch, *, child_story=False):
    options, combat, state, runtime = menu(tmp_path, monkeypatch)
    args, _ = provisional_args(tmp_path / "model", monkeypatch)
    candidates = tuple(
        replace(c, challenge=None) if b.kind is GoalKind.DEVELOP_TEAM else c
        for b, c in zip(options.bindings, options.menu.candidates, strict=True)
    )
    options = replace(
        options,
        menu=replace(options.menu, candidates=candidates),
        preparation_party_witness=PreparationPartyWitness(SOURCE, (("fixture-party", "combat"),)),
    )
    prep = next(i for i, b in enumerate(options.bindings) if b.kind is GoalKind.DEVELOP_TEAM)
    seen = []

    def select(model, observed, **kw):
        seen.append(observed)
        return RedLiveOptionChoice(
            observed,
            prep,
            RedLiveOptionSelectionMode.MODEL_GREEDY,
            tuple(
                float(i == prep) if i in observed.menu.available_indices else None
                for i in range(len(observed.bindings))
            ),
            tuple(float(i == prep) for i in range(len(observed.bindings))),
            kw["seed"],
            model.model_sha256,
        )

    monkeypatch.setattr(C, "select_red_live_option", select)

    def child(self, observed, **kw):
        kind = "unlock_access" if child_story else "develop"
        return tuple(
            float(c.features.kind.value == kind) if i in observed.available_indices else None
            for i, c in enumerate(observed.candidates)
        )

    monkeypatch.setattr(ChallengeConsequenceHead, "scores", child)
    return options, combat, prep, args["model"], progress_head("kind.develop"), seen, runtime


def choose(options, model, head, **overrides):
    kw = dict(
        objective_ref="private-combat-goal",
        seed=3,
        greedy_selection=True,
        refine_preparation=True,
        associate_unique_combat=True,
        defer_unbound_preparation=False,
        allow_singleton_parent_support=False,
        source_state_sha256=SOURCE,
    )
    kw.update(overrides)
    return C.select_branch_recovery_live_option(model, options, head, **kw)


@pytest.mark.parametrize("child_story", [False, True])
def test_complete_parent_menu_and_exact_private_association(tmp_path, monkeypatch, child_story):
    options, combat, prep, model, head, seen, runtime = fixture(
        tmp_path, monkeypatch, child_story=child_story
    )
    before = options.menu.policy_dict()
    choice = choose(options, model, head)
    receipt = choice.branch_recovery
    assert seen == [options] and seen[0] is options
    assert options.menu.policy_dict() == before
    assert receipt.parent.selected_binding is options.binding(prep)
    assert receipt.parent.options.menu.available_indices == options.menu.available_indices
    assert options.menu.candidates[prep].challenge is None
    witness = receipt.unique_combat_witness
    assert witness.combat_binding is options.binding(combat)
    assert witness.preparation_binding is options.binding(prep)
    assert witness.validate(
        receipt.parent, ("private-combat-goal",), source_state_sha256=SOURCE
    ) is options.binding(combat)
    assert all(
        c.challenge == options.menu.candidates[combat].challenge
        for c in receipt.child.options.menu.candidates
    )
    doc = receipt.document()
    assert doc["parent_model_queries"] == doc["child_model_queries"] == 1
    assert doc["parent_selected_kind"] == GoalKind.DEVELOP_TEAM.value
    assert doc["child_overrode_parent_binding"] is child_story
    assert witness.document()["parent_combat_selection"] is False
    assert "combat_binding_ref" not in str(doc)
    assert C.selected_preparation_parent(choice) is (
        None if child_story else options.binding(combat)
    )
    assert not runtime.recorder.trace


@pytest.mark.parametrize(
    "fault",
    ["second_equal_combat", "unknown_story", "out_of_scope", "unavailable", "no_party_witness"],
)
def test_ambiguous_or_unsupported_context_stays_unassociated(tmp_path, monkeypatch, fault):
    options, combat, prep, model, head, seen, runtime = fixture(tmp_path, monkeypatch)
    other = next(
        i
        for i, b in enumerate(options.bindings)
        if b.kind is GoalKind.ADVANCE_STORY and i != combat
    )
    cs = list(options.menu.candidates)
    bs = list(options.bindings)
    if fault == "second_equal_combat":
        cs[other] = replace(cs[other], challenge=cs[combat].challenge)
    elif fault == "unknown_story":
        cs[other] = replace(cs[other], challenge=None)
    elif fault == "out_of_scope":
        bs[combat] = replace(bs[combat], story_objective_ref="other-legitimate-combat")
    elif fault == "unavailable":
        cs[combat] = replace(
            cs[combat],
            availability=LivingDexOptionAvailability.UNAVAILABLE,
            unavailable_reason=LivingDexOptionUnavailableReason.TEMPORARILY_BLOCKED,
        )
    options = replace(
        options,
        bindings=tuple(bs),
        menu=replace(options.menu, candidates=tuple(cs)),
        preparation_party_witness=None
        if fault == "no_party_witness"
        else options.preparation_party_witness,
    )
    choice = choose(options, model, head)
    assert choice.branch_recovery.unique_combat_witness is None
    assert choice.branch_recovery.child is None
    assert choice.selected_binding is options.binding(prep)
    assert not runtime.recorder.trace


def test_stale_boundary_is_rejected_before_execution(tmp_path, monkeypatch):
    options, combat, prep, model, head, seen, runtime = fixture(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="exact observed preparation boundary"):
        choose(options, model, head, source_state_sha256="c" * 64)
    assert not runtime.recorder.trace


def test_equal_binding_copy_cannot_replace_private_identity(tmp_path, monkeypatch):
    options, combat, prep, model, head, seen, runtime = fixture(tmp_path, monkeypatch)
    choice = choose(options, model, head)
    receipt = choice.branch_recovery
    forged = replace(receipt.unique_combat_witness, combat_binding=replace(options.binding(combat)))
    with pytest.raises(ValueError, match="exact observed preparation boundary"):
        replace(choice, branch_recovery=replace(receipt, unique_combat_witness=forged))
    assert not runtime.recorder.trace


@pytest.mark.parametrize(
    "fault",
    ["defer_unbound_preparation", "allow_singleton_parent_support", "not_refine", "not_greedy"],
)
def test_new_mode_cannot_hide_parent_options_or_support(tmp_path, monkeypatch, fault):
    options, combat, prep, model, head, seen, runtime = fixture(tmp_path, monkeypatch)
    changes = (
        {fault: True}
        if fault in {"defer_unbound_preparation", "allow_singleton_parent_support"}
        else {"refine_preparation" if fault == "not_refine" else "greedy_selection": False}
    )
    with pytest.raises(ValueError):
        choose(options, model, head, **changes)
    assert seen == [] and not runtime.recorder.trace


def test_default_off_keeps_legacy_parent_only_semantics_and_identity(tmp_path, monkeypatch):
    options, combat, prep, model, head, seen, runtime = fixture(tmp_path, monkeypatch)
    choice = choose(options, model, head, associate_unique_combat=False)
    assert choice.branch_recovery.child is None
    assert choice.branch_recovery.unique_combat_witness is None
    assert "associate_unique_combat" not in choice.branch_recovery.document()
    old = C.branch_recovery_identity(
        model.model_sha256,
        head.model_sha256,
        "private-combat-goal",
        greedy_selection=True,
        refine_preparation=True,
    )
    assert choice.model_sha256 == old
    assert not runtime.recorder.trace


def test_missing_boundary_is_unknown_not_a_fabricated_or_stale_witness(tmp_path, monkeypatch):
    options, combat, prep, model, head, seen, runtime = fixture(tmp_path, monkeypatch)
    choice = choose(options, model, head, source_state_sha256=None)
    receipt = choice.branch_recovery
    assert receipt.unique_combat_witness is None and receipt.child is None
    assert receipt.document()["parent_model_queries"] == 1
    assert receipt.document()["child_model_queries"] == 0
    assert choice.selected_binding is options.binding(prep)
    assert not runtime.recorder.trace


def test_public_inspection_passes_a_contemporaneously_authenticated_source():
    # Structural integration regression: no guest, CLI, model or file-fixture run.
    import ast
    from pathlib import Path

    path = Path(__file__).parents[1] / "scripts/run_configured_red_player.py"
    tree = ast.parse(path.read_text())
    functions = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
    callers = [
        n
        for n in functions
        if any(
            isinstance(c, ast.Call)
            and isinstance(c.func, ast.Name)
            and c.func.id == "select_branch_recovery_live_option"
            for c in ast.walk(n)
        )
    ]
    assert len(callers) == 1
    caller = callers[0]
    call = next(
        c
        for c in ast.walk(caller)
        if isinstance(c, ast.Call)
        and isinstance(c.func, ast.Name)
        and c.func.id == "select_branch_recovery_live_option"
    )
    kw = {k.arg: k.value for k in call.keywords}
    assert ast.unparse(kw["source_state_sha256"]) == "association_source_sha256"
    guard = next(
        n
        for n in ast.walk(caller)
        if isinstance(n, ast.If)
        and ast.unparse(n.test)
        == "refinement is not None and refinement.get('associate_unique_combat', False)"
    )
    body = ast.unparse(ast.Module(body=guard.body, type_ignores=[]))
    assert "observed_state = em.save_state_bytes()" in body
    assert "association_source_sha256 = sha256(observed_state).hexdigest()" in body
    assert "observed_state != payload" in body
    assert "association_source_sha256 != context['state_sha256']" in body
    assert any(isinstance(n, ast.Raise) for n in ast.walk(guard))
    assert guard.lineno < call.lineno


@pytest.mark.parametrize("refinement", [None, {}, {"associate_unique_combat": False}])
def test_inspection_association_guard_preserves_absent_legacy_refinement(refinement):
    import ast
    from pathlib import Path

    path = Path(__file__).parents[1] / "scripts/run_configured_red_player.py"
    tree = ast.parse(path.read_text())
    guard = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.If)
        and ast.unparse(n.test)
        == "refinement is not None and refinement.get('associate_unique_combat', False)"
    )
    # Evaluate only the actual pure boolean guard, never the launcher/module.
    expression = ast.Expression(body=guard.test)
    assert (
        eval(compile(expression, "inspection_guard", "eval"), {"refinement": refinement}) is False
    )
