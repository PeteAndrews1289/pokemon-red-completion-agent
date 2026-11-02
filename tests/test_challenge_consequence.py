"""Synthetic contracts, never native training or gameplay evidence."""

import copy
import json
from dataclasses import replace

import numpy as np
import pytest
from test_red_player_lesson_runtime import fixture
from test_red_player_preparation_lesson import observe

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.living_dex_option_value import LivingDexOptionMenu
from pokemon_red_completion.player_challenge_consequence import (
    CONSEQUENCE_SCHEMA,
    ChallengeConsequenceHead,
    ConsequenceExample,
    fit_challenge_consequence,
)
from pokemon_red_completion.player_option_challenge import OptionChallenge
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_challenge_consequence import (
    ChallengeConsequenceSpec,
    project_consequence,
)
from pokemon_red_completion.red_native_curriculum import curriculum_projection
from pokemon_red_completion.red_player_lesson_runtime import record_native_player_lesson


def documents(tmp_path, monkeypatch):
    store, _, kwargs = fixture(tmp_path, monkeypatch, kind=GoalKind.DEVELOP_TEAM)
    pre = record_native_player_lesson(
        store,
        **kwargs,
        observe_preparation=observe,
        observe_challenge=lambda *_: OptionChallenge.from_levels(
            combat_levels=(20,), opponent_levels=(21, 24)
        ),
        preflight_only=True,
    )["declaration"]
    context, candidate = curriculum_projection(pre)
    menu = LivingDexOptionMenu(context, (candidate, replace(candidate, binding_ref="other")))
    spec = ChallengeConsequenceSpec(
        GoalKind.DEVELOP_TEAM,
        dict(kind="events", map_id=0, events=[1]),
        pre["player_lesson"]["target"],
    )
    before = dict(
        state_sha256=pre["source"]["state_sha256"],
        actions=0,
        completed_actions=0,
        frames=0,
        heals=0,
        cash=1500,
        observation=copy.deepcopy(pre["before"]),
        lesson=copy.deepcopy(pre["player_lesson"]["before"]),
        endpoint=dict(map_id=0, at=[1, 1], events=[False]),
        settled=True,
    )
    plan = dict(
        schema="pokemon.red.challenge-consequence-plan.v1",
        consequence_schema=CONSEQUENCE_SCHEMA,
        prospective=True,
        partition="train",
        source=pre["source"],
        execution={},
        spec=spec.document(),
        before=before,
        menu=menu.policy_dict(),
        selected_index=0,
        binding_ref=candidate.binding_ref,
    )
    after = copy.deepcopy(before)
    after.update(state_sha256="a" * 64, actions=100, completed_actions=100, frames=6000, heals=1)
    after["lesson"]["party"][0].update(level=22, experience=10648)
    after["observation"]["semantic_observation"]["input_ready"] = True
    training = dict(
        ordinal=0,
        kind="develop_team",
        binding_ref=candidate.binding_ref,
        before=before,
        after=after,
        interventions=[],
        error=None,
        verified=True,
        battle=None,
        cost_verified=True,
    )
    terminal = copy.deepcopy(after)
    terminal.update(
        state_sha256="b" * 64, actions=120, completed_actions=120, frames=7000, cash=750
    )
    challenge = dict(
        ordinal=1,
        kind="advance_story",
        binding_ref="challenge",
        before=copy.deepcopy(after),
        after=terminal,
        interventions=[],
        error=None,
        verified=False,
        battle="lost",
        cost_verified=True,
    )
    return plan, [training, challenge], menu


@pytest.mark.parametrize("won", [False, True])
def test_completed_dose_is_not_challenge_success(tmp_path, monkeypatch, won):
    plan, phases, menu = documents(tmp_path, monkeypatch)
    if won:
        phases[-1].update(verified=True, battle="won")
        phases[-1]["after"]["endpoint"]["events"] = [True]
    row = project_consequence(plan, phases)
    assert row.features == menu.candidate_vector(0, feature_version=7)
    assert row.outcome.attempted and row.outcome.completed is won
    assert row.outcome.actions == 120 and row.outcome.frames == 7000
    assert row.outcome.cash_debits == 750 and row.outcome.restorations == 1
    assert "red-preparation:" not in str(row.document())
    assert "map_id" not in str(row.document())
    restored = ConsequenceExample.from_document(json.loads(json.dumps(row.document())))
    assert restored == row


def test_failed_dose_is_not_observed_battle_loss(tmp_path, monkeypatch):
    plan, phases, _ = documents(tmp_path, monkeypatch)
    phases = phases[:1]
    phases[0]["verified"] = False
    phases[0]["after"]["lesson"]["party"][0].update(level=20, experience=8100)
    row = project_consequence(plan, phases)
    assert not row.outcome.attempted and not row.outcome.completed
    assert row.outcome.actions == 100 and row.outcome.restorations == 1


@pytest.mark.parametrize(
    "fault", ["interrupt", "exception", "unsettled", "cost", "partial", "unfinished", "no_battle"]
)
def test_unknown_is_censored_not_loss(tmp_path, monkeypatch, fault):
    plan, phases, _ = documents(tmp_path, monkeypatch)
    if fault == "exception":
        phases[-1]["error"] = "RuntimeError"
    elif fault == "unsettled":
        phases[-1]["after"]["settled"] = False
    elif fault == "cost":
        phases[-1]["cost_verified"] = False
    elif fault == "partial":
        phases[-1]["after"]["completed_actions"] -= 1
    elif fault == "unfinished":
        phases = phases[:1]
    elif fault == "no_battle":
        phases[-1]["battle"] = None
    row = project_consequence(plan, phases, interrupted=fault == "interrupt")
    assert row.outcome is None and row.censor_reason


