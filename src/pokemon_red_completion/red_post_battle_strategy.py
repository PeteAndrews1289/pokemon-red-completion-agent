"""Read-only Red log adapter for title-neutral strategic battle evidence.

Only retained, authenticated episode bytes enter this adapter. It neither opens
a ROM nor issues inputs. The caller must separately authenticate the current
terminal and recovery; a battle-ending snapshot is not the healed field state.
"""

import hashlib
import json
import re
from collections import Counter

from .battle_actions import BattleAction
from .battle_opposition import observed_opponent_position
from .post_battle_strategy import BattleAftermath, BattleResult, _integer


def _party(state, size):
    arrays = [state[name] for name in ("party_hp", "party_max_hp", "party_levels", "party_pp")]
    if any(not isinstance(a, list) or len(a) != size for a in arrays):
        raise ValueError("battle party shape changed")
    hp, maximum, levels, pp = arrays
    for health, cap, level, moves in zip(hp, maximum, levels, pp, strict=True):
        _integer(cap, 1, 65535, "maximum HP")
        _integer(health, 0, cap, "HP")
        _integer(level, 1, 100, "level")
        if not isinstance(moves, list) or len(moves) != 4:
            raise ValueError("four PP slots required")
        for value in moves:
            _integer(value, 0, 63, "PP")
    return hp, maximum, levels, pp


def _trainer_roster_faints(row, count):
    """Read referee-only roster transitions, not the possibly switched active foe.

    New V4 recordings retain this proof when trainer AI switches during a turn.
    Older recordings and final turns without retained roster RAM use the existing
    selected-turn outcome. No referee HP is exposed in the strategic features.
    """
    keys = (
        "referee_opponent_roster_hp_before",
        "referee_opponent_roster_hp_after",
        "opponent_faints",
    )
    if not any(key in row for key in keys):
        return None
    if not all(key in row for key in keys):
        raise ValueError("incomplete opponent roster faint proof")
    before, after = (row[key] for key in keys[:2])
    if any(not isinstance(values, list) or len(values) != count for values in (before, after)):
        raise ValueError("opponent roster faint proof shape differs")
    for old, new in zip(before, after, strict=True):
        _integer(old, 0, 65535, "opponent roster HP")
        _integer(new, 0, 65535, "opponent roster HP")
        if old == 0 and new != 0:
            raise ValueError("fainted opponent revived inside trainer episode")
    fainted = sum(old > 0 and new == 0 for old, new in zip(before, after, strict=True))
    if type(row[keys[2]]) is not int or row[keys[2]] != fainted:
        raise ValueError("opponent roster faint count contradicts HP proof")
    return fainted


def _model_struggle_evidence(row, before, slot, *, wild, roster_faints):
    """Keep learned zero-PP attacks distinct from forced singleton mechanics."""
    outcome = row.get("outcome")
    diagnostics = row.get("model_diagnostics")
    proposal = diagnostics.get("struggle_proposal") if isinstance(diagnostics, dict) else None
    if (
        wild
        or row.get("authority") != "learner"
        or row.get("semantic_action") != BattleAction.struggle().public_dict()
        or before[0][slot] <= 0
        or sum(hp > 0 for hp in before[0]) < 2
        or any(before[3][slot])
        or not isinstance(outcome, dict)
        or outcome.get("schema") != "pokemon.red.model-struggle-turn.v1"
        or outcome.get("authority") != "learner"
        or type(outcome.get("pp_spent")) is not int
        or outcome["pp_spent"] != 0
        or outcome.get("move_slot") is not None
        or outcome.get("departed_main_menu") is not True
        or roster_faints is None
        or not isinstance(diagnostics, dict)
        or diagnostics.get("control_choice") != "struggle"
        or not isinstance(proposal, dict)
        or proposal.get("schema") != "pokemon.red.model-struggle-proposal.v1"
        or proposal.get("semantic_action") != "pokemon.core:battle:struggle"
        or proposal.get("public_move_ref") != "pokemon.red.gb.us.rev0:move:165"
        or proposal.get("source_visible_pp") != [0, 0, 0, 0]
        or proposal.get("projection_pp") != [0.0]
        or proposal.get("ordinary_move_legal_mask") != [False]
        or proposal.get("observation_modified") is not False
        or proposal.get("supplied_action") is not False
    ):
        raise ValueError("model Struggle learned execution evidence required")
    _integer(row.get("policy_elapsed_ns"), 0, 2**63 - 1, "policy elapsed time")
    expected_reserves = [i + 1 for i, hp in enumerate(before[0]) if i != slot and hp > 0]
    if row.get("legal_party_slots") != expected_reserves:
        raise ValueError("model Struggle reserve evidence differs")
    selected = outcome.get("cartridge_selection_observed")
    suppression = outcome.get("suppression")
    if not (
        (selected is True and suppression is None
         and outcome.get("selected_move_ref") == "pokemon.red.gb.us.rev0:move:165"
         and outcome.get("execution_claim") == "attempt_only")
        or (selected is False and isinstance(suppression, str) and suppression
            and outcome.get("selected_move_ref") is None
            and outcome.get("execution_claim") == "suppressed_before_selection")
    ):
        raise ValueError("model Struggle cartridge selection evidence required")


