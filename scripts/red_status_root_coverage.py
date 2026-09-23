"""Prospective crossed TRAIN-root recipes and fail-closed mechanics support checks."""

from collections import Counter
from copy import deepcopy

from pokemon_red_completion.red_balanced_status_features import COMPACT_STATUS_NAMES
from pokemon_red_completion.red_battle_catalog import PokemonRedBattleCatalog

SEED = 2026092137
FAMILIES = {"sleep", "paralysis", "poison", "accuracy", "confusion", "disable", "heal", "rest"}


def crossed_recipes(cartridge, roots, *, seed=SEED):
    from run_red_balanced_status_curriculum import balanced_recipes
    if len(roots) != 4 or len(set(roots)) != 4 or list(roots) != sorted(roots):
        raise ValueError("four distinct sorted TRAIN roots required")
    rows = []
    for source_index, root in enumerate(roots):
        for template in balanced_recipes(cartridge, seed=seed):
            role = "holdout" if source_index == 3 else "train"
            if template["role"] != role:
                continue
            row = deepcopy(template)
            row.update(id=f"effect-crossed-{source_index}-{template['id']}",
                       source_index=source_index, root=root, native_followup=False)
            row["effect_conditions"] = {
                "opponent_confusion_turns": 3 if row["family"] == "confusion" and
                    row["contrast"] == 1 else 0,
                "opponent_disabled_slot": 1 if row["family"] == "disable" and
                    row["contrast"] == 1 else None}
            rows.append(row)
    validate_recipes(rows, roots, cartridge)
    return rows


def validate_recipes(rows, roots, cartridge):
    catalog = PokemonRedBattleCatalog()
    if len(rows) != 224 or len({r["id"] for r in rows}) != 224:
        raise ValueError("expected224unique prospective recipes")
    counts = Counter()
    for row in rows:
        index = row["source_index"]
        if (type(index) is not int or index not in range(4) or row["root"] != roots[index]
                or row["role"] != ("holdout" if index == 3 else "train")):
            raise ValueError("explicit source/role assignment differs")
        family, contrast = row["family"], row["contrast"]
        if family not in FAMILIES or contrast not in range(4):
            raise ValueError("unknown family/contrast")
        p, c = row["practice"], row["conditions"]
        if family in {"confusion", "disable"}:
            key = "opponent_confusion_turns" if family == "confusion" else "opponent_disabled_slot"
            if bool(row["effect_conditions"][key]) != (contrast == 1):
                raise ValueError("required occupied volatile-effect contrast is missing")
        types = catalog.resolve_species(p["opponent_species_ref"]).types
        if family in {"poison", "paralysis"}:
            immune = ("poison" if family == "poison" else "ground") in types
            if immune != (contrast == 3):
                raise ValueError("required immunity contrast is missing")
        if (family in {"sleep", "poison", "paralysis"} and
                (c["opponent_status"] != "none") != (contrast == 1)):
            raise ValueError("required occupied-status contrast is missing")
        if family == "accuracy" and (c["opponent_accuracy"] == -6) != (contrast == 1):
            raise ValueError("required accuracy-floor contrast is missing")
        if family in {"heal", "rest"}:
            max_hp = cartridge.species(int(p["actor_species_ref"].rsplit(":", 1)[1])).neutral_stats(
                p["actor_level"]).max_hp
            if (p["actor_hp"] == max_hp) != (contrast == 1):
                raise ValueError("required full/injured healing contrast is missing")
        counts[(index, family, contrast)] += 1
    expected = {(i, f, c): (1 if i == 3 else 2)
                for i in range(4) for f in FAMILIES for c in range(4)}
    if counts != expected:
        raise ValueError("mechanics are not represented on every declared root")
    return {"recipes": len(rows), "training": 192, "reserved": 32,
            "conditions_per_root": 32, "independent_natural_roots": 0}


def require_observed_support(rows, roots):
    """Future pre-fit admission: plans do not substitute for observed feature support."""
    required = {
        "poison": ("choice.major_status_occupied", "choice.poison_type_immune"),
        "paralysis": ("choice.major_status_occupied", "choice.electric_paralysis_type_immune"),
        "sleep": ("choice.major_status_occupied",), "accuracy": ("choice.accuracy_floor",),
        "heal": ("choice.heal_full_hp",), "rest": ("choice.heal_full_hp",),
        "confusion": ("choice.already_confused",),
    }
    missing = []
    for root in roots:
        for family, names in required.items():
            subset = [r for r in rows if r["root"] == root and
                      r["evidence"]["family"] == family and r["evidence"]["kind"] == "observed"]
            if {r["evidence"]["net_change"] for r in subset} != {0, 1}:
                missing.append(f"{root}:{family}:both_observed_classes")
            for name in names:
                index = COMPACT_STATUS_NAMES.index(name)
                if {r["features"][index] for r in subset} != {0., 1.}:
                    missing.append(f"{root}:{family}:{name}")
    if missing:
        raise ValueError("insufficient measured support: " + ", ".join(missing))
