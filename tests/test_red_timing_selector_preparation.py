from copy import deepcopy
from types import SimpleNamespace

import pytest
import run_red_timing_selector_preparation as preparation


def inventory():
    cells = {}
    for family, condition in preparation.CELLS:
        cells[(family, condition)] = [{"capture_id": f"{family}-{condition}-{i}",
            "manifest_sha256": f"manifest-{family}-{condition}-{i}",
            "state_sha256": f"state-{family}-{condition}-{i}",
            "family": family, "asleep": False} for i in range(4)]
    sleepers = [{"capture_id": f"sleeper-{i}", "manifest_sha256": f"manifest-sleeper-{i}",
                 "state_sha256": f"state-sleeper-{i}", "family": "rest", "asleep": True}
                for i in range(4)]
    return cells, sleepers


def test_selection_excludes_manifest_state_and_capture_identity_without_mutation():
    cells, sleepers = inventory()
    original = deepcopy(cells)
    consumed = [cells[("heal", 1)][0], cells[("confusion", 0)][0], sleepers[0]]
    # Different manifests or names cannot re-admit an identical saved game.
    cells[("heal", 1)][1]["state_sha256"] = consumed[0]["state_sha256"]
    selected, coverage = preparation.select_unused(cells, sleepers, consumed)
    assert len(selected) == 12 and set(coverage.values()) == {2}
    for key in ("capture_id", "manifest_sha256", "state_sha256"):
        assert not {r[key] for r in selected} & {r[key] for r in consumed}
        assert len({r[key] for r in selected}) == len(selected)
    assert "id" not in cells[("confusion", 0)][0]
    assert cells[("confusion", 0)] == original[("confusion", 0)]


def test_thin_cells_remain_represented_without_replaying_consumed_states():
    cells, sleepers = inventory()
    for key in (("heal", 1), ("confusion", 0)):
        cells[key] = cells[key][:1]
    chosen, coverage = preparation.select_unused(cells, sleepers, [])
    assert len(chosen) == 10 and sum(not r["asleep"] for r in chosen) == 8
    assert coverage["heal:1"] == coverage["confusion:0"] == 1


@pytest.mark.parametrize("change", ["missing", "too_few", "duplicate_state"])
def test_insufficient_coverage_fails_without_replacement(change):
    cells, sleepers = inventory()
    if change == "missing":
        cells[("heal", 1)] = []
    elif change == "too_few":
        cells = {k: v[:1] for k, v in cells.items()}
    else:
        for pool in cells.values():
            for row in pool:
                row["state_sha256"] = "same-state"
    with pytest.raises(ValueError):
        preparation.select_unused(cells, sleepers, [])


def test_selection_uses_identity_not_scores_or_outcomes():
    cells, sleepers = inventory()
    a = preparation.select_unused(cells, sleepers, [])[0]
    for pool in [*cells.values(), sleepers]:
        pool.reverse()
        for i, row in enumerate(pool):
            row.update(probability=i/4, application_success=i % 2)
    b = preparation.select_unused(cells, sleepers, [])[0]
    assert [r["capture_id"] for r in a] == [r["capture_id"] for r in b]


def qualification():
    names = preparation.combined.COMPACT_STATUS_NAMES
    rows = []
    for family, condition in preparation.CELLS:
        features = [0.] * len(names)
        name = "choice.already_confused" if family == "confusion" else "choice.heal_full_hp"
        features[names.index(name)] = condition
        rows.append({"family": family, "features": features, "asleep_before_choice": False,
                     "evidence": {"kind": "observed", "application_success": 1-condition}})
    return {"rows": rows}


def test_unknown_and_suppressed_labels_cannot_satisfy_observed_cell_gate():
    q = qualification()
    assert preparation.require_observed_cells(q)["passed"]
    q["rows"][0]["evidence"] = {"kind": "unknown", "application_success": None}
    assert not preparation.require_observed_cells(q)["passed"]
    q = qualification()
    q["rows"][0]["asleep_before_choice"] = True
    assert not preparation.require_observed_cells(q)["passed"]