def _disabled_struggle_evidence(row, before, after, slot):
    """Read the separately proved native singleton; never admit a TRAIN row."""
    state, outcome = row["state_before"], row["outcome"]
    encoded, disabled, turns = (
        outcome.get("encoded_pp_before"), outcome.get("disabled_move_slot"),
        outcome.get("disable_turns"),
    )
    if not (
        type(disabled) is int and 1 <= disabled <= 4
        and type(turns) is int and 1 <= turns <= 8
        and state.get("player_disabled_move_slot") == disabled
        and state.get("player_disable_turns") == turns
        and type(state.get("player_disabled_move_slot")) is int
        and type(state.get("player_disable_turns")) is int
        and isinstance(encoded, list) and len(encoded) == 4
        and all(type(pp) is int and 0 <= pp <= 255 for pp in encoded)
        and encoded[disabled - 1] & 63 > 0
        and all(pp == 0 for i, pp in enumerate(encoded) if i != disabled - 1)
        and encoded == state.get("active_pp")
        and [pp & 63 for pp in encoded] == before[3][slot]
        and after[3] == before[3]
        and state.get("active_party_slot") == slot + 1
        and state.get("active_hp") == before[0][slot]
        and state.get("battle_state") == 2
        and outcome.get("learned_choice") is False
        and outcome.get("train_admission_authorized") is False
        and outcome.get("move_slot") is None
        and outcome.get("departed_main_menu") is True
        and type(row.get("policy_elapsed_ns")) is int
        and type(outcome.get("frames_executed")) is int
        and outcome["frames_executed"] > 0
        and outcome["frames_executed"] == row.get("frames_executed")
    ):
        return False
    selected = (
        outcome.get("cartridge_selection_observed") is True
        and outcome.get("suppression") is None
        and outcome.get("selected_move_ref") == "pokemon.red.gb.us.rev0:move:165"
        and outcome.get("execution_claim") == "attempt_only"
    )
    status = state.get("active_status")
    suppressed = (
        outcome.get("cartridge_selection_observed") is False
        and outcome.get("selected_move_ref") is None
        and outcome.get("execution_claim") == "suppressed_before_selection"
        and type(status) is int
        and (
            (outcome.get("suppression") == "sleep" and bool(status & 7))
            or (outcome.get("suppression") == "freeze" and bool(status & 32))
            or (outcome.get("suppression") == "trapping"
                and state.get("enemy_using_trapping_move") is True)
        )
    )
    return selected or suppressed


