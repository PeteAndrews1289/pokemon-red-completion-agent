"""Prospective progress feedback; synthetic tests are not native TRAIN evidence."""

import copy
from dataclasses import replace

import numpy as np
import pytest
from test_challenge_consequence import documents
from test_red_post_battle_strategy import episode

from pokemon_red_completion.player_challenge_consequence import (
    PROGRESS_UTILITY,
    ChallengeConsequence,
    ChallengeConsequenceHead,
    ConsequenceExample,
    fit_challenge_consequence,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_challenge_consequence import (
    ChallengeConsequenceSpec,
    challenge_progress_from_episode,
    project_consequence,
)


def progressive(plan, phases):
    spec = replace(ChallengeConsequenceSpec.from_document(plan["spec"]), feedback_version=2)
    plan.update(schema="pokemon.red.challenge-consequence-plan.v3",
                consequence_schema="pokemon.player.challenge-consequence.v2", spec=spec.document())
    phases[-1]["challenge_episode"] = episode()
    return plan, phases


def test_progress_is_measured_from_battle_not_xp_or_success_claim(tmp_path, monkeypatch):
    plan, phases, _ = documents(tmp_path, monkeypatch)
    old = project_consequence(plan, phases)
    old_document = copy.deepcopy(old.document())
    progressive(plan, phases)
    row = project_consequence(plan, phases)
    assert row.outcome.challenge_progress == pytest.approx(0.495)
    assert not row.outcome.initial_goal_failed
    assert not row.outcome.completed and row.outcome.attempted
    assert old.document() == old_document
    assert len(old.outcome.vector()) == 7 and len(row.outcome.vector()) == 9
    assert ConsequenceExample.from_document(row.document()) == row


def test_failed_dose_is_penalized_without_invented_battle_progress(tmp_path, monkeypatch):
    plan, phases, _ = documents(tmp_path, monkeypatch)
    progressive(plan, phases)
    phases = phases[:1]
    phases[0]["verified"] = False
    phases[0]["after"]["lesson"]["party"][0].update(level=20, experience=8100)
    row = project_consequence(plan, phases)
    assert row.outcome.initial_goal_failed and row.outcome.challenge_progress == 0
    assert not row.outcome.attempted
    assert sum(w * v for w, v in zip(PROGRESS_UTILITY, row.outcome.vector(), strict=True)) < -0.5


def test_completed_dose_without_challenge_remains_censored(tmp_path, monkeypatch):
    plan, phases, _ = documents(tmp_path, monkeypatch)
    progressive(plan, phases)
    row = project_consequence(plan, phases[:1])
    assert row.outcome is None and row.censor_reason
    assert row.feedback_version == 2


@pytest.mark.parametrize("fault", ["missing", "result", "metric", "version"])
def test_unverified_or_retrospective_progress_rejected(tmp_path, monkeypatch, fault):
    plan, phases, _ = documents(tmp_path, monkeypatch)
    progressive(plan, phases)
    if fault == "missing":
        phases[-1]["challenge_episode"] = None
    elif fault == "result":
        phases[-1]["challenge_episode"]["battle_won"] = True
    elif fault == "metric":
        phases[-1]["challenge_episode"]["metrics"]["opponent_faints"] = 1
    else:
        plan["consequence_schema"] = "pokemon.player.challenge-consequence.v1"
    with pytest.raises(ValueError):
        project_consequence(plan, phases)


def test_roster_faints_do_not_double_count_last_zero_hp():
    data = episode()
    data["decisions"][0].update(referee_opponent_roster_hp_before=[100, 150],
                               referee_opponent_roster_hp_after=[100, 0], opponent_faints=1)
    data["metrics"]["opponent_faints"] = 1
    data["decisions"][0]["state_after"]["opponent_hp"] = 0
    assert challenge_progress_from_episode(data, battle="lost") == 0.5


def test_new_head_retains_legacy_labels_without_fabricated_auxiliary_targets(tmp_path, monkeypatch):
    plan, phases, _ = documents(tmp_path, monkeypatch)
    legacy = replace(project_consequence(plan, phases), provenance="synthetic")
    progressive(plan, phases)
    loss = replace(project_consequence(plan, phases), provenance="synthetic",
                   declaration_sha256="e"*64)
    win = replace(loss, declaration_sha256="f"*64, outcome=replace(
        loss.outcome, completed=True, challenge_progress=1, cash_debits=0))
    frozen = copy.deepcopy(legacy.document())
    head = fit_challenge_consequence((legacy, loss, win), feedback_version=2)
    assert head.examples == 3 and head.feedback_version == 2
    assert len(head.predict(legacy.features)) == 9
    restored = ChallengeConsequenceHead.from_document(
        head.document(), expected_sha256=head.model_sha256)
    assert np.array_equal(head.coefficients, restored.coefficients)
    assert legacy.document() == frozen
    assert canonical_sha256(legacy.document()) == canonical_sha256(frozen)
    with pytest.raises(ValueError, match="actual labels"):
        fit_challenge_consequence((legacy, loss), feedback_version=2)
    with pytest.raises(ValueError):
        fit_challenge_consequence((loss, win))


@pytest.mark.parametrize("kwargs", [
    {"challenge_progress": -0.1}, {"challenge_progress": float("nan")},
    {"initial_goal_failed": True}, {"completed": True},
])
def test_invalid_feedback_is_not_admitted(kwargs):
    values = dict(attempted=True, completed=False, actions=1, frames=1, cash_debits=0,
                  cash_credits=0, restorations=0, feedback_version=2,
                  initial_goal_failed=False, challenge_progress=0.5)
    with pytest.raises(ValueError):
        ChallengeConsequence(**(values | kwargs))
