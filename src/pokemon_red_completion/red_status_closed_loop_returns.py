"""Versioned TRAIN return from actual learner continuations and visible transitions.

This module scores retained outcomes only. It does not select, mask or execute
actions. No-change observations are not claimed to be cartridge failure messages.
"""

from collections.abc import Mapping
from typing import Any

from .red_battle_catalog import PokemonRedBattleCatalog

RETURN_SCHEMA = "pokemon.red.status.closed-loop-return.v1"


def unchanged_status_turns(episode: Mapping[str, Any]) -> list[int]:
    steps = episode["decisions"]
    flagged = []
    catalog = PokemonRedBattleCatalog()
    for index, step in enumerate(steps):
        if step["kind"] != "attack" or not step["outcome"]["move_executed"]:
            continue
        before = step["observation"]["features"]
        later = (steps[index + 1]["observation"] if index + 1 < len(steps)
                 else episode["final_observation"])["features"]
        old, new = before.get("battle"), later.get("battle")
        if not isinstance(new, dict) or not new.get("active") or not isinstance(old, dict):
            continue
        if old["opponent_species_ref"] != new["opponent_species_ref"]:
            continue
        move = next(m for m in before["party"]["lead"]["moves"]
                    if m["slot_index"] == step["move_slot"] - 1)
        effect = catalog.move_effect(move["move_ref"])
        unchanged = False
        if effect in {"SLEEP_EFFECT", "POISON_EFFECT", "PARALYZE_EFFECT"}:
            unchanged = old.get("opponent_status") == new.get("opponent_status")
        elif effect == "CONFUSION_EFFECT":
            if "status_context" in old and "status_context" in new:
                unchanged = (old["status_context"]["opponent_confused"]
                             == new["status_context"]["opponent_confused"])
        elif (effect == "ACCURACY_DOWN1_EFFECT" and "status_context" in old
              and "status_context" in new):
            unchanged = (old["status_context"]["opponent_stages"][4]
                         == new["status_context"]["opponent_stages"][4])
        # HP gain can be hidden by an incoming hit; enemy Disable is not observed.
        if unchanged:
            flagged.append(index + 1)
    return flagged


def closed_loop_return(episode: Mapping[str, Any]) -> float:
    steps = episode["decisions"]
    stop = episode["stop_reason"]
    if not steps or stop not in {"battle_won", "party_defeated", "player_turn_budget"}:
        raise ValueError("closed-loop return requires a retained bounded gameplay outcome")
    before, after = steps[0]["state_before"], steps[-1]["state_after"]
    hp = sum(after["party_hp"]) / sum(before["party_max_hp"])
    foe_cap = steps[0]["observation"]["features"]["battle"]["opponent_max_hp"]
    damage = (steps[0]["opponent_hp_before"] - steps[-1]["opponent_hp_after"]) / foe_cap
    return ((10. if stop == "battle_won" else -10.) + .5 * hp + .5 * damage
            - .1 * len(steps) - .01 * episode["metrics"]["party_pp_spent"]
            - .5 * len(unchanged_status_turns(episode)))