@pytest.mark.parametrize(
    "fault",
    [
        "link",
        "counter_reset",
        "source",
        "intervention",
        "second_training",
        "false_win",
        "event_without_win",
        "already_done",
        "different_target",
        "development",
        "retrospective",
        "extra_challenge",
    ],
)
def test_invalid_consequence_is_rejected(tmp_path, monkeypatch, fault):
    plan, phases, _ = documents(tmp_path, monkeypatch)
    if fault == "link":
        phases[-1]["before"]["state_sha256"] = "c" * 64
    elif fault == "counter_reset":
        phases[-1]["after"]["frames"] = 1
    elif fault == "source":
        plan["source"]["state_sha256"] = "d" * 64
    elif fault == "intervention":
        phases[0]["interventions"] = ["restore_state"]
    elif fault == "second_training":
        phases[-1]["kind"] = "develop_team"
    elif fault == "false_win":
        phases[-1].update(battle="won", verified=True)
    elif fault == "event_without_win":
        phases[-1]["after"]["endpoint"]["events"] = [True]
    elif fault == "already_done":
        plan["before"]["endpoint"]["events"] = [True]
    elif fault == "different_target":
        plan["spec"]["preparation_target"]["level"] = 23
    elif fault == "development":
        plan["partition"] = "development"
    elif fault == "retrospective":
        plan["prospective"] = False
    else:
        phases.append(dict(phases[-1], ordinal=2, before=copy.deepcopy(phases[-1]["after"])))
    with pytest.raises(ValueError):
        project_consequence(plan, phases)


def test_synthetic_fit_codec_scores_and_legacy_unchanged(tmp_path, monkeypatch):
    from test_red_live_option_menu import _model

    from pokemon_red_completion.living_dex_goal_policy import DEFAULT_LIVING_DEX_GOAL_UTILITY
    from pokemon_red_completion.living_dex_option_value import (
        upgrade_option_value_model_for_preparation,
    )

    plan, phases, menu = documents(tmp_path, monkeypatch)
    loss = replace(project_consequence(plan, phases), provenance="synthetic")
    # Distinct observed synthetic example; never a fabricated unselected native label.
    win = replace(
        loss,
        declaration_sha256="f" * 64,
        outcome=replace(loss.outcome, completed=True, cash_debits=0),
    )
    baseline = upgrade_option_value_model_for_preparation(_model())
    identity, scores = baseline.model_sha256, baseline.scores(menu, DEFAULT_LIVING_DEX_GOAL_UTILITY)
    head = fit_challenge_consequence((loss, win))
    restored = ChallengeConsequenceHead.from_document(
        json.loads(json.dumps(head.document())), expected_sha256=head.model_sha256
    )
    assert restored.predict(loss.features) == head.predict(loss.features)
    assert all(np.isfinite(restored.scores(menu, challenge_refs=("private-a", "private-a"))))
    assert head.provenance == "synthetic"
    assert baseline.model_sha256 == identity
    assert baseline.scores(menu, DEFAULT_LIVING_DEX_GOAL_UTILITY) == scores
    with pytest.raises(ValueError):
        head.scores(menu, challenge_refs=("private-a", "private-b"))
    doc = head.document()
    doc["utility"][1] = 100
    with pytest.raises(ValueError):
        ChallengeConsequenceHead.from_document(doc, expected_sha256=canonical_sha256(doc))
    with pytest.raises(ValueError):
        fit_challenge_consequence((loss, loss))
    with pytest.raises(ValueError):
        fit_challenge_consequence((loss, replace(win, provenance="native_train")))


def test_synthetic_learning_prefers_useful_dose_and_skips_unnecessary_dose(tmp_path, monkeypatch):
    from pokemon_red_completion.living_dex_option_value import LivingDexOptionKind
    from pokemon_red_completion.player_challenge_consequence import ChallengeConsequence

    plan, phases, original = documents(tmp_path, monkeypatch)
    anchor = replace(project_consequence(plan, phases), provenance="synthetic")
    training = original.candidates[0]
    direct = replace(
        training,
        binding_ref="direct",
        preparation=None,
        features=replace(training.features, kind=LivingDexOptionKind.UNLOCK_ACCESS),
    )
    menus, rows = [], []
    for level in (15, 20):
        challenge = OptionChallenge.from_levels(combat_levels=(level,), opponent_levels=(18, 21))
        train = replace(
            training,
            challenge=challenge,
            preparation=replace(training.preparation, current_level=level, target_level=level + 1),
        )
        menu = LivingDexOptionMenu(original.context, (train, replace(direct, challenge=challenge)))
        menus.append(menu)
        for index in (0, 1):
            outcome = ChallengeConsequence(
                True,
                index == 0 or level == 20,
                1000 if index == 0 else 100,
                10000 if index == 0 else 1000,
                0,
                0,
                int(index == 0),
            )
            rows.append(
                replace(
                    anchor,
                    declaration_sha256=f"{len(rows) + 1:064x}",
                    features=menu.candidate_vector(index, feature_version=7),
                    outcome=outcome,
                )
            )
    head = fit_challenge_consequence(rows, ridge=0.001)
    weak, strong = [head.scores(menu, challenge_refs=("same", "same")) for menu in menus]
    assert weak[0] > weak[1]
    assert strong[1] > strong[0]
    assert head.provenance == "synthetic"  # Numerical capacity, not real-world learning proof.