def red_battle_aftermath(payload: bytes, *, expected_sha256: str) -> BattleAftermath:
    """Project observable evidence only; unknown outcomes stay unresolved.

    Supports the retained V4 trainer log. Unseen opponents are never filled from
    a cartridge roster. Species, map, move and snapshot identities never enter
    the returned semantic context. No winner labels for preparation are created.
    """
    if (
        not isinstance(payload, bytes)
        or len(payload) > 64 * 1024 * 1024
        or not isinstance(expected_sha256, str)
        or re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None
        or hashlib.sha256(payload).hexdigest() != expected_sha256
    ):
        raise ValueError("battle episode authentication failed")
    try:
        return _project(json.loads(payload))
    except (KeyError, TypeError, IndexError, AttributeError) as error:
        raise ValueError("incomplete battle episode evidence") from error


def _project(episode):
    if episode["schema"] != "pokemon.red.trainer-practice-model-episode.v4":
        raise ValueError("unsupported battle episode schema")
    decisions = episode["decisions"]
    if not isinstance(decisions, list) or not decisions:
        raise ValueError("observed battle decisions required")
    _integer(episode["decision_count"], 1, 100000, "decision count")
    if len(decisions) != episode["decision_count"]:
        raise ValueError("decision count differs")
    if type(episode["battle_won"]) is not bool or not isinstance(episode["stop_reason"], str):
        raise ValueError("explicit outcome evidence required")
    if episode["battle_won"] and episode["stop_reason"] == "party_defeated":
        raise ValueError("conflicting battle outcome")
    first = decisions[0]["observation"]["features"]["party"]
    size = first["count"]
    _integer(size, 1, 6, "party count")
    initial = _party(decisions[0]["state_before"], size)
    count = None
    battle_kind = None
    opponents, engaged = {}, {}
    actions = Counter()
    spent = suppressed = defeated = initially_defeated = 0
    for index, row in enumerate(decisions, 1):
        if type(row["decision_index"]) is not int or row["decision_index"] != index:
            raise ValueError("decision order differs")
        kind = row["kind"]
        if kind not in {
            "attack",
            "voluntary_switch",
            "forced_switch",
            "switch_prompt",
            "forced_struggle",
            "model_struggle",
        }:
            raise ValueError("unsupported battle decision")
        actions[kind] += 1
        features = row["observation"]["features"]
        battle, party = features["battle"], features["party"]
        if battle["active"] is not True or battle["kind"] not in {"trainer", "wild"}:
            raise ValueError("active battle evidence required")
        if battle_kind is not None and battle["kind"] != battle_kind:
            raise ValueError("battle kind changed inside episode")
        battle_kind = battle["kind"]
        wild = battle_kind == "wild"
        # Gen-I wild encounters have one opponent. Trainer roster/position RAM
        # is stale in this mode and must never supply invented wild opponents.
        total, remaining, level = (
            1 if wild else battle["opponent_party_count"],
            1 if wild else battle["opponent_remaining_count"],
            battle["opponent_level"],
        )
        _integer(total, 1, 6, "enemy roster")
        _integer(remaining, 1, total, "enemy remaining")
        if index == 1:
            initially_defeated = total - remaining
        if count is not None and count != total:
            raise ValueError("opponent roster changed")
        count = total
        if type(party["count"]) is not int or party["count"] != size:
            raise ValueError("own party changed")
        slot = party["active_index"]
        _integer(slot, 0, size - 1, "active member")
        before = _party(row["state_before"], size)
        after = _party(row["state_after"], size)
        roster_faints = None if wild else _trainer_roster_faints(row, total)
        # A resumed trainer can require replacing our already-fainted lead
        # before its first opponent is loaded. Native position 255 is not an
        # opponent identity: preserve the verified switch/costs, but do not
        # join the stale species/level left by an earlier encounter.
        unobserved_initial_foe = (
            not wild
            and index == 1
            and kind == "forced_switch"
            and type(row["state_before"].get("opponent_party_position")) is int
            and row["state_before"]["opponent_party_position"] == 255
            and before[0][slot] == 0
            and sum(after[0]) > 0
            and roster_faints == 0
            and type(row["state_after"].get("opponent_party_position")) is int
            and 0 <= row["state_after"]["opponent_party_position"] < total
        )
        if not unobserved_initial_foe:
            _integer(level, 1, 100, "enemy level")
            position = 0 if wild else observed_opponent_position(row)
            if position in opponents and opponents[position] != level:
                raise ValueError("conflicting repeated opponent")
            opponents[position] = level
        engaged.setdefault(slot, before[2][slot])
        spent += sum(
            max(0, x - y)
            for a, b in zip(before[3], after[3], strict=True)
            for x, y in zip(a, b, strict=True)
        )
        outcome = row.get("outcome")
        if kind == "attack":
            if not isinstance(outcome, dict) or type(outcome["move_executed"]) is not bool:
                raise ValueError("attack execution evidence required")
            suppressed += int(not outcome["move_executed"])
        if kind == "forced_struggle":
            pp_proved = not any(before[3][slot])
            if isinstance(outcome, dict) and outcome.get("availability_basis") is not None:
                pp_proved = (
                    outcome["availability_basis"] == "last_usable_move_disabled"
                    and _disabled_struggle_evidence(row, before, after, slot)
                )
            if (
                wild
                or not isinstance(outcome, dict)
                or row.get("authority") != "forced_mechanic"
                or row.get("policy_elapsed_ns") != 0
                or row.get("model_diagnostics") != {}
                or row.get("legal_party_slots") != []
                or before[0][slot] <= 0
                or sum(hp > 0 for hp in before[0]) != 1
                or not pp_proved
                or outcome.get("schema") != "pokemon.red.forced-struggle-turn.v1"
                or outcome.get("authority") != "forced_mechanic"
                or type(outcome.get("pp_spent")) is not int
                or outcome["pp_spent"] != 0
                or roster_faints is None
            ):
                raise ValueError("forced Struggle mechanical evidence required")
        elif kind == "model_struggle":
            _model_struggle_evidence(row, before, slot, wild=wild, roster_faints=roster_faints)
        elif outcome is not None and type(outcome["opponent_fainted"]) is not bool:
            raise ValueError("opponent faint evidence required")
        defeated += (
            roster_faints
            if roster_faints is not None
            else int(outcome["opponent_fainted"])
            if outcome is not None
            else 0
        )
    metrics = episode["metrics"]
    for key, value in (
        ("party_pp_spent", spent),
        ("opponent_faints", defeated),
        ("move_suppressed_or_failed", suppressed),
    ):
        if type(metrics[key]) is not int or metrics[key] != value:
            raise ValueError("episode metrics contradict decisions")
    # Native V4 logs include explicit zero counts for unused action kinds;
    # older retained logs omit them. Both describe the same observed decisions.
    declared_counts = episode["action_counts"]
    known_kinds = {
        "attack",
        "voluntary_switch",
        "forced_switch",
        "switch_prompt",
        "forced_struggle",
        "model_struggle",
    }
    if (
        not isinstance(declared_counts, dict)
        or not declared_counts.keys() <= known_kinds
        or any(type(value) is not int or value < 0 for value in declared_counts.values())
        or any(declared_counts.get(kind, 0) != actions[kind] for kind in known_kinds)
    ):
        raise ValueError("action counts contradict decisions")
    final = _party(decisions[-1]["state_after"], size)
    result = (
        BattleResult.WON
        if episode["battle_won"]
        else BattleResult.LOST
        if episode["stop_reason"] == "party_defeated"
        else BattleResult.UNRESOLVED
    )
    starting_pp = sum(map(sum, initial[3]))
    used_slots = [
        (x, y)
        for a, b in zip(initial[3], final[3], strict=True)
        for x, y in zip(a, b, strict=True)
        if x > 0
    ]
    last_hp = None
    last = decisions[-1]
    observed = last["observation"]["features"]["battle"]
    # After-state HP is only interpretable using this observed max HP if the
    # same opponent position remains. A replacement's health is not guessed.
    if not unobserved_initial_foe and (
        battle_kind == "wild"
        or (last["state_after"]["opponent_party_position"] == observed_opponent_position(last))
    ):
        maximum = observed["opponent_max_hp"]
        health = last["state_after"]["opponent_hp"]
        _integer(maximum, 1, 65535, "enemy maximum HP")
        _integer(health, 0, maximum, "enemy HP")
        last_hp = health / maximum
    # V4 switch rows have no attack outcome. A wild opponent can nevertheless
    # faint on that turn (for example, from recoil or Self-Destruct). Preserve
    # the authenticated attack-only metric above, and derive this one additional
    # knockout only from the terminal HP transition and verified native exit.
    if (
        battle_kind == "wild"
        and defeated == 0
        and result is BattleResult.WON
        and last["kind"] == "voluntary_switch"
        and last.get("outcome") is None
        and episode.get("final_battle_state") == 0
        and type(episode.get("final_battle_state")) is int
        and last_hp == 0
        and sum(final[0]) > 0
    ):
        _integer(last["state_before"]["opponent_hp"], 1, maximum, "enemy pre-switch HP")
        defeated = 1
    # A final simultaneous faint can settle after the selected-turn referee
    # snapshot. Preserve those attack metrics; authenticate the additional
    # last-member knockout from the retained native exit and terminal roster.
    terminal_roster = episode.get("final_enemy_roster_hp")
    previous_roster = last.get("referee_opponent_roster_hp_after")
    # Legacy ordinary-trainer switch rows have no selected attack outcome or
    # per-turn roster proof. A native exit, complete terminal roster and the
    # same observed living last foe becoming zero HP prove exactly one faint.
    # Preserve the original attack metrics; never fill unseen levels or foes.
    legacy_switch_faint = (
        last["kind"] == "voluntary_switch"
        and last.get("outcome") is None
        and previous_roster is None
        and type(last["state_before"]["opponent_hp"]) is int
        and last["state_before"]["opponent_hp"] > 0
        and type(last["state_after"]["opponent_hp"]) is int
        and last["state_after"]["opponent_hp"] == 0
    )
    delayed_roster_faint = (
        isinstance(previous_roster, list)
        and len(previous_roster) == count
        and sum(hp > 0 for hp in previous_roster) == 1
        and previous_roster[observed_opponent_position(last)] > 0
    ) if battle_kind == "trainer" and not unobserved_initial_foe else False
    if (
        battle_kind == "trainer"
        and result is BattleResult.WON
        and defeated + initially_defeated == count - 1
        and type(episode.get("final_battle_state")) is int
        and episode["final_battle_state"] == 0
        and observed["opponent_remaining_count"] == 1
        and (
            last_hp == 0
            or (legacy_switch_faint and last["state_after"]["opponent_party_position"] is None)
        )
        and sum(final[0]) > 0
        and isinstance(terminal_roster, list)
        and len(terminal_roster) == count
        and all(type(hp) is int and hp == 0 for hp in terminal_roster)
        and (legacy_switch_faint or delayed_roster_faint)
    ):
        if legacy_switch_faint:
            # Ordinary logs correctly clear the active position outside battle.
            # The authenticated complete zero roster proves the observed last
            # foe's zero health; do not join an arbitrary replacement position.
            maximum = observed["opponent_max_hp"]
            _integer(maximum, 1, 65535, "enemy maximum HP")
            _integer(last["state_before"]["opponent_hp"], 1, maximum, "enemy pre-switch HP")
            last_hp = 0.0
        defeated += 1
    return BattleAftermath(
        result,
        tuple(opponents[k] for k in sorted(opponents)),
        count,
        defeated + initially_defeated,
        tuple(engaged[k] for k in sorted(engaged)),
        size,
        final[0].count(0),
        sum(final[0]) / sum(final[1]),
        min(1.0, spent / starting_pp) if starting_pp else 0.0,
        sum(y == 0 for _, y in used_slots) / len(used_slots) if used_slots else 0.0,
        actions["voluntary_switch"] / len(decisions),
        suppressed / actions["attack"] if actions["attack"] else 0.0,
        last_hp,
    )
