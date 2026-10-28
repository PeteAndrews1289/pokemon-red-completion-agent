"""ROM-free native recorder regression for travel followed by a real challenge."""

from copy import deepcopy
from dataclasses import replace

import pytest
from test_native_challenge_consequence import harness, session

import pokemon_red_completion.red_challenge_consequence as consequence
from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_runtime import GoalExecutionReport
from pokemon_red_completion.living_dex_option_value import (
    upgrade_option_value_model_for_level_workload,
)
from pokemon_red_completion.provenance import canonical_sha256


def arrival_session(tmp_path, monkeypatch, *, opt_in=True, fault="win", feedback=1):
    args, state = harness(tmp_path, monkeypatch, fault=fault)
    state["arrived"] = False
    args["model"] = upgrade_option_value_model_for_level_workload(args["model"])
    args["consequence_spec"] = replace(
        args["consequence_spec"], include_challenge_arrival=opt_in, feedback_version=feedback
    )
    monkeypatch.setattr(
        consequence, "capture_story_unit",
        lambda *_: dict(map_id=0 if state["arrived"] else 1, at=[1, 1],
                       events=[state["challenge"] and fault == "win"]),
    )
    original = args["enumerate_bindings"]

    def enumerate_bindings(rt, actions, boundary):
        bindings = original(rt, actions, boundary)
        result = []
        for binding in bindings.bindings:
            if binding.kind is GoalKind.ADVANCE_STORY:
                if state["trained"] and not state["arrived"]:
                    def arrive():
                        actions.execute(MacroAction(MacroActionKind.WAIT, repeat=2))
                        state["arrived"] = True
                        return GoalExecutionReport(1, 2, {})

                    binding = replace(binding, execute=arrive,
                                      binding_ref="pokemon.red:story-travel:" + "a" * 64)
                    from pokemon_red_completion.goal_manager_runtime import GoalVerification
                    binding = replace(binding, verify=lambda _: GoalVerification.succeeded())
                elif feedback == 2:
                    execute = binding.execute

                    def battle(execute=execute):
                        from test_red_post_battle_strategy import episode
                        report = execute()
                        return replace(report, evidence={
                            "battle": {"outcome": "lost", "episode": episode()}
                        })

                    binding = replace(binding, execute=battle)
            result.append(binding)
        return replace(bindings, bindings=tuple(result),
                       opportunities=tuple(replace(b.opportunity, binding_ref=b.binding_ref)
                                           for b in result))

    args["enumerate_bindings"] = enumerate_bindings
    return session(args), args


def execute_kind(s, ordinal, kind):
    options = s.observe(ordinal)
    binding = next(b for b in options.bindings if b.kind is kind)
    binding.verify(binding.execute())


@pytest.mark.parametrize("fault,feedback", [("win", 1), (None, 1), (None, 2)])
def test_native_arrival_keeps_full_costs_until_actual_battle(tmp_path, monkeypatch, fault, feedback):
    s, args = arrival_session(tmp_path, monkeypatch, fault=fault, feedback=feedback)
    execute_kind(s, 0, GoalKind.DEVELOP_TEAM)
    execute_kind(s, 1, GoalKind.ADVANCE_STORY)
    assert not s.consequence.done
    assert s.consequence.plan["schema"] == "pokemon.red.challenge-consequence-plan.v6"
    execute_kind(s, 2, GoalKind.ADVANCE_STORY)
    assert s.consequence.done
    result = s.consequence.finish()
    row = consequence.load_challenge_consequence(
        args["store"], declaration_sha256=result["declaration_sha256"],
        result_sha256=canonical_sha256(result),
    )
    assert row.outcome.attempted and row.outcome.completed is (fault == "win")
    assert row.outcome.actions == 4 and row.outcome.frames == 8
    assert row.outcome.restorations == 1
    assert row.feature_version == 9 and row.feedback_version == feedback
    if feedback == 2:
        assert row.outcome.challenge_progress == pytest.approx(.495)
    assert not s.controller.pressed_buttons


@pytest.mark.parametrize("opt_in,reason", [(True, "challenge_not_reached_before_stop"),
                                          (False, "challenge_not_observed")])
def test_arrival_alone_is_never_a_success_label(tmp_path, monkeypatch, opt_in, reason):
    s, args = arrival_session(tmp_path, monkeypatch, opt_in=opt_in)
    execute_kind(s, 0, GoalKind.DEVELOP_TEAM)
    execute_kind(s, 1, GoalKind.ADVANCE_STORY)
    result = s.consequence.finish()
    row = consequence.load_challenge_consequence(
        args["store"], declaration_sha256=result["declaration_sha256"],
        result_sha256=canonical_sha256(result),
    )
    assert row.outcome is None and row.censor_reason == reason
    assert s.consequence.done is (not opt_in)
    if not opt_in:
        assert s.consequence.plan["schema"] == "pokemon.red.challenge-consequence-plan.v5"
        assert "include_challenge_arrival" not in s.consequence.plan["spec"]


@pytest.mark.parametrize("fault", ["binding", "destination", "party", "cash", "events", "unsettled"])
def test_forged_or_unsettled_arrival_cannot_be_skipped(tmp_path, monkeypatch, fault):
    s, _ = arrival_session(tmp_path, monkeypatch)
    execute_kind(s, 0, GoalKind.DEVELOP_TEAM)
    execute_kind(s, 1, GoalKind.ADVANCE_STORY)
    plan, phases = deepcopy(s.consequence.plan), deepcopy(s.consequence.phases)
    arrival = phases[1]
    if fault == "binding":
        arrival["binding_ref"] = "pokemon.red:story-battle:" + "a" * 64
    elif fault == "destination":
        arrival["after"]["endpoint"]["map_id"] = 2
    elif fault == "party":
        arrival["after"]["lesson"]["party"][0]["experience"] += 1
    elif fault == "cash":
        arrival["after"]["cash"] -= 1
    elif fault == "events":
        arrival["after"]["endpoint"]["events"] = [True]
    else:
        arrival["after"]["settled"] = False
    row = consequence.project_consequence(plan, phases)
    assert row.outcome is None
    assert row.censor_reason != "challenge_not_reached_before_stop"


def test_arrival_requires_explicit_boolean_and_v9_before_input(tmp_path, monkeypatch):
    s, _ = arrival_session(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="boolean"):
        replace(s.consequence.spec, include_challenge_arrival=1)
    options = s.observe(0)
    selected = next(b for b in options.bindings if b.kind is GoalKind.DEVELOP_TEAM)
    s.model_feature_version = 7
    with pytest.raises(ValueError, match="V9"):
        s.consequence.begin(options, selected, preflight_only=True)
    assert not s.recorder.trace
