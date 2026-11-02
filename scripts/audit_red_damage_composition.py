"""Independently replay frozen composition choices from retained observations, no frames."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import replace
from pathlib import Path
from statistics import fmean

import run_red_damage_composition as packet
from audit_red_interaction_damage_successor import _audit_events, _audit_source

from pokemon_red_completion.battle_scenario_capture import open_battle_scenario_capture
from pokemon_red_completion.battle_semantics import BattleFeatureProjector
from pokemon_red_completion.red_battle_scenario import (
    PreparedRedBattleScenario,
    red_battle_move_unsupported_reason,
)
from pokemon_red_completion.red_trainer_practice_episode import _main_model_input
from pokemon_red_completion.red_trainer_practice_outcome_policy import (
    RedTrainerPracticeOutcomePolicy,
)

read, require, old = packet.read, packet.require, packet.old


def opponent_faints(decision):
    """Use roster deltas, or the explicit final KO when battle exit clears that roster."""
    before = decision.get("referee_opponent_roster_hp_before")
    after = decision.get("referee_opponent_roster_hp_after")
    if before is not None and after is not None:
        return sum(a > 0 and b == 0 for a, b in zip(before, after, strict=True))
    outcome = decision.get("outcome", {})
    require(
        decision["kind"] == "attack"
        and outcome.get("battle_exited") is True
        and outcome.get("opponent_fainted") is True
        and decision["state_before"]["opponent_hp"] > 0
        and decision["state_after"]["opponent_hp"] == 0,
        "missing roster without authenticated final knockout",
    )
    return 1


def prepared_from_observation(observation, catalog):
    batch = BattleFeatureProjector(catalog, mask_counter_without_prior_damage=True).project(
        observation
    )
    moves = observation["features"]["party"]["lead"]["moves"]
    by_slot = {m["slot_index"] + 1: m for m in moves}
    reasons = []
    for slot, legal, pp in zip(batch.slot_indices, batch.legal_mask, batch.current_pp, strict=True):
        move = by_slot[slot + 1]
        reason = red_battle_move_unsupported_reason(int(move["move_ref"][-3:]), pp, catalog=catalog)
        if reason == "status_or_non_damaging_outside_segment" and catalog.status_move_supported(
            move["move_ref"]
        ):
            reason = None
        if reason is None and not legal:
            reason = "disabled_or_mechanically_illegal"
        reasons.append(reason)
    return PreparedRedBattleScenario(
        old.lab.canonical_sha256(observation),
        replace(batch, legal_mask=tuple(r is None for r in reasons)),
        allow_no_attack=True,
        unsupported_candidate_reasons=tuple(reasons),
    )


def audit_decisions(episode, model, catalog):
    policy = RedTrainerPracticeOutcomePolicy("status-experiment", episode["capture_id"], model)
    counts = Counter()
    for d in episode["decisions"]:
        observation = d["observation"]
        require(
            old.lab.canonical_sha256(observation) == d["observation_sha256"], "observation hash"
        )
        kind = d["kind"]
        before, after = d["state_before"], d["state_after"]
        counts["decisions"] += 1
        counts[kind] += 1
        counts["policy_nanoseconds"] += d["policy_elapsed_ns"]
        counts[f"active_slot_{before['active_party_slot']}"] += 1
        if kind in {"forced_switch", "switch_prompt"}:
            forced = kind == "forced_switch"
            selected = policy.choose_switch(
                observation, tuple(d["legal_party_slots"]), forced=forced, may_decline=not forced
            )
            require(selected == d["party_slot"], "replayed replacement differs")
            require(selected is None or selected in d["legal_party_slots"], "illegal replacement")
        else:
            prepared = prepared_from_observation(observation, catalog)
            require(_main_model_input(prepared) == d["model_input"], "reprojected inputs differ")
            action = policy.choose_main(observation, prepared)
            require(
                (kind == "attack" and action.move_slot == d["move_slot"])
                or (kind == "voluntary_switch" and action.party_slot == d["party_slot"]),
                "replayed main choice differs",
            )
            moves = {
                m["slot_index"] + 1: m for m in observation["features"]["party"]["lead"]["moves"]
            }
            status_slots = {
                slot + 1
                for slot, legal in zip(
                    prepared.features.slot_indices, prepared.supported_candidate_mask, strict=True
                )
                if legal and catalog.resolve_move(moves[slot + 1]["move_ref"]).category == "status"
            }
            counts["main_with_legal_status"] += bool(status_slots)
            if kind == "attack":
                require(prepared.supported_candidate_mask[d["move_slot"] - 1], "illegal attack")
                counts["status_choices"] += d["move_slot"] in status_slots
                counts["suppressed_or_failed"] += not d["outcome"]["move_executed"]
            else:
                require(action.party_slot in d["legal_party_slots"], "illegal voluntary switch")
        require(
            policy.last_decision_diagnostics == d["model_diagnostics"], "model diagnostics differ"
        )
        policy.observe_opponent_transition(
            before["opponent_party_position"], after["opponent_party_position"]
        )
        counts["own_faints"] += sum(
            a > 0 and b == 0 for a, b in zip(before["party_hp"], after["party_hp"], strict=True)
        )
        counts["pp_spent"] += sum(
            max(0, a - b)
            for arow, brow in zip(before["party_pp"], after["party_pp"], strict=True)
            for a, b in zip(arow, brow, strict=True)
        )
        counts["opponents_defeated"] += opponent_faints(d)
    return counts


def audit_arm(directory, expected, team, offset, model, catalog):
    episode = read(directory / "episode.json")
    terminal = read(directory / "final-state.json")
    require(old.sha(directory / "episode.json") == expected["episode_sha256"], "episode binding")
    require(
        old.sha(directory / "final.state")
        == terminal["state_sha256"]
        == expected["terminal_sha256"],
        "terminal binding",
    )
    events = _audit_events(directory, "run_finished")
    records = [read(p)["payload"] for p in sorted((directory / "events").glob("event-*.json"))]
    require(
        [e["decision"] for e in records if e["event"] == "decision_completed"]
        == episode["decisions"],
        "episode/event decision join",
    )
    identity = records[0]["identity"]
    capture = open_battle_scenario_capture(
        directory.parent / "capture.state", directory.parent / "capture.state.json"
    )
    require(
        identity["capture_id"] == capture.manifest.capture_id == episode["capture_id"]
        and identity["root"] == capture.manifest.root_lineage_id == team["root"]
        and identity["model_sha256"] == old.lab.canonical_sha256(model.to_dict())
        and identity["first_slot"] is None
        and identity["horizon"] is None
        and identity["learner_continuation"]
        and identity["allow_status_moves"]
        and identity["partition"] == "train"
        and identity["offset"] == episode["opening_idle_frames"] == offset,
        "full learner identity differs",
    )
    require(
        not episode["teacher_queries"] and not episode["memory_write_actions"], "teacher action"
    )
    require(
        0 < terminal["completed_actions"] <= terminal["attempted_actions"] <= 5000
        and terminal["frame_delta"] <= 120000
        and terminal["wall_elapsed_seconds"] <= 45
        and episode["decision_count"] <= 80,
        "arm ceiling exceeded",
    )
    stop = episode["stop_reason"]
    require(episode["battle_won"] == (stop == "battle_won"), "win flag differs")
    require(
        old.lab.canonical_sha256(episode["final_observation"])
        == episode["final_observation_sha256"],
        "final observation hash differs",
    )
    if stop == "battle_won":
        require(
            episode["final_battle_state"] == 0
            and episode["final_enemy_roster_hp"]
            and not any(episode["final_enemy_roster_hp"]),
            "win lacks all-foe defeat",
        )
    if stop == "party_defeated":
        require(
            not any(episode["decisions"][-1]["state_after"]["party_hp"]),
            "loss lacks own-party defeat",
        )
    require(stop in packet.CENSORED_STOPS | {"battle_won", "party_defeated"}, "unexpected terminal")
    if (directory / "failure.json").exists():
        require(
            stop in packet.CENSORED_STOPS
            and read(directory / "failure.json")
            == {"type": "ValueError", "error": f"unsupported stop {stop}"},
            "unexpected arm error",
        )
    counts = audit_decisions(episode, model, catalog)
    for metric, key in (
        ("party_faints", "own_faints"),
        ("party_pp_spent", "pp_spent"),
        ("opponent_faints", "opponents_defeated"),
    ):
        require(episode["metrics"][metric] == counts[key], "reconstructed resources differ")
    measured = old._composition_metrics(episode, directory)
    measured.update(
        {
            "actual_actions": terminal["completed_actions"],
            "attempted_actions": terminal["attempted_actions"],
            "actual_frames": terminal["frame_delta"],
            "terminal_sha256": terminal["state_sha256"],
        }
    )
    require(measured == expected, "paired measurements differ")
    counts.update(
        {
            "event_records": events,
            "actual_actions": terminal["completed_actions"],
            "attempted_actions": terminal["attempted_actions"],
            "actual_frames": terminal["frame_delta"],
            "repeat_state_action_loops": expected["repeat_state_action_loops"],
        }
    )
    return counts


def independent_gate(pairs):
    failures = []

    def total(arm, key):
        return sum(p[arm][key] for p in pairs)

    require(
        len(pairs) == 72 and len({(p["team_id"], p["offset"]) for p in pairs}) == 72,
        "comparison inventory",
    )
    if any(p[a]["invalid_action_failures"] for p in pairs for a in ("admitted", "candidate")):
        failures.append("illegal_action")
    for key, failure in (("censored", "censored_increase"), ("loss", "loss_increase")):
        if total("candidate", key) > total("admitted", key):
            failures.append(failure)
    if total("candidate", "win") < total("admitted", "win"):
        failures.append("win_decrease")
    if not (
        total("candidate", "win") > total("admitted", "win")
        or total("candidate", "opponents_defeated") > total("admitted", "opponents_defeated")
        or fmean(
            p["candidate"]["normalized_terminal_hp"] - p["admitted"]["normalized_terminal_hp"]
            for p in pairs
        )
        >= 0.02
    ):
        failures.append("no_strict_gain")
    common = [p for p in pairs if p["admitted"]["win"] and p["candidate"]["win"]]
    if not common:
        failures.append("common_win_efficiency_unassessed")
    elif any(
        total_common(common, "admitted", key) <= 0
        or total_common(common, "candidate", key) / total_common(common, "admitted", key) - 1 > 0.10
        for key in ("turns", "pp_spent")
    ):
        failures.append("common_win_efficiency_regression")
    return failures


def total_common(pairs, arm, key):
    return sum(p[arm][key] for p in pairs)


def audit(output):
    plan, result = read(output / "PLAN.json"), read(output / "RESULT.json")
    require(not (output / "FAILURE.json").exists(), "incomplete native packet")
    _audit_source(plan)
    for path, digest in plan["protected_inputs"].items():
        require(old.sha(Path(path)) == digest, "protected input changed")
    require(
        result["plan_sha256"] == old.sha(output / "PLAN.json")
        and result["candidate_model_sha256"] == packet.CANDIDATE_SHA
        and result["admitted_model_sha256"] == old.sha(old.ADMITTED),
        "result bindings",
    )
    cartridge, catalog, sources, _, admitted = old.inputs()
    candidate = old.TrainerPracticeThreeHeadModel.from_dict(read(packet.CANDIDATE))
    packet.assert_models(admitted, candidate)
    coverage = packet.validate_teams(
        plan["teams"], cartridge, catalog, sources, packet.exclusions()
    )
    require(coverage == plan["coverage"], "coverage differs")
    require(
        plan["teams"] == packet.build_teams(cartridge, catalog, sources, packet.exclusions()),
        "prospective recipe differs",
    )
    totals = {arm: Counter() for arm in ("admitted", "candidate")}
    pairs = []
    for team in plan["teams"]:
        require(read(output / team["id"] / "setup.json")["recipe"] == team, "setup recipe differs")
        for offset in packet.OFFSETS:
            pair = read(output / team["id"] / f"pair-{offset}.json")
            require(
                pair["arm_order"] == plan["orders"][f"{team['id']}:{offset}"]
                and pair["offset"] == offset
                and pair["root"] == team["root"]
                and pair["team_id"] == team["id"],
                "pair inventory differs",
            )
            for arm in pair["arm_order"]:
                directory = output / team["id"] / f"offset-{offset}-{arm}"
                claim = read(directory.with_suffix(".claim.json"))
                require(
                    claim["plan_sha256"] == result["plan_sha256"]
                    and claim["team"] == team["id"]
                    and claim["offset"] == offset
                    and claim["arm"] == arm
                    and claim["elapsed_seconds"] < packet.MAX_SECONDS,
                    "dispatch binding/cap",
                )
                totals[arm].update(
                    audit_arm(
                        directory,
                        pair[arm],
                        team,
                        offset,
                        admitted if arm == "admitted" else candidate,
                        catalog,
                    )
                )
            pairs.append(pair)
    require(result["pairs"] == pairs, "result/pair join")
    require(
        result["gate_failures"] == independent_gate(pairs)
        and result["provisional_review_gate_passed"] == (not independent_gate(pairs)),
        "independent gate differs",
    )
    rebuilt = old.score_composition(
        pairs,
        plan,
        bindings={
            k: result[k] for k in ("plan_sha256", "admitted_model_sha256", "candidate_model_sha256")
        },
    )
    require(
        {k: v for k, v in result.items() if k != "native_elapsed_seconds"} == rebuilt,
        "result aggregate differs",
    )
    return {
        "schema": "pokemon.red.frozen-damage-composition-audit.v1",
        "passed": True,
        "result_sha256": old.sha(output / "RESULT.json"),
        "plan_sha256": old.sha(output / "PLAN.json"),
        "counts": totals,
        "gate_failures": result["gate_failures"],
        "composition_passed": result["provisional_review_gate_passed"],
        "independent_new_roots": 0,
        "fits": 0,
        "promotions": 0,
        "audit_source_sha256": old.sha(Path(__file__)),
        "audit_only_correction": "Account for the final knockout after battle exit clears roster; "
        "unchanged native plan, observations, models and outcomes.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=packet.OUTPUT)
    args = parser.parse_args()
    report = audit(args.output)
    old.write_once(args.output / "AUDIT.json", report)
    print(json.dumps(report))
