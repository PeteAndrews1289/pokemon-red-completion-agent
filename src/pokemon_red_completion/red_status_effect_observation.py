"""Conservative turn-boundary evidence; never a causal success label or action rule."""

from .red_battle_catalog import PokemonRedBattleCatalog, pokemon_red_move_ref

EFFECT_OBSERVATION_SCHEMA = "pokemon.red.status.boundary-effect-observation.v1"


def observe_status_effect(episode, index=0):
    steps = episode["decisions"]
    step = steps[index]
    result = {"schema": EFFECT_OBSERVATION_SCHEMA, "net_change": None,
              "application_success": None, "family": "unsupported"}

    def finish(kind, reason, value=None):
        return {**result, "kind": kind, "reason": reason, "net_change": value}

    if step["kind"] != "attack":
        return finish("unknown", "not_an_attack")
    old_features = step["observation"]["features"]
    move = next(m for m in old_features["party"]["lead"]["moves"]
                if m["slot_index"] == step["move_slot"] - 1)
    effect = PokemonRedBattleCatalog().move_effect(move["move_ref"])
    family = {"SLEEP_EFFECT": "sleep", "PARALYZE_EFFECT": "paralysis",
              "POISON_EFFECT": "poison", "CONFUSION_EFFECT": "confusion",
              "ACCURACY_DOWN1_EFFECT": "accuracy", "DISABLE_EFFECT": "disable",
              "HEAL_EFFECT": "heal"}.get(effect, "unsupported")
    if move["move_ref"] == pokemon_red_move_ref(156):
        family = "rest"
    result["family"] = family
    executed = step["outcome"]["move_executed"]
    if type(executed) is not bool:
        raise ValueError("effect observation requires explicit execution boolean")
    if not executed:
        return finish("suppressed", "selected_move_not_executed")
    if family in {"heal", "rest", "disable", "unsupported"}:
        return finish("unknown", "immediate_effect_not_observed")
    later = (steps[index + 1]["observation"] if index + 1 < len(steps)
             else episode["final_observation"])["features"]
    before, after = old_features.get("battle"), later.get("battle")
    if (not isinstance(before, dict) or not isinstance(after, dict)
            or not before.get("active") or not after.get("active")):
        return finish("unknown", "terminal_or_missing_opponent")
    if not before.get("opponent_species_ref") or not after.get("opponent_species_ref"):
        return finish("unknown", "missing_opponent_identity")
    if before.get("opponent_species_ref") != after.get("opponent_species_ref"):
        return finish("unknown", "opponent_changed")
    a, b = step["state_before"], step["state_after"]
    for key in ("opponent_party_position", "opponent_species_id", "active_party_slot"):
        if key not in a or key not in b or a[key] is None or b[key] is None:
            return finish("unknown", "missing_boundary_identity")
        if a[key] != b[key]:
            return finish("unknown", "boundary_subject_changed")
    if index + 1 < len(steps) and b != steps[index + 1]["state_before"]:
        return finish("unknown", "intervening_resource_transition")
    if family in {"sleep", "paralysis", "poison"}:
        if "opponent_status" not in before or "opponent_status" not in after:
            return finish("unknown", "missing_status")
        old, new = before["opponent_status"], after["opponent_status"]
        if old == "sleep":
            return finish("unknown", "sleep_duration_or_expiry_ambiguous")
        if new == family and old != family:
            return finish("observed", "new_intended_affliction", 1)
        if old == new:
            return finish("observed", "no_net_affliction_change", 0)
        return finish("unknown", "other_affliction_transition")
    old_context, new_context = before.get("status_context"), after.get("status_context")
    if not isinstance(old_context, dict) or not isinstance(new_context, dict):
        return finish("unknown", "missing_status_context")
    if family == "confusion":
        old, new = old_context.get("opponent_confused"), new_context.get("opponent_confused")
        if type(old) is not bool or type(new) is not bool:
            return finish("unknown", "missing_confusion_boolean")
        if old:
            return finish("unknown", "confusion_expiry_or_reapplication_ambiguous")
        return finish("observed", "net_confusion_transition", int(new))
    old, new = old_context.get("opponent_stages"), new_context.get("opponent_stages")
    if (not isinstance(old, list) or not isinstance(new, list)
            or len(old) != 6 or len(new) != 6):
        return finish("unknown", "missing_accuracy_stage")
    if (type(old[4]) is not int or type(new[4]) is not int
            or not -6 <= old[4] <= 6 or not -6 <= new[4] <= 6):
        return finish("unknown", "invalid_accuracy_stage")
    if new[4] > old[4]:
        return finish("unknown", "opposing_accuracy_transition")
    return finish("observed", "net_accuracy_transition", int(new[4] < old[4]))
