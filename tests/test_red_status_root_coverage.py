from copy import deepcopy
from types import SimpleNamespace

import pytest
import red_status_root_coverage as coverage

from pokemon_red_completion.red_battle_catalog import PokemonRedBattleCatalog


def templates():
    catalog = PokemonRedBattleCatalog()
    ordinary = next(s for s in catalog.species_ids if not set(
        catalog.resolve_species(f"pokemon.red.gb.us.rev0:species:{s:03d}").types) &
        {"poison", "ground"})
    immune = {t: next(s for s in catalog.species_ids if t in catalog.resolve_species(
        f"pokemon.red.gb.us.rev0:species:{s:03d}").types) for t in ("ground", "poison")}

    def enemy_ref(family, contrast):
        species = (immune["poison" if family == "poison" else "ground"]
                   if contrast == 3 and family in {"poison", "paralysis"} else ordinary)
        return f"pokemon.red.gb.us.rev0:species:{species:03d}"

    return [{"id": f"{family}-{v}-{contrast}", "family": family, "contrast": contrast,
             "role": "holdout" if v == 2 else "train",
             "conditions": {"opponent_status": "paralysis" if contrast == 1 else "none",
                            "opponent_accuracy": -6 if contrast == 1 else 0},
             "practice": {"actor_species_ref": f"pokemon.red.gb.us.rev0:species:{ordinary:03d}",
                "actor_level": 32, "actor_hp": 100 if contrast == 1 else 50,
                "opponent_species_ref": enemy_ref(family, contrast)}}
            for family in sorted(coverage.FAMILIES) for v in range(3) for contrast in range(4)]


def setup(monkeypatch):
    import run_red_balanced_status_curriculum as old
    rows = templates()
    monkeypatch.setattr(old, "balanced_recipes", lambda *args, **kw: deepcopy(rows))
    cartridge = SimpleNamespace(species=lambda _: SimpleNamespace(
        neutral_stats=lambda _: SimpleNamespace(max_hp=100)))
    return cartridge, ["root0", "root1", "root2", "root3"]


def test_every_mechanic_occurs_on_each_root_without_role_leakage(monkeypatch):
    cartridge, roots = setup(monkeypatch)
    rows = coverage.crossed_recipes(cartridge, roots)
    assert len(rows) == 224
    assert coverage.validate_recipes(list(reversed(rows)), roots, cartridge)["training"] == 192
    assert {r["root"] for r in rows if r["role"] == "train"} == set(roots[:3])
    assert {r["root"] for r in rows if r["role"] == "holdout"} == {roots[3]}


def test_positional_assignment_missing_contrast_and_fake_immunity_rejected(monkeypatch):
    cartridge, roots = setup(monkeypatch)
    rows = coverage.crossed_recipes(cartridge, roots)
    with pytest.raises(ValueError):
        coverage.validate_recipes(rows[:-1], roots, cartridge)
    wrong = deepcopy(rows)
    wrong[0]["source_index"] = 1
    with pytest.raises(ValueError, match="source/role"):
        coverage.validate_recipes(wrong, roots, cartridge)
    wrong = deepcopy(rows)
    poisoned = next(r for r in wrong if r["family"] == "poison" and r["contrast"] == 3)
    poisoned["practice"]["opponent_species_ref"] = next(r for r in wrong if
        r["family"] == "poison" and r["contrast"] == 0)["practice"]["opponent_species_ref"]
    with pytest.raises(ValueError, match="immunity"):
        coverage.validate_recipes(wrong, roots, cartridge)


def test_missing_actual_observed_support_is_not_replaced_by_a_plan():
    with pytest.raises(ValueError, match="choice.poison_type_immune"):
        coverage.require_observed_support([], ["root0"])


def test_native_diagnostic_builder_never_requests_custom_trainer_stats():
    from qualify_red_status_effect_trace import diagnostic_recipes

    from pokemon_red_completion.battle_practice_factory import PracticeStats
    actor = SimpleNamespace(neutral_stats=lambda _: PracticeStats(100, 40, 40, 50, 40))
    enemy = SimpleNamespace(trainer_stats=lambda _: PracticeStats(100, 30, 30, 20, 30),
                            teachable_moves_at_level=lambda _: (33, 55), national_number=35)
    cartridge = SimpleNamespace(species_ids=(4,), species=lambda s: actor if s == 40 else enemy)
    rows = [{"id": f"example-balanced-{family}-0-{contrast}", "source_index": i % 3,
             "family": family, "contrast": contrast, "conditions": {},
             "practice": {"actor_species_ref": "pokemon.red.gb.us.rev0:species:040",
                          "actor_level": 32, "opponent_level": 32, "actor_hp": 75}}
            for i, family in enumerate(("heal", "rest", "confusion", "disable"))
            for contrast in (0, 1)]
    before = deepcopy(rows)
    result = diagnostic_recipes(rows, cartridge)
    assert len(result) == 8 and rows == before
    assert all("actor_stats" not in r["practice"] and "opponent_stats" not in r["practice"]
               for r in result)
