"""ROM-free recorder qualification on the real continuous execution seam."""

import json
from dataclasses import replace

import pytest
from test_red_live_option_menu import _binding
from test_red_native_player import setup

import pokemon_red_completion.red_challenge_consequence as consequence
import pokemon_red_completion.red_native_player as native
import pokemon_red_completion.red_player_lesson_runtime as lesson
from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.goal_manager import GoalFailureReason, GoalKind
from pokemon_red_completion.goal_manager_runtime import (
    GoalBindingSet,
    GoalExecutionReport,
    GoalVerification,
)
from pokemon_red_completion.living_dex_option_value import (
    upgrade_option_value_model_for_preparation,
)
from pokemon_red_completion.player_option_challenge import OptionChallenge
from pokemon_red_completion.player_option_preparation import OptionPreparation
from pokemon_red_completion.provenance import canonical_sha256


def harness(tmp_path, monkeypatch, *, fault=None, first=GoalKind.DEVELOP_TEAM):
    args, _ = setup(tmp_path, monkeypatch)
    state = dict(trained=False, challenge=False)
    capture = lesson.capture_player_lesson_snapshot

    def observed(rt):
        observation, snapshot = capture(rt)
        if state["trained"]:
            snapshot["party"][0].update(level=22, experience=10648)
        if state["challenge"] and fault != "win":
            observation.raw.player_money = 1500
        return observation, snapshot

    monkeypatch.setattr(lesson, "capture_player_lesson_snapshot", observed)
    monkeypatch.setattr(native, "capture_player_lesson_snapshot", observed)
    monkeypatch.setattr(consequence, "capture_player_lesson_snapshot", observed)
    monkeypatch.setattr(
        consequence,
        "capture_story_unit",
        lambda *_: dict(map_id=0, at=[1, 1], events=[state["challenge"] and fault == "win"]),
    )

    def bindings(rt, actions, _boundary):
        def restore():
            actions.execute(MacroAction(MacroActionKind.WAIT, repeat=2))
            return GoalExecutionReport(1, 2, {})

        nurse = replace(
            _binding(GoalKind.RESTORE_TEAM, binding_ref="nurse", calls=[]), execute=restore
        )

        def train():
            a, f = actions.actions_executed, rt.emulator.frame_count
            actions.execute_restoration(nurse)
            actions.execute(MacroAction(MacroActionKind.WAIT, repeat=2))
            if fault == "exception":
                raise RuntimeError("retained interrupted dose")
            state["trained"] = fault != "dose_failed"
            return GoalExecutionReport(
                actions.actions_executed - a, rt.emulator.frame_count - f, {}
            )

        def challenge():
            actions.execute(MacroAction(MacroActionKind.WAIT, repeat=2))
            state["challenge"] = True
            return GoalExecutionReport(
                1, 2, {"battle": {"outcome": "won" if fault == "win" else "lost"}}
            )

        train_binding = replace(
            _binding(GoalKind.DEVELOP_TEAM, binding_ref="train", calls=[]),
            execute=train,
            verify=lambda _: (
                GoalVerification.succeeded()
                if state["trained"]
                else GoalVerification.failed(GoalFailureReason.RECOVERY_REQUIRED)
            ),
        )
        story = replace(
            _binding(GoalKind.ADVANCE_STORY, binding_ref="challenge", calls=[]),
            execute=challenge,
            verify=lambda _: (
                GoalVerification.succeeded()
                if fault == "win"
                else GoalVerification.failed(GoalFailureReason.RESOURCE_LOST)
            ),
        )
        items = (train_binding, story)
        return GoalBindingSet(tuple(b.opportunity for b in items), items)

    refs = args["combat_specimen_refs"]
    preview = OptionChallenge.from_levels(combat_levels=(20,), opponent_levels=(21, 24))
    args.update(
        model=upgrade_option_value_model_for_preparation(args["model"]),
        enumerate_bindings=bindings,
        observe_challenges=lambda rt, bs, *_: {b.binding_ref: preview for b in bs.bindings},
        observe_preparations=lambda rt, bs, *_: {
            "train": OptionPreparation(
                22 if state["trained"] else 20,
                24 if state["trained"] else 22,
                2648,
                20 / 60,
                None,
                True,
                False,
                36,
            )
        },
        limits=replace(args["limits"], actions=20, frames=100, decisions=4),
        consequence_spec=consequence.ChallengeConsequenceSpec(
            first,
            dict(kind="events", map_id=0, events=[1]),
            dict(specimen_ref=refs[0], level=22) if first is GoalKind.DEVELOP_TEAM else None,
        ),
    )
    return args, state


