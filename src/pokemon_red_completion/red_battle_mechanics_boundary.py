"""Disclosed Red-only action screening, not learned preferences or a type override."""

from pokemon_red_completion.red_battle_scenario import red_battle_move_is_model_supported


def capped_stat_choices(observation, catalog, legal_moves):
    """Screen known capped stat effects only; never choose a damaging move.

    This supplied mechanics rule is opt-in at the policy. Unknown effects,
    uncapped setup, sleep and other statuses remain available. Keep a nonempty
    inventory if every available move is a no-op rather than invent an action.
    """
    battle = observation["features"]["battle"]
    context = battle.get("status_context")
    if not isinstance(context, dict) or context.get("schema") != (
        "pokemon.core.battle.status-context.v1"
    ):
        raise ValueError("Capped stat screen requires observed status context")
    stats = ("ATTACK", "DEFENSE", "SPEED", "SPECIAL", "ACCURACY", "EVASION")
    for side in ("player", "opponent"):
        values = context.get(f"{side}_stages")
        if (
            not isinstance(values, list)
            or len(values) != 6
            or any(type(v) is not int or not -6 <= v <= 6 for v in values)
        ):
            raise ValueError("Capped stat screen requires six observed stages")
    moves = observation["features"]["party"]["lead"]["moves"]
    by_slot = {m["slot_index"] + 1: m["move_ref"] for m in moves}
    removed = []
    for slot in legal_moves:
        ref = by_slot[slot]
        if catalog.resolve_move(ref).category != "status":
            continue
        effect = catalog.move_effect(ref)
        for index, stat in enumerate(stats):
            for direction, side, cap in (("UP", "player", 6), ("DOWN", "opponent", -6)):
                if effect in {f"{stat}_{direction}{n}_EFFECT" for n in (1, 2)} and (
                    context[f"{side}_stages"][index] == cap
                ):
                    removed.append(slot)
    if len(removed) == len(legal_moves):
        return legal_moves, ()
    return tuple(s for s in legal_moves if s not in removed), tuple(removed)


def immunity_choices(observation, prepared, catalog, legal_moves):
    """Remove proven-immune ordinary damage only with a productive alternative.

    Status and special damage are never classified through the ordinary type
    multiplier. Resistant/neutral/super-effective attacks remain ranker choices.
    A reserve is productive here only when it has an ordinary attack with PP and
    nonzero effectiveness; this is not a claim that switching guarantees survival.
    """
    batch = prepared.features
    names = batch.feature_names
    immune, productive, special = [], [], []
    for slot in legal_moves:
        row = batch.candidate_vectors[batch.slot_indices.index(slot - 1)]
        if row[names.index("move.category.status")]:
            continue
        ordinary = (
            row[names.index("move.power_fraction")] > 0
            and row[names.index("move.effect.fixed_damage")] == 0
        )
        if not ordinary:
            special.append(slot)
        elif row[names.index("move.type_effectiveness_fraction")] == 0:
            immune.append(slot)
        else:
            productive.append(slot)
    all_damage_immune = bool(immune) and not productive and not special
    reserves = productive_reserve_slots(observation, catalog) if all_damage_immune else ()
    removed = tuple(immune) if productive or reserves else ()
    admitted = tuple(slot for slot in legal_moves if slot not in removed)
    return admitted, tuple(reserves), removed


def productive_reserve_slots(observation, catalog):
    features = observation["features"]
    party, battle = features["party"], features["battle"]
    foe = catalog.resolve_species(battle["opponent_species_ref"])
    reserves = []
    for index, member in enumerate(party["members"]):
        if index == party["active_index"] or member["hp"] <= 0:
            continue
        for item in member["moves"]:
            if item["pp"] <= 0:
                continue
            move = catalog.resolve_move(item["move_ref"])
            if (
                move.category != "status"
                and move.power > 0
                and "fixed_damage" not in move.effect_flags
                and red_battle_move_is_model_supported(
                    int(item["move_ref"].rsplit(":", 1)[1]), item["pp"], catalog=catalog
                )
                and catalog.type_effectiveness(move.type_name, foe.types) > 0
            ):
                reserves.append(index + 1)
                break
    return tuple(reserves)
