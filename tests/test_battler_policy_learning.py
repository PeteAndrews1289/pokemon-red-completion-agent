from copy import deepcopy

import pytest
from capture_fresh_red_brock_development import check_independence
from fit_red_trainer_learner_continuation import learning_checks, retention_limits
from run_red_trainer_learning_probe import learning_summary

from pokemon_red_completion.observation import PokemonRedStateReader


def test_provenance_only_party_original_trainer_ids():
    class Memory:
        values = {0xD163: 2, 0xD177: 0xAB, 0xD178: 0xCD, 0xD1A3: 0x12, 0xD1A4: 0x34}

        def read_u8(self, address):
            return self.values.get(int(address), 0)

    memory = Memory()
    assert PokemonRedStateReader(memory).read_party_original_trainer_ids() == (0xABCD, 0x1234)
    memory.values[0xD163] = 7
    with pytest.raises(ValueError, match="party count"):
        PokemonRedStateReader(memory).read_party_original_trainer_ids()


def test_natural_independence_cannot_be_created_by_renaming_snapshots():
    a = {"origin_state_sha256": "aaa", "first_party_ot_id": 10, "root_lineage_id": "root-a"}
    b = {"origin_state_sha256": "bbb", "first_party_ot_id": 20, "root_lineage_id": "root-b"}
    check_independence([a, b])
    for key in a:
        with pytest.raises(ValueError, match="origins"):
            check_independence([a, {**b, key: a[key]}])


def test_policy_learning_keeps_old_numeric_limits_and_requires_real_improvement():
    before = {
        group: {
            head: {"model_mean_train_regret": 0.03}
            for head in ("move", "switch", "composed_action")
        }
        for group in ("original44", "retained52", "terminal128", "new80", "prior48", "late90")
    }
    limits = retention_limits(before)
    assert limits["original44", "move"] == 0.0554
    assert limits["retained52", "move"] == 0.0648
    assert limits["retained52", "composed_action"] == 0.1609
    new_before = {"composed_action": {"model_mean_train_regret": 1.0}}
    new_after = {"composed_action": {"model_mean_train_regret": 0.5}}
    assert all(learning_checks(new_before, new_after, before, limits).values())
    assert not all(learning_checks(new_before, new_before, before, limits).values())
    bad = deepcopy(before)
    bad["late90"]["switch"]["model_mean_train_regret"] = 0.04
    assert not all(learning_checks(new_before, new_after, bad, limits).values())


def test_learning_accepts_losses_but_not_ties_duplicates_or_assistance():
    rows = [
        {
            "case": i,
            "arm": arm,
            "battle_won": i < (12 if arm == "candidate" else 8),
            "stop_reason": "battle_won"
            if i < (12 if arm == "candidate" else 8)
            else "party_defeated",
            "teacher_queries": 0,
            "memory_write_actions": 0,
            "decision_count": 10,
            "metrics": {"party_faints": 0, "party_hp_lost": 20, "invalid_action_failures": 0},
        }
        for i in range(24)
        for arm in ("frozen", "candidate")
    ]
    result = learning_summary(rows)
    assert result["learning_signal_observed"]
    assert result["totals"]["candidate"]["wins"] == 12
    assert result["candidate_only_wins"] == 4
    assert not result["final_player_ready"]
    bad = deepcopy(rows)
    bad[1]["teacher_queries"] = 1
    assert not learning_summary(bad)["learning_signal_observed"]
    with pytest.raises(ValueError, match="exactly one"):
        learning_summary(rows[:-1] + [rows[0]])
    for row in rows:
        row["battle_won"] = row["case"] < 8
        row["stop_reason"] = "battle_won" if row["battle_won"] else "party_defeated"
    assert not learning_summary(rows)["learning_signal_observed"]


def test_natural_admission_dispatches_policy_receipt_without_legacy_relabel(tmp_path, monkeypatch):
    import json

    import fit_red_trainer_learner_continuation as policy_fit
    from run_red_trainer_natural_comparison import qualified_fit_receipt

    (tmp_path / "plan.json").write_text(json.dumps({"policy_id": "frozen-learner"}))
    (tmp_path / "result.json").write_text("{}")
    expected = {"qualification_tier": "independent_root_train", "final_player_ready": False}
    monkeypatch.setattr(
        policy_fit,
        "qualified_policy_fit_receipt",
        lambda path: expected if path == tmp_path else None,
    )
    assert qualified_fit_receipt(tmp_path) == expected


def test_policy_fit_receipt_rejects_unqualified_or_unknown_continuation(tmp_path):
    import json

    from fit_red_trainer_learner_continuation import qualified_policy_fit_receipt

    (tmp_path / "plan.json").write_text(json.dumps({"policy_id": "teacher"}))
    (tmp_path / "result.json").write_text("{}")
    with pytest.raises(ValueError, match="declared"):
        qualified_policy_fit_receipt(tmp_path)