def test_primers_are_prospective_heal_variants_on_two_train_roots(monkeypatch):
    rows = [{"id": f"crossed-{i}-balanced-heal-{i}-1", "family": "heal",
             "contrast": 1, "source_index": i, "root": str(i)} for i in (0, 1)]
    monkeypatch.setattr(preparation, "crossed_recipes", lambda *a, **k: rows)
    monkeypatch.setattr(preparation, "timing_case", lambda r, c, order: {**r, "order": order})
    result = preparation.primer_recipes(None, ["0", "1", "2", "3"])
    assert len(result) == 2
    assert all(r["order"] == "opponent_first" for r in result)
    assert {r["root"] for r in result} == {"0", "1"}


def test_native_primer_cannot_replace_a_failed_or_injured_later_state(monkeypatch, tmp_path):
    names = preparation.combined.N
    features = [0.] * len(names)
    features[names.index("choice.heal_full_hp")] = 1
    features[names.index("choice.effect.heal")] = 1
    monkeypatch.setattr(preparation.combined.lab, "BattleFeatureProjector", lambda *_:
                        SimpleNamespace(project=lambda observation: None))
    monkeypatch.setattr(preparation, "project_balanced_status_moves", lambda *a:
                        SimpleNamespace(candidate_vectors=[features], candidate_slots=[2]))
    capture = SimpleNamespace(manifest_sha256="a", manifest=SimpleNamespace(
        state_sha256="b", capture_id="new-later"))
    ep = {"stop_reason": "player_turn_budget", "decisions": [{"move_slot": 2}],
          "final_observation": {}}
    row = preparation.derive_later_row(capture, tmp_path, {"root": "train"}, ep, {"sha256": "c"})
    assert row["state_name"] == "intermediate.state" and row["capture_id"] == "new-later"
    features[names.index("choice.heal_full_hp")] = 0
    with pytest.raises(ValueError, match="no replacement"):
        preparation.derive_later_row(capture, tmp_path, {"root": "train"}, ep, {})
    ep["stop_reason"] = "party_defeated"
    with pytest.raises(ValueError, match="later decision"):
        preparation.derive_later_row(capture, tmp_path, {"root": "train"}, ep, {})


def test_fresh_native_recipe_plan_creates_all_cells_without_post_action_interventions(monkeypatch):
    templates = []
    for i in (0, 1):
        for family, contrast in preparation.CELLS:
            templates.append({"id": f"x-{i}-{family}-{i}-{contrast}", "family": family,
                "contrast": contrast, "source_index": i, "root": str(i),
                "effect_conditions": {"opponent_confusion_turns": 3}, "practice": {
                    "actor_species_ref": "pokemon.red.gb.us.rev0:species:001", "actor_level": 32,
                    "actor_moves": [{"move_ref": preparation.combined.lab.pokemon_red_move_ref(
                        preparation.combined.lab.FAMILIES[family]), "pp": 10}]}})
    monkeypatch.setattr(preparation, "crossed_recipes", lambda *a, **k: deepcopy(templates))
    monkeypatch.setattr(preparation, "timing_case", lambda r, c, order: {**r, "order": order})
    cartridge = SimpleNamespace(species=lambda _: SimpleNamespace(
        teachable_moves_at_level=lambda _: (92,)))
    rows = preparation.fresh_native_recipes(cartridge, ["0", "1", "2", "3"])
    assert len(rows) == 10 and len({r["id"] for r in rows}) == 10
    for family, condition in preparation.CELLS:
        assert sum(r["family"] == family and r["contrast"] == condition for r in rows) == 2
    for row in rows:
        if row["family"] == "confusion":
            assert row["effect_conditions"]["opponent_confusion_turns"] == 0
            assert row["order"] == "actor_first"
        if row["primer_move"] == 92:
            assert any(m["move_ref"].endswith(":092") for m in row["practice"]["actor_moves"])
    cartridge.species = lambda _: SimpleNamespace(teachable_moves_at_level=lambda _: ())
    with pytest.raises(ValueError, match="legally learn"):
        preparation.fresh_native_recipes(cartridge, ["0", "1", "2", "3"])
