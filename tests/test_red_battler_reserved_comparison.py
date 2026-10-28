from types import SimpleNamespace

import pytest
import run_red_battler_reserved_comparison as comparison


def test_failed_readiness_blocks_before_rom_access_or_output_creation(monkeypatch, tmp_path):
    monkeypatch.setattr(comparison, "inspect", lambda *a: {
        "ready_to_prepare_reserved_comparison": False,
        "first_unpassed_gate": "later_effect_qualification"})
    monkeypatch.setattr(comparison.combined.previous, "load_inputs",
                        lambda *a: pytest.fail("reserved recipes accessed"))
    args = SimpleNamespace(root=tmp_path, packet=tmp_path / "packet",
                           rom=tmp_path / "absent.gb")
    with pytest.raises(ValueError, match="blocked by later_effect"):
        comparison.run(args)
    assert not args.packet.exists()


def recipes():
    return [{"id": f"case-{i}-{seed}", "role": "holdout"}
            for seed in comparison.COHORTS for i in range(32)]


def test_all_four_original_cohorts_are_required():
    comparison.validate_recipes(recipes(), SimpleNamespace(damage_reference=object()))


@pytest.mark.parametrize("change", ["missing", "duplicate", "role", "cohort", "damage"])
def test_comparison_cannot_shrink_or_relabel_the_reserved_inventory(change):
    cases, candidate = recipes(), SimpleNamespace(damage_reference=object())
    if change == "missing":
        cases.pop()
    elif change == "duplicate":
        cases[-1] = cases[0]
    elif change == "role":
        cases[0]["role"] = "train"
    elif change == "cohort":
        cases[0]["id"] = "not-a-declared-cohort"
    else:
        candidate.damage_reference = None
    with pytest.raises(ValueError):
        comparison.validate_recipes(cases, candidate)
