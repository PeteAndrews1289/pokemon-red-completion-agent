"""Read-only risk measurements from retained, digest-bound battle episodes.

These are diagnostics, not action masks, teacher labels or counterfactual regret.
Positive-power coverage omits indirect/fixed damage, future turns and special
effects; zero coverage does not prove a member can never contribute or win.
No unseen opponent roster, native memory, or outcome chooses an actor action.
"""

import hashlib
import json
import math
from collections import Counter

from .battle_matchups import project_party_matchups


def _integer(value, low, high, label):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"invalid {label}")
    return value


def review_battle_choices(payload, *, expected_sha256, catalog):
    """Report observable risks without changing a policy or prescribing a move.

    The digest authenticates the supplied episode bytes, not their experimental
    provenance. Callers must independently check event logs, model identity and
    partition before interpreting this report as evidence from an admitted run.
    """
    if type(payload) is not bytes or hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise ValueError("battle review episode digest differs")
    episode = json.loads(payload)
    if episode.get("schema") != "pokemon.red.trainer-practice-model-episode.v4":
        raise ValueError("unsupported battle episode schema")
    decisions = episode.get("decisions")
    if not isinstance(decisions, list) or not decisions:
        raise ValueError("battle review needs completed decisions")
    if _integer(episode.get("decision_count"), 1, 100000, "decision count") != len(decisions):
        raise ValueError("battle decision count differs")
    counts, rows = Counter(), []
    for number, decision in enumerate(decisions, 1):
        if _integer(decision.get("decision_index"), 1, 100000, "decision index") != number:
            raise ValueError("battle decision order differs")
        kind = decision.get("kind")
        if kind not in {
            "attack",
            "voluntary_switch",
            "forced_switch",
            "switch_prompt",
            "forced_struggle",
        }:
            raise ValueError("unsupported battle decision kind")
        observation = decision["observation"]
        party, battle = (observation["features"][key] for key in ("party", "battle"))
        members = party["members"]
        size = _integer(party["count"], 1, 6, "party count")
        active = _integer(party["active_index"], 0, size - 1, "active index") + 1
        if not isinstance(members, list) or len(members) != size:
            raise ValueError("observed party size differs")
        if party["lead"] != {k: v for k, v in members[active - 1].items() if k != "party_index"}:
            raise ValueError("active member and lead observation differ")
        for index, member in enumerate(members):
            if _integer(member.get("party_index"), 0, size - 1, "party index") != index:
                raise ValueError("observed member order differs")
        profiles = {p.party_slot: p for p in project_party_matchups(observation, catalog)}
        foe_hp = _integer(battle["opponent_hp"], 0, 999, "opponent HP")
        foe_max = _integer(battle["opponent_max_hp"], 1, 999, "opponent maximum HP")
        if foe_hp > foe_max:
            raise ValueError("opponent HP exceeds maximum")
        row = dict(
            decision_index=number,
            kind=kind,
            active_slot=active,
            opponent_hp=foe_hp,
            opponent_hp_fraction=foe_hp / foe_max,
        )
        counts[kind] += 1
        probabilities = decision.get("model_diagnostics", {}).get("control_probabilities")
        if probabilities is not None:
            if (
                not isinstance(probabilities, list)
                or len(probabilities) != 2
                or any(
                    type(x) not in {int, float} or not math.isfinite(x) or not 0 <= x <= 1
                    for x in probabilities
                )
                or not math.isclose(sum(probabilities), 1, abs_tol=1e-6)
            ):
                raise ValueError("malformed control probabilities")
            row["control_probability_margin"] = abs(probabilities[0] - probabilities[1])
            counts["control_margins_within_0_05"] += row["control_probability_margin"] <= 0.05
        if kind == "attack":
            if active not in profiles:
                raise ValueError("fainted member cannot select an attack")
            slot = _integer(decision.get("move_slot"), 1, 4, "selected move slot")
            matches = [m for m in party["lead"]["moves"] if m["slot_index"] + 1 == slot]
            legal_moves = decision["legal_move_slots"]
            if (
                not isinstance(legal_moves, list)
                or any(type(v) is not int or not 1 <= v <= 4 for v in legal_moves)
                or len(set(legal_moves)) != len(legal_moves)
                or len(matches) != 1
                or slot not in legal_moves
                or matches[0]["pp"] <= 0
            ):
                raise ValueError("selected attack lacks a usable logged move")
            move = catalog.resolve_move(matches[0]["move_ref"])
            opponent = catalog.resolve_species(battle["opponent_species_ref"])
            immune = (
                move.category != "status"
                and catalog.type_effectiveness(move.type_name, opponent.types) == 0
            )
            row.update(
                selected_move_slot=slot,
                type_immune_attack=immune,
                active_positive_power_coverage=profiles[active].offensive_power > 0,
                selected_status_move=move.category == "status",
                selected_while_asleep=party["lead"].get("status") == "sleep",
            )
            counts["type_immune_attacks"] += immune
            counts["attacks_without_positive_power_coverage"] += (
                profiles[active].offensive_power == 0
            )
            counts["status_move_choices"] += row["selected_status_move"]
            counts["attack_choices_while_asleep"] += row["selected_while_asleep"]
        elif kind == "forced_struggle":
            from .red_trainer_practice_admission import _actor_observation_matches

            if not _actor_observation_matches(decision):
                raise ValueError("unproved forced Struggle mechanic")
            row["authority"] = "forced_mechanic"
        else:
            declined = kind == "switch_prompt" and decision.get("party_slot") is None
            chosen = (
                active
                if declined
                else _integer(decision.get("party_slot"), 1, size, "selected party slot")
            )
            legal = decision["legal_party_slots"]
            if (
                not isinstance(legal, list)
                or any(type(slot) is not int or slot not in profiles for slot in legal)
                or len(set(legal)) != len(legal)
                or active in legal
                or chosen not in profiles
                or (not declined and chosen not in legal)
            ):
                raise ValueError("selected switch lacks a living legal candidate")
            alternatives = [
                slot for slot in legal if slot != chosen and profiles[slot].offensive_power > 0
            ]
            # Staying with the active member is a real alternative to voluntary
            # switching, even though it is not in the switch-target mask.
            if (
                kind in {"voluntary_switch", "switch_prompt"}
                and active != chosen
                and active in profiles
                and profiles[active].offensive_power > 0
            ):
                alternatives.append(active)
            selected = profiles[chosen]
            risk = selected.offensive_power == 0 and bool(alternatives)
            row.update(
                selected_party_slot=chosen,
                stayed=chosen == active,
                selected_hp_fraction=selected.hp_ratio,
                selected_positive_power_coverage=selected.offensive_power > 0,
                other_coverage_slots=sorted(set(alternatives)),
                zero_power_choice_with_covered_alternative=risk,
            )
            counts["zero_power_choices_with_covered_alternative"] += risk
            counts["switch_choices_below_quarter_hp"] += (
                chosen != active and selected.hp_ratio < 0.25
            )
        rows.append(row)
    return dict(
        schema="pokemon.battle.choice-risk-review.v1",
        episode_sha256=expected_sha256,
        decision_count=len(rows),
        counts=dict(counts),
        decisions=rows,
        policy_changed=False,
        training_labels=False,
        counterfactual_tested=False,
        limitations=[
            "Risk flags are not proved mistakes or estimates of alternative win probability.",
            "Positive-power coverage excludes indirect/fixed damage and does not predict survival.",
            "Type immunity is catalog-level; "
            "special move execution effects require separate checks.",
            "Digest binding alone does not validate event logs or independent origins.",
        ],
    )