def session(args):
    return native.NativePlayerSession(
        **{k: v for k, v in args.items() if k not in {"model", "seed", "run_id", "arm_id"}},
        model_feature_version=args["model"].feature_version,
        execution=native.NativeExecutionIdentity(
            args["run_id"], args["arm_id"], args["model"].model_sha256, args["seed"]
        ),
    )


@pytest.mark.parametrize("fault", [None, "win", "dose_failed", "exception"])
def test_same_continuous_port_retains_preparation_heal_and_challenge(tmp_path, monkeypatch, fault):
    args, state = harness(tmp_path, monkeypatch, fault=fault)
    s = session(args)
    options = s.observe(0)
    selected = next(b for b in options.bindings if b.kind is GoalKind.DEVELOP_TEAM)
    pre = s.consequence.begin(options, selected, preflight_only=True)
    assert s.consequence.plan is None and args["emulator"].frame_count == 0
    assert args["store"].find_sealed_record("rcc-plan-" + canonical_sha256(pre)) is None
    if fault == "exception":
        with pytest.raises(RuntimeError):
            selected.execute()
    else:
        selected.verify(selected.execute())
        if fault != "dose_failed":
            choices = s.observe(1)
            challenge = next(b for b in choices.bindings if b.kind is GoalKind.ADVANCE_STORY)
            challenge.verify(challenge.execute())
    assert s.consequence.done
    result = s.consequence.finish()
    assert result["error"] is None
    row = consequence.load_challenge_consequence(
        args["store"],
        declaration_sha256=result["declaration_sha256"],
        result_sha256=canonical_sha256(result),
    )
    if fault == "exception":
        assert row.outcome is None and row.censor_reason
        assert result["phases"][0]["after"]["actions"] == 2
    else:
        assert row.outcome.actions == (2 if fault == "dose_failed" else 3)
        assert row.outcome.frames == (4 if fault == "dose_failed" else 6)
        assert row.outcome.restorations == 1
        assert row.outcome.attempted is (fault != "dose_failed")
        assert row.outcome.completed is (fault == "win")
    assert s.heals == s.support_restorations == 1
    assert len(list(args["output"].glob("restoration-*/result.json"))) == 1
    assert not args["emulator"].pressed_buttons
    assert state["challenge"] is (fault not in {"exception", "dose_failed"})
    with pytest.raises(ValueError):
        s.consequence.begin(options, selected)
    if fault is None:
        # A sealed-looking row with invented costs still cannot bypass the native trace.
        forged = json.loads(json.dumps(result))
        forged["phases"][-1]["after"]["frames"] += 1
        forged["row"] = consequence.project_consequence(
            s.consequence.plan, forged["phases"]
        ).document()
        digest = canonical_sha256(forged)
        args["store"].publish_sealed_record(
            "rcc-result-" + digest, kind="red_challenge_consequence_result", record=forged
        )
        with pytest.raises(ValueError, match="sealed native actions"):
            consequence.load_challenge_consequence(
                args["store"], declaration_sha256=result["declaration_sha256"], result_sha256=digest
            )

        truncated = json.loads(json.dumps(result))
        truncated["phases"] = truncated["phases"][:1]
        truncated["phases"][0]["verified"] = False
        truncated["row"] = consequence.project_consequence(
            s.consequence.plan, truncated["phases"]
        ).document()
        digest = canonical_sha256(truncated)
        args["store"].publish_sealed_record(
            "rcc-result-" + digest, kind="red_challenge_consequence_result", record=truncated
        )
        with pytest.raises(ValueError, match="omits a later native action"):
            consequence.load_challenge_consequence(
                args["store"], declaration_sha256=result["declaration_sha256"], result_sha256=digest
            )


