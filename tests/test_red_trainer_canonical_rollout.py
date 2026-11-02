from types import SimpleNamespace

import pytest
import run_red_trainer_canonical_rollout as rollout


def rows():
    return [{"case": i, "arm": arm, "episode": {
        "stop_reason": "battle_won", "battle_won": True, "decision_count": 10,
        "teacher_queries": 0, "memory_write_actions": 0, "frames_executed": 1000,
        "metrics": {"invalid_action_failures": 0, "party_faints": 1,
                    "party_hp_lost": 20 if arm == "J" else 10, "party_pp_spent": 5},
        "action_counts": {"voluntary_switch": 2, "forced_switch": 1}}}
        for i in range(8) for arm in ("J", "K")]


@pytest.fixture(autouse=True)
def score(monkeypatch):
    monkeypatch.setattr(rollout, "score_trainer_practice_episode", lambda e: SimpleNamespace(
        value=10 - e["metrics"]["party_hp_lost"] / 100))


def test_cost_gain_can_pass_without_natural_or_production_claim():
    result = rollout.summarize(rows())
    assert result["train_rollout_passed"]
    assert result["totals"]["K"]["wins"] == 8
    assert result["totals"]["K"]["hp_lost"] == 80
    assert not result["natural_qualified"]
    assert result["authority_promotions"] == result["fits"] == 0
    assert result["independent_evaluation_origins"] == 0


def test_no_gain_is_rejected():
    source = rows()
    for row in source:
        row["episode"]["metrics"]["party_hp_lost"] = 20
    assert not rollout.summarize(source)["train_rollout_passed"]


def test_normal_loss_is_retained_and_win_regression_rejects():
    source = rows()
    source[-1]["episode"].update(stop_reason="party_defeated", battle_won=False)
    result = rollout.summarize(source)
    assert result["totals"]["K"]["losses"] == 1
    assert not result["train_rollout_passed"]


@pytest.mark.parametrize("bad", ["missing", "duplicate", "nonterminal", "invalid",
                                "teacher", "write"])
def test_incomplete_or_invalid_cells_cannot_pass(bad):
    source = rows()
    if bad == "missing":
        source.pop()
    elif bad == "duplicate":
        source[-1] = source[0]
    elif bad == "nonterminal":
        source[0]["episode"]["stop_reason"] = "decision_budget"
    elif bad == "invalid":
        source[0]["episode"]["metrics"]["invalid_action_failures"] = 1
    elif bad == "teacher":
        source[0]["episode"]["teacher_queries"] = 1
    else:
        source[0]["episode"]["memory_write_actions"] = 1
    with pytest.raises(ValueError):
        rollout.summarize(source)
