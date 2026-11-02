"""ROM-free purchase/consequence contracts, not native learning evidence."""

import copy
from dataclasses import replace

import numpy as np
import pytest
from test_native_challenge_consequence import harness, session
from test_red_consequence_choice import progress_head
from test_red_live_option_menu import _binding
from test_red_post_battle_strategy import episode

import pokemon_red_completion.red_challenge_consequence as consequence
import pokemon_red_completion.red_native_player as native
import pokemon_red_completion.red_player_lesson_runtime as lesson
from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_runtime import GoalBindingSet, GoalExecutionReport
from pokemon_red_completion.goal_resource_quote import GoalResourceQuote, GoalResourceReserve
from pokemon_red_completion.observation import ItemId
from pokemon_red_completion.player_challenge_consequence import (
    ChallengeConsequenceHead,
    fit_challenge_consequence,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_consequence_choice import (
    choose_consequence_binding,
    recovery_purchase_quote,
)


def purchase_harness(tmp_path, monkeypatch, *, initial=GoalKind.RESUPPLY, resource="recovery"):
    args, state = harness(tmp_path, monkeypatch, first=GoalKind.ADVANCE_STORY)
    state["stock"] = 0
    capture = lesson.capture_player_lesson_snapshot

    def observed(rt):
        observation, snapshot = capture(rt)
        observation.raw.player_money = (1350 if state["challenge"]
                                        else 3000 - 300 * state["stock"])
        observation.raw.bag_items = (
            ((int(ItemId.POTION), state["stock"]),) if state["stock"] else ()
        )
        document = observation.public_dict()
        document["semantic_observation"]["capture_item_count"] = 0
        document["semantic_observation"]["recovery_item_count"] = state["stock"]
        observation.public_dict = lambda: copy.deepcopy(document)
        return observation, snapshot

    for module in (lesson, native, consequence):
        monkeypatch.setattr(module, "capture_player_lesson_snapshot", observed)
    old_enum = args["enumerate_bindings"]

    def bindings(rt, actions, boundary):
        old = old_enum(rt, actions, boundary)
        story = next(b for b in old.bindings if b.kind is GoalKind.ADVANCE_STORY)
        execute = story.execute

        def challenge():
            report = execute()
            return replace(report, evidence={"battle": {"outcome": "lost", "episode": episode()}})

        def purchase():
            actions.execute(MacroAction(MacroActionKind.WAIT, repeat=2))
            state["stock"] += 1
            return GoalExecutionReport(1, 2, {})

        quote = GoalResourceQuote(
            3000 - 300 * state["stock"], 300,
            (GoalResourceReserve(resource, state["stock"], state["stock"] + 1, 1),),
        )
        medicine = replace(_binding(GoalKind.RESUPPLY, binding_ref="medicine", calls=[]),
                           resource_quote=quote, execute=purchase)
        story = replace(story, execute=challenge)
        items = (medicine, story)
        return GoalBindingSet(tuple(b.opportunity for b in items), items)

    args.update(enumerate_bindings=bindings, observe_preparations=lambda *_: {},
        consequence_spec=consequence.ChallengeConsequenceSpec(
            initial, dict(kind="events", map_id=0, events=[1]), feedback_version=2,
            include_recovery_purchases=True))
    return args, state


def run_purchase_lesson(tmp_path, monkeypatch):
    args, state = purchase_harness(tmp_path, monkeypatch)
    s = session(args)
    options = s.observe(0)
    medicine = next(b for b in options.bindings if b.kind is GoalKind.RESUPPLY)
    pre = s.consequence.begin(options, medicine, preflight_only=True)
    assert pre["schema"] == "pokemon.red.challenge-consequence-plan.v4"
    assert args["emulator"].frame_count == 0 and s.consequence.plan is None
    medicine.verify(medicine.execute())
    choices = s.observe(1)
    story = next(b for b in choices.bindings if b.kind is GoalKind.ADVANCE_STORY)
    story.verify(story.execute())
    result = s.consequence.finish()
    assert result["error"] is None, result
    row = consequence.load_challenge_consequence(args["store"],
        declaration_sha256=result["declaration_sha256"], result_sha256=canonical_sha256(result))
    return args, state, s, result, row


def test_purchase_then_challenge_keeps_actual_stock_cost_and_loss(tmp_path, monkeypatch):
    args, state, s, _, row = run_purchase_lesson(tmp_path, monkeypatch)
    assert row.outcome.actions == 2 and row.outcome.frames == 4
    assert row.outcome.cash_debits == 1650
    assert row.outcome.attempted and not row.outcome.completed
    assert row.outcome.challenge_progress == pytest.approx(0.495)
    assert row.outcome.restorations == 0 and not row.outcome.initial_goal_failed
    assert state["stock"] == 1 and not args["emulator"].pressed_buttons
    assert s.consequence.plan["spec"]["include_recovery_purchases"]
    assert "recovery_purchase_question" not in str(row.document())


@pytest.mark.parametrize("fault", ["cash", "stock", "class", "party", "quote", "partition"])
def test_purchase_consequence_rejects_forged_economy_or_party(tmp_path, monkeypatch, fault):
    _, _, s, result, _ = run_purchase_lesson(tmp_path, monkeypatch)
    plan, phases = copy.deepcopy(s.consequence.plan), copy.deepcopy(result["phases"])
    after = phases[0]["after"]
    if fault == "cash":
        after["economy"]["cash"] += 1
    elif fault == "stock":
        after["economy"]["inventory"][0][1] += 1
    elif fault == "class":
        after["observation"]["semantic_observation"]["recovery_item_count"] = 0
    elif fault == "party":
        after["lesson"]["party"][0]["experience"] -= 1
    elif fault == "quote":
        plan["recovery_purchase_question"]["candidates"][0]["resource_quote"]["purchase_cost"] += 1
    else:
        plan["partition"] = "development"
    phases[1]["before"] = copy.deepcopy(after)
    with pytest.raises(ValueError):
        consequence.project_consequence(plan, phases)


def test_purchase_alone_remains_censored(tmp_path, monkeypatch):
    args, _ = purchase_harness(tmp_path, monkeypatch)
    s = session(args)
    options = s.observe(0)
    medicine = next(b for b in options.bindings if b.kind is GoalKind.RESUPPLY)
    medicine.verify(medicine.execute())
    row = consequence.project_consequence(s.consequence.plan, s.consequence.phases)
    assert row.outcome is None and row.censor_reason == "challenge_not_reached_before_stop"


def test_capture_stock_is_not_a_recovery_purchase_before_input(tmp_path, monkeypatch):
    args, _ = purchase_harness(tmp_path, monkeypatch, resource="capture")
    s = session(args)
    options = s.observe(0)
    medicine = next(b for b in options.bindings if b.kind is GoalKind.RESUPPLY)
    with pytest.raises(ValueError, match="medicine purchase"):
        s.consequence.begin(options, medicine, preflight_only=True)
    assert args["emulator"].frame_count == 0 and s.consequence.plan is None


def test_purchase_ranking_is_explicit_and_old_head_remains_strict(tmp_path, monkeypatch):
    args, _ = purchase_harness(tmp_path, monkeypatch)
    s = session(args)
    options = s.observe(0)
    challenge = next(c.challenge for c in options.menu.candidates if c.challenge is not None)
    options = replace(options, menu=replace(options.menu, candidates=tuple(
        replace(c, challenge=challenge) for c in options.menu.candidates)))
    old = progress_head("kind.resupply")
    frozen = old.document()
    with pytest.raises(ValueError, match="actual recovery quote"):
        choose_consequence_binding(options, old, challenge_refs=("same",) * len(options.bindings))
    current = replace(old, include_recovery_purchases=True)
    selected, receipt = choose_consequence_binding(
        options, current, challenge_refs=("same",) * len(options.bindings))
    assert selected.kind is GoalKind.RESUPPLY and not receipt["executed"]
    restored = ChallengeConsequenceHead.from_document(
        current.document(), expected_sha256=current.model_sha256)
    assert restored.include_recovery_purchases
    assert np.array_equal(restored.coefficients, old.coefficients)
    assert current.model_sha256 != old.model_sha256 and old.document() == frozen
    assert args["emulator"].frame_count == 0


@pytest.mark.parametrize("value", [None, 0, 1, "true"])
def test_recovery_purchase_permissions_reject_coercion(value):
    with pytest.raises(ValueError, match="explicit progress"):
        replace(progress_head(), include_recovery_purchases=value)
    with pytest.raises(ValueError, match="explicit progress"):
        consequence.ChallengeConsequenceSpec(
            GoalKind.ADVANCE_STORY, dict(kind="events", map_id=0, events=[1]),
            feedback_version=2, include_recovery_purchases=value)
    with pytest.raises(ValueError, match="explicit progress"):
        fit_challenge_consequence((), feedback_version=2, include_recovery_purchases=value)


def test_legacy_contract_cannot_acquire_purchase_authority():
    with pytest.raises(ValueError, match="explicit progress"):
        consequence.ChallengeConsequenceSpec(GoalKind.RESUPPLY,
            dict(kind="events", map_id=0, events=[1]), include_recovery_purchases=True)
    assert not recovery_purchase_quote(GoalResourceQuote(100, 0, (), expected_income=50))
    assert not recovery_purchase_quote(GoalResourceQuote(0, 0, (),
        available_recovery_units=2, maximum_recovery_consumption=1))
