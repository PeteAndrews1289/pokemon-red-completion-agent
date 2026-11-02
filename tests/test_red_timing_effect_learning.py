from copy import deepcopy
from types import SimpleNamespace

import pytest
import run_red_timing_effect_learning as timing


def rows(roots=("a", "b", "c"), *, role="train"):
    result = []
    names = timing.measured.COMPACT_STATUS_NAMES
    for root in roots:
        for family in timing.measured.FAMILIES:
            for order in timing.ORDERS:
                for condition in (0, 1):
                    features = [0.] * len(names)
                    features[names.index(f"choice.effect.{family}")] = 1.
                    features[names.index(timing.measured.CONDITION[family])] = condition
                    features[timing.SPEED] = .3 if order == "actor_first" else -.3
                    success = int(not condition or
                                  (family != "confusion" and order == "opponent_first"))
                    key = f"{root}:{family}:{order}:{condition}"
                    result.append({"root": root, "role": role, "family": family,
                        "case": key, "capture_id": key, "features": features,
                        "evidence": {"kind": "observed", "application_success": success},
                        "timing": {"order": order, "visible_speed_margin": features[timing.SPEED],
                                   "damage_before_effect": order == "opponent_first"}})
    return result


def test_single_fit_learns_timing_without_using_label_side_evidence():
    data = rows()
    fit = timing.fit_once(data, ["a", "b", "c"])
    assert fit["fits"] == 1 and fit["success"]
    assert len(fit["weights"]) == 29
    assert "damage_before_effect" not in fit["feature_names"]
    evaluation = timing.evaluate(rows(("d",), role="holdout"), ["d"], fit)
    assert evaluation["diagnostic_pass"]
    assert evaluation["overall"]["errors_at_half"] == 0
    assert evaluation["support"]["observed_cells"] == 12


@pytest.mark.parametrize("mutation", ["cell", "label", "margin", "order", "damage", "duplicate",
                                      "role", "root", "unknown"])
def test_bad_support_stops_before_fit(monkeypatch, mutation):
    data = rows()
    if mutation == "cell":
        data.pop()
    elif mutation == "label":
        for row in data:
            row["evidence"]["application_success"] = 0
    elif mutation == "margin":
        data[0]["features"][timing.SPEED] = 0.
    elif mutation == "order":
        data[0]["timing"]["order"] = "opponent_first"
    elif mutation == "damage":
        for row in data:
            row["timing"]["damage_before_effect"] = False
    elif mutation == "duplicate":
        data.append(deepcopy(data[0]))
    elif mutation == "role":
        data[0]["role"] = "holdout"
    elif mutation == "root":
        data[0]["root"] = "d"
    else:
        data[0]["evidence"] = {"kind": "unknown", "application_success": None}
    monkeypatch.setattr(timing.measured, "minimize", lambda *a, **k: pytest.fail("fit started"))
    with pytest.raises(ValueError):
        timing.fit_once(data, ["a", "b", "c"])


def test_observed_native_speed_and_hp_are_checked():
    row = rows()[0]
    recipe = {"family": row["family"], "order": "actor_first", "planned_speed_margin": .3,
              "practice": {"actor_hp": 75}}
    episode = {"decisions": [{"observation": {"features": {"party": {"lead": {"hp": 75}}}}}]}
    trace = {"records": [{"before": {"turn": 0, "move": 105, "player_hp": 75}}]}
    result = timing.timing_evidence(row, recipe, episode, trace)
    assert not result["damage_before_effect"] and result["effect_entry_hp"] == 75
    recipe["planned_speed_margin"] = .4
    with pytest.raises(ValueError, match="speed"):
        timing.timing_evidence(row, recipe, episode, trace)
    recipe["planned_speed_margin"] = .3
    recipe["practice"]["actor_hp"] = 100
    with pytest.raises(ValueError, match="HP"):
        timing.timing_evidence(row, recipe, episode, trace)


def test_unknown_effect_does_not_manufacture_timing_damage():
    row = rows()[0]
    recipe = {"family": row["family"], "order": "actor_first", "planned_speed_margin": .3,
              "practice": {"actor_hp": 75}}
    ep = {"decisions": [{"observation": {"features": {"party": {"lead": {"hp": 75}}}}}]}
    result = timing.timing_evidence(row, recipe, ep, {"records": []})
    assert result["effect_entry_hp"] is None and not result["damage_before_effect"]


def test_reserved_role_and_root_cannot_mix_with_fitting():
    fit = timing.fit_once(rows(), ["a", "b", "c"])
    with pytest.raises(ValueError, match="disjoint"):
        timing.evaluate(rows(("d",)), ["d"], fit)
    with pytest.raises(ValueError, match="disjoint"):
        timing.evaluate(rows(("a",), role="holdout"), ["a"], fit)


def test_poor_frozen_predictor_fails_without_refit():
    fit = {"weights": [0.] * 29, "train_prevalence": .5, "train_roots": ["a", "b", "c"]}
    result = timing.evaluate(rows(("d",), role="holdout"), ["d"], fit)
    assert not result["diagnostic_pass"] and result["overall"]["brier"] == pytest.approx(.25)


def test_native_constructor_uses_ordinary_moves_and_never_custom_stats():
    class Species:
        def __init__(self, species):
            self.national_number = species
            self.speed = {1: 50, 2: 30, 3: 70}[species]

        def neutral_stats(self, level):
            return SimpleNamespace(speed=self.speed, max_hp=100, attack=30, defense=50, special=50)

        trainer_stats = neutral_stats

        def teachable_moves_at_level(self, level):
            return (1, 33, 98, 120)  # ordinary, inaccurate, priority, exploding

    cartridge = SimpleNamespace(species_ids=(1, 2, 3), species=Species)
    template = {"id": "effect-crossed-0-balanced-rest-0-0", "family": "rest", "contrast": 0,
                "conditions": {"player_status": "none"}, "practice": {
                    "actor_species_ref": "pokemon.red.gb.us.rev0:species:001", "actor_level": 32}}
    original = deepcopy(template)
    for order in timing.ORDERS:
        row = timing.timing_case(template, cartridge, order)
        assert (row["planned_speed_margin"] > 0) == (order == "actor_first")
        assert row["practice"]["opponent_moves"][0]["move_ref"].endswith(":001")
        assert row["conditions"]["player_status"] == "burn"
        assert not any("stats" in key for key in row["practice"])
    assert template == original
    cartridge.species_ids = (1,)
    with pytest.raises(ValueError, match="no prospective"):
        timing.timing_case(template, cartridge, "actor_first")


def test_packet_has_72_fit_and_12_untouched_reserved_cases(monkeypatch):
    templates = [{"id": f"crossed-{i}-{family}-{v}-{c}", "family": family, "contrast": c,
                  "source_index": i, "root": str(i), "role": "holdout" if i == 3 else "train"}
                 for i in range(4) for family in (*timing.measured.FAMILIES, "disable")
                 for v in ((2,) if i == 3 else (0, 1)) for c in range(4)]
    monkeypatch.setattr(timing, "crossed_recipes", lambda *a, **k: templates)
    monkeypatch.setattr(timing, "timing_case", lambda r, _, o: {**r, "id": r["id"]+o, "order": o})
    result = timing.recipes(None, [str(i) for i in range(4)])
    assert len(result) == 84 and sum(r["role"] == "train" for r in result) == 72
    assert {r["root"] for r in result if r["role"] == "holdout"} == {"3"}
