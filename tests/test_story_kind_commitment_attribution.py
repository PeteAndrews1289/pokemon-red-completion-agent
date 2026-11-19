"""Exercise the real goal loop: support attribution must not leak to the next choice."""
import json
from dataclasses import replace

import pytest
from test_recurrence_parent_exploration import observed_menu
from test_red_continuous_player import facts
from test_story_branch_value import _parent

import pokemon_red_completion.red_autonomous_player as runner
from pokemon_red_completion import red_story_kind_commitment as kc
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_runtime import GoalExecutionReport


@pytest.mark.parametrize("apply", [False, True])
def test_commitment_override_is_support_and_next_real_choice_remains_eligible(tmp_path, monkeypatch, apply):
    state = {"n": 0}
    model, original = observed_menu(seen=False)
    carrier = kc.StoryKindCommitmentCarrier()
    carrier.current = kc.StoryKindCommitment("private-travel-goal")
    calls = []

    def execute(kind):
        calls.append(kind)
        state["n"] += 1
        return GoalExecutionReport(1, 10, {})

    def observe(_):
        return replace(original, bindings=tuple(
            replace(b, execute=lambda kind=b.kind: execute(kind)) for b in original.bindings))

    def select(_model, options, **_):
        ref = next(b.binding_ref for b in options.bindings if b.kind is GoalKind.ACQUIRE_SPECIES)
        return _parent(options, ref)

    monkeypatch.setattr(runner, "select_red_live_option", select)
    monkeypatch.setattr(kc, "party_fit", lambda _: apply and state["n"] == 0)
    result = runner.run_autonomous_options(
        model=model, output=tmp_path / "run", seed=1, maximum_decisions=2,
        snapshot=lambda: runner.AutonomousSnapshot(str(state["n"]).encode(), dict(facts(state["n"]), cash=5000), True),
        observe=observe, provenance={"source": {"partition": "development"}},
        continuous_player=True, maximum_cash_spent=None,
        story_milestone_commitment=True, story_kind_commitment=True,
        story_kind_commitment_carrier=carrier)
    assert result["executed_decisions"] == result["successful_decisions"] == 2
    assert result["model_decisions"] == (1 if apply else 2)
    assert result["support_decisions"] == int(apply)
    first, second = result["outcomes"]
    assert first["learning_eligible"] is (not apply)
    assert first["support_role"] == ("deterministic_story_continuation" if apply else None)
    assert second["learning_eligible"] is True and second["support_role"] is None
    assert calls == ([GoalKind.ADVANCE_STORY, GoalKind.ACQUIRE_SPECIES] if apply else [GoalKind.ACQUIRE_SPECIES] * 2)
    assert first["terminal_state_sha256"] == second["before_state_sha256"]
    assert (tmp_path / "run/step-001/terminal.state").read_bytes() == b"2"
    receipt = json.loads((tmp_path / "run/step-000/story-kind-commitment.json").read_text())
    assert receipt["overridden"] is apply
