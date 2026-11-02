"""ROM-free guards around the single-use native damage experiment."""

import json
from itertools import product

import pytest
import run_red_interaction_damage_successor as packet


def synthetic_plan():
    sources = [(None, {"source_id": f"root-{i}"}) for i in range(4)]
    families, rows = [], []
    for role, n in (("fit", 24), ("comparison", 16)):
        for i in range(n):
            root = (i // 4 + i % 4) % 4
            family = f"{role}-{i:02d}"
            families.append(
                {
                    "id": family,
                    "role": role,
                    "actor": i + (1 if role == "fit" else 101),
                    "enemy": i + (201 if role == "fit" else 301),
                    "favored": "physical" if (i // 4) % 2 == 0 else "special",
                    "source_index": root,
                    "level": packet.LEVELS[i % 4],
                }
            )
            for context in ("neutral", "burn", "stage"):
                rows.append(
                    {
                        "id": f"{family}-{context}",
                        "family_id": family,
                        "role": role,
                        "context": context,
                        "favored": families[-1]["favored"],
                        "practice": {
                            "actor_level": families[-1]["level"],
                            "actor_species_ref": f"species:{families[-1]['actor']:03d}",
                            "opponent_species_ref": f"species:{families[-1]['enemy']:03d}",
                        },
                        "source_index": root,
                        "root": sources[root][1]["source_id"],
                    }
                )
    return rows, families, sources


def test_root_level_category_and_family_split_validator(monkeypatch):
    monkeypatch.setattr(packet, "_prior_pairs", lambda: set())
    rows, families, sources = synthetic_plan()
    packet.validate_plan(rows, families, sources)
    assert (
        len({(f["source_index"], f["level"]) for f in families if f["role"] == "comparison"}) == 16
    )
    families[24]["source_index"] = 1
    with pytest.raises(ValueError, match="crossing"):
        packet.validate_plan(rows, families, sources)


def test_historical_pair_or_imbalanced_category_fails_before_native(monkeypatch):
    rows, families, sources = synthetic_plan()
    monkeypatch.setattr(packet, "_prior_pairs", lambda: {(1, 201)})
    with pytest.raises(ValueError, match="historical exclusion"):
        packet.validate_plan(rows, families, sources)
    monkeypatch.setattr(packet, "_prior_pairs", lambda: set())
    for f in families:
        if f["role"] == "comparison":
            f["favored"] = "special"
    with pytest.raises(ValueError, match="physical/special"):
        packet.validate_plan(rows, families, sources)


def test_exact_and_near_best_and_physical_retention_use_actual_slots(monkeypatch):
    monkeypatch.setattr(packet.old, "sha", lambda _: "digest")

    class Head:
        def __init__(self, selected):
            self.selected = selected

        def predict_index(self, _):
            return self.selected

    at_p = packet.old.MOVE_FEATURE_NAMES.index("move.category.physical")
    at_s = packet.old.MOVE_FEATURE_NAMES.index("move.category.special")
    vectors = [[0.0] * len(packet.old.MOVE_FEATURE_NAMES) for _ in range(4)]
    for index in (0, 2):
        vectors[index][at_p] = 1.0
    for index in (1, 3):
        vectors[index][at_s] = 1.0
    row = {
        "id": "fit-00-neutral",
        "family_id": "fit-00",
        "source_index": 0,
        "context": "neutral",
        "favored": "physical",
        "ratio_bin": "middle",
        "mean_damage": (0.49, 0.5, 0.01, 0.0),
        "vectors": vectors,
        "branches": [{}] * 12,
    }
    evaluated = packet._evaluate([row] * 96, Head(0), Head(1), expected=96, branches_per_case=12)
    case = evaluated["cases"][0]
    assert case["baseline_exact_best"] is False
    assert case["baseline_near_best"] is True
    assert case["candidate_exact_best"] is True
    assert case["physical_best"] is False and case["special_best"] is True


def test_no_resume_and_elapsed_cap(monkeypatch, tmp_path):
    monkeypatch.setattr(packet, "OUTPUT", tmp_path)
    with pytest.raises(ValueError, match="single-use"):
        packet.run(preflight_only=True)
    monkeypatch.setattr(packet.time, "monotonic", lambda: 2700.0)
    with pytest.raises(TimeoutError, match="45minutes"):
        packet._deadline(0.0)


def test_offsets_and_branch_budget_exact():
    assert tuple(range(0, 36, 4)) == packet.OFFSETS
    assert len(tuple(product(range(4), packet.OFFSETS))) == 36
    assert 120 * 36 == 4320
    with pytest.raises(ValueError, match="native trainer bound"):
        packet.validate_offsets(packet.OFFSETS)
    packet.validate_offsets(tuple(range(9)))
    with pytest.raises(ValueError, match="native trainer bound"):
        packet.validate_offsets(tuple([0] * 9))


def test_preflight_rejects_v1_offsets_before_loading_inputs(monkeypatch):
    def forbidden():
        raise AssertionError("private inputs should not open")

    monkeypatch.setattr(packet.old, "inputs", forbidden)
    with pytest.raises(ValueError, match="native trainer bound"):
        packet.preflight()


@pytest.mark.parametrize(
    "offsets", [(False, 1, 3, 4, 6, 7, 9, 10, 12), (0, 1, 3, 4, 6, 7, 9, 10, 13)]
)
def test_timing_validator_uses_native_type_and_upper_bound(offsets):
    with pytest.raises(ValueError, match="native trainer bound"):
        packet.validate_offsets(offsets)
    packet.validate_offsets(packet.V2_OFFSETS)


def test_no_family_role_or_species_substitution(monkeypatch):
    monkeypatch.setattr(packet, "_prior_pairs", lambda: set())
    rows, families, sources = synthetic_plan()
    rows[0]["role"] = "comparison"
    with pytest.raises(ValueError, match="partition"):
        packet.validate_plan(rows, families, sources)
    rows[0]["role"] = "fit"
    rows[0]["practice"]["actor_species_ref"] = "species:999"
    with pytest.raises(ValueError, match="partition"):
        packet.validate_plan(rows, families, sources)


def test_additional_v1_pairs_are_excluded(monkeypatch):
    monkeypatch.setattr(packet, "_prior_pairs", lambda: set())
    rows, families, sources = synthetic_plan()
    with pytest.raises(ValueError, match="historical exclusion"):
        packet.validate_plan(rows, families, sources, excluded_pairs={(1, 201)})


def test_fit_failure_retains_claim_and_prevents_retry(monkeypatch, tmp_path):
    output = tmp_path / "experiment"
    monkeypatch.setattr(
        packet, "experiment_config", lambda _: (output, 1, packet.V2_OFFSETS, set())
    )
    rows = [{"id": f"fit-{i}", "role": "fit"} for i in range(72)]
    rows.append({"id": "comparison-unopened", "role": "comparison"})
    monkeypatch.setattr(packet, "preflight", lambda **_: (None, None, [], None, None, rows, {}))
    monkeypatch.setattr(packet, "_source_pins", lambda: {})
    monkeypatch.setattr(packet.subprocess, "check_output", lambda *a, **k: b"")
    monkeypatch.setattr(packet.old, "sha", lambda _: "a" * 64)
    measured = []

    def measure(args, row, *unused, **kwargs):
        measured.append(row["id"])
        return {"id": row["id"], "vectors": [], "mean_damage": []}

    monkeypatch.setattr(packet, "_measure", measure)
    fits = []

    def fail_fit(*args, **kwargs):
        fits.append(1)
        assert (output / "FIT_CLAIM.json").is_file()
        raise ValueError("injected fit failure")

    monkeypatch.setattr(packet, "fit_damage_interaction_head", fail_fit)
    with pytest.raises(ValueError, match="injected fit failure"):
        packet.run(version=2)
    assert len(measured) == 72 and fits == [1]
    assert json.loads((output / "FAILURE.json").read_bytes())["fit_claimed"] is True
    assert not (output / "candidate-model.json").exists()
    with pytest.raises(ValueError, match="single-use"):
        packet.run(version=2)
    assert fits == [1]
