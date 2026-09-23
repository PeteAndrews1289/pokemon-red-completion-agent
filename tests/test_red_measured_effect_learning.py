from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest
import run_red_measured_effect_learning as learning


def rows(roots=("a", "b", "c")):
    result = []
    for root in roots:
        for family in learning.FAMILIES:
            for occupied in (0, 1):
                features = [0.] * len(learning.COMPACT_STATUS_NAMES)
                features[learning.COMPACT_STATUS_NAMES.index(f"choice.effect.{family}")] = 1.
                features[learning.COMPACT_STATUS_NAMES.index(learning.CONDITION[family])] = occupied
                result.append({"root": root, "role": "train", "family": family,
                    "capture_id": f"{root}-{family}-{occupied}",
                    "case": f"{root}-{family}-{occupied}",
                    "features": features,
                    "evidence": {"kind": "observed", "application_success": 1-occupied}})
    return result


def test_fit_is_single_fresh_call_without_held_rows_and_generalizes_condition():
    data = rows()
    fit = learning.fit_once(data, ["a", "b", "c"])
    assert fit["fits"] == 1 and fit["success"] and fit["authority_promotions"] == 0
    held = rows(("d",))
    result = learning.metrics(held, fit)
    assert result["brier"] < .1 * result["constant_brier"]
    assert result["errors_at_half"] == 0
    assert not any("duration" in n or "root" in n for n in fit["feature_names"])


@pytest.mark.parametrize("mutation", ["role", "root", "family", "class", "feature", "duplicate"])
def test_admission_rejects_heldout_or_inadequate_measured_support(monkeypatch, mutation):
    data = rows()
    if mutation == "role":
        data[0]["role"] = "holdout"
    elif mutation == "root":
        data[0]["root"] = "d"
    elif mutation == "family":
        data[0]["family"] = "disable"
    elif mutation == "class":
        data[0]["evidence"] = {"kind": "unknown", "application_success": None}
    elif mutation == "feature":
        data[1]["features"] = data[0]["features"]
    else:
        data.append(deepcopy(data[0]))
    monkeypatch.setattr(learning, "minimize", lambda *a, **k: pytest.fail("fit must not start"))
    with pytest.raises(ValueError):
        learning.fit_once(data, ["a", "b", "c"])


def traced_turn():
    before = {"turn": 0, "move": 105, "effect": 0x38, "stack": 10,
              "player_species": 1, "enemy_species": 4, "player_slot": 0,
              "enemy_slot": 0, "battle": 2, "player_hp": 50, "player_max_hp": 100}
    record = {"schema": learning.TRACE_SCHEMA, "before": before,
              "after": {**before, "player_hp": 100}}
    record["label"] = learning.effect_label(record)
    trace = {"enabled": True, "pending": None, "records": [record]}
    episode = {"decisions": [{"outcome": {"move_executed": True}, "state_before": {
        "opponent_species_id": 4, "opponent_party_position": 0, "active_party_slot": 1}}]}
    return episode, trace


def test_execution_suppression_and_unknown_are_not_negative_labels():
    ep, trace = traced_turn()
    assert learning.selected_trace_label(ep, trace, 105)["application_success"] == 1
    trace["records"] = []
    assert learning.selected_trace_label(ep, trace, 105)["kind"] == "unknown"
    ep["decisions"][0]["outcome"]["move_executed"] = False
    label = learning.selected_trace_label(ep, trace, 105)
    assert label["kind"] == "suppressed" and label["application_success"] is None


@pytest.mark.parametrize("mutation", ["label", "subject", "pending", "suppressed"])
def test_trace_integrity_and_subject_identity_rejected(mutation):
    ep, trace = traced_turn()
    if mutation == "label":
        trace["records"][0]["label"]["application_success"] = 0
    elif mutation == "subject":
        ep["decisions"][0]["state_before"]["opponent_species_id"] = 9
    elif mutation == "pending":
        trace["pending"] = {}
    else:
        ep["decisions"][0]["outcome"]["move_executed"] = False
    with pytest.raises(ValueError):
        learning.selected_trace_label(ep, trace, 105)


def test_nonfinite_fit_is_retained_as_failed_without_promotion(monkeypatch):
    monkeypatch.setattr(learning, "minimize", lambda *a, **k: SimpleNamespace(
        x=np.full(29, np.nan), success=True, nit=1, fun=np.nan, jac=np.array([np.nan]),
        message="invalid"))
    result = learning.fit_once(rows(), ["a", "b", "c"])
    assert not result["success"] and result["fits"] == 1 and result["authority_promotions"] == 0


def test_recipe_packet_keeps_four_roots_and_reserved_variant(monkeypatch):
    templates = [{"id": f"effect-crossed-{i}-balanced-{family}-{variant}-{contrast}",
                  "root": f"r{i}", "source_index": i, "role": "holdout" if i == 3 else "train",
                  "family": family, "contrast": contrast}
                 for i in range(4) for family in (*learning.FAMILIES, "disable")
                 for variant in ((2,) if i == 3 else (0, 1)) for contrast in range(4)]
    monkeypatch.setattr(learning, "crossed_recipes", lambda *a, **k: deepcopy(templates))
    monkeypatch.setattr(learning, "native_first_actor_case", lambda row, _: deepcopy(row))
    checks, cases = learning.recipes(None, [f"r{i}" for i in range(4)])
    assert len(checks) == 6 and sum(r["contrast"] == 0 for r in checks) == 4
    assert len(cases) == 42
    assert {r["root"] for r in cases if r["role"] == "train"} == {"r0", "r1", "r2"}
    assert {r["root"] for r in cases if r["role"] == "holdout"} == {"r3"}
    assert all(r["family"] != "disable" for r in cases)