def test_native_runner_unchanged_without_head_and_stops_after_one_challenge(tmp_path, monkeypatch):
    args, _ = harness(tmp_path, monkeypatch, first=GoalKind.ADVANCE_STORY, fault="win")
    # Make the model select the story candidate; no production score override.
    model = args["model"]
    from pokemon_red_completion.living_dex_option_value import option_feature_names

    coefficients = model.coefficients.copy()
    coefficients[option_feature_names(7).index("kind.unlock_access"), 0] = 100
    args["model"] = replace(model, coefficients=coefficients)
    result = native.run_native_continuous_player(**args)
    assert result["executed_decisions"] == 1
    assert result["stop_reason"] == "declared_consequence_complete"
    recorded = json.loads((args["output"] / "consequence-result.json").read_text())
    assert recorded["row"]["outcome"]["completed"]
    assert recorded["row"]["outcome"]["actions"] == 1


def test_native_progress_version_uses_returned_episode_and_keeps_legacy_unchanged(
    tmp_path, monkeypatch,
):
    from test_red_post_battle_strategy import episode

    args, _ = harness(tmp_path, monkeypatch)
    args["consequence_spec"] = replace(args["consequence_spec"], feedback_version=2)
    old_enum = args["enumerate_bindings"]

    def enumeration(*arguments):
        bs = old_enum(*arguments)
        items = []
        for binding in bs.bindings:
            if binding.kind is GoalKind.ADVANCE_STORY:
                execute = binding.execute

                def challenge(execute=execute):
                    report = execute()
                    return replace(report, evidence={
                        "battle": {"outcome": "lost", "episode": episode()}})

                binding = replace(binding, execute=challenge)
            items.append(binding)
        return replace(bs, bindings=tuple(items))

    args["enumerate_bindings"] = enumeration
    s = session(args)
    options = s.observe(0)
    train = next(b for b in options.bindings if b.kind is GoalKind.DEVELOP_TEAM)
    train.verify(train.execute())
    options = s.observe(1)
    story = next(b for b in options.bindings if b.kind is GoalKind.ADVANCE_STORY)
    story.verify(story.execute())
    result = s.consequence.finish()
    row = consequence.load_challenge_consequence(
        args["store"], declaration_sha256=result["declaration_sha256"],
        result_sha256=canonical_sha256(result))
    assert row.feedback_version == 2
    assert row.outcome.challenge_progress == pytest.approx(0.495)
    assert not row.outcome.initial_goal_failed and row.outcome.attempted
    assert not row.outcome.completed
    assert s.consequence.plan["schema"] == "pokemon.red.challenge-consequence-plan.v3"


@pytest.mark.parametrize("fault", ["wrong_initial", "old_model", "development", "already_complete"])
def test_consequence_rejects_before_input(tmp_path, monkeypatch, fault):
    args, state = harness(tmp_path, monkeypatch, fault="win")
    if fault == "old_model":
        from test_red_live_option_menu import _model

        args["model"] = _model()
    if fault == "development":
        args["source"] = dict(args["source"], partition="development")
    if fault in {"old_model", "development"}:
        with pytest.raises(ValueError):
            session(args)
    else:
        s = session(args)
        options = s.observe(0)
        kind = GoalKind.ADVANCE_STORY if fault == "wrong_initial" else GoalKind.DEVELOP_TEAM
        selected = next(b for b in options.bindings if b.kind is kind)
        if fault == "already_complete":
            state["challenge"] = True
        with pytest.raises(ValueError):
            selected.execute()
    assert args["emulator"].frame_count == 0
