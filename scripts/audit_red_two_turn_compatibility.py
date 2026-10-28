"""Read-only two-turn trace reconstruction, including incomplete failed prefixes."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import audit_red_damage_composition as full_audit
import run_red_two_turn_compatibility as packet
from audit_red_interaction_damage_successor import _audit_events, _audit_source

read, require, old = packet.read, packet.require, packet.old


def trace_counts(records, row, episode):
    counts = Counter()
    latest = None
    by_index = {}
    active_index = None
    for event in records:
        kind = event["event"]
        if kind == "two_turn_observed":
            require(latest is None or event["frame"] > latest["frame"], "telemetry frame order")
            latest = event
            counts["sampled_actions"] += 1
            charge = event["charge"]
            if charge.get("opponent_charging") and not row["player_charge"]:
                counts[f"enemy_charge_samples_{row['charge_move']}"] += 1
            if active_index is not None:
                by_index.setdefault(active_index, []).append(event)
        elif kind == "choice_recorded":
            active_index = event["decision_index"]
            counts["recorded_choices"] += 1
            if latest and latest["charge"].get("player_charging") and latest["player_hp"] > 0:
                counts["choices_during_charge"] += 1
        elif kind == "decision_completed":
            active_index = None
    for d in episode["decisions"]:
        if d["kind"] != "attack":
            continue
        moves = {
            m["slot_index"] + 1: int(m["move_ref"][-3:])
            for m in d["observation"]["features"]["party"]["lead"]["moves"]
        }
        move = moves[d["move_slot"]]
        if move not in {19, 91}:
            continue
        counts[f"selected_{move}"] += 1
        samples = by_index.get(d["decision_index"], [])
        charging = [s for s in samples if s["charge"].get("player_charging")]
        before = d["state_before"]["active_pp"]
        # A native post-battle heal can restore PP and clear the active index.
        # Prove the spend from the retained in-battle sample, never that healed endpoint.
        live = [
            s
            for s in samples
            if s["charge"].get("active")
            and s["player_slot"] == d["state_before"]["active_party_slot"] - 1
        ]
        require(live, "charge lacks live PP evidence")
        after = live[-1]["player_pp"]
        require(
            d["outcome"].get("battle_exited")
            or d["state_before"]["active_party_slot"] == d["state_after"]["active_party_slot"],
            "charge unexpectedly changed battler",
        )
        spent = before[d["move_slot"] - 1] - after[d["move_slot"] - 1]
        require(spent == int(d["outcome"]["move_executed"]), "charge PP outcome mismatch")
        require(
            all(
                a == b
                for i, (a, b) in enumerate(zip(before, after, strict=True), 1)
                if i != d["move_slot"]
            ),
            "charge spent another slot",
        )
        if charging:
            counts[f"observed_player_charge_{move}"] += 1
            require(all(s["player_pp"] == before for s in charging), "PP spent while charging")
            if (
                samples
                and samples[-1]["charge"].get("player_charging")
                and samples[-1]["player_hp"] > 0
            ):
                counts["completed_while_charging"] += 1
            counts["observed_charge_release" if spent else "observed_charge_interruption"] += 1
        counts["charge_no_damage"] += d["opponent_hp_after"] == d["opponent_hp_before"]
        counts["charge_spent_pp"] += spent
    return counts


def audit_arm(path, row, arm, offset, model, catalog):
    has_episode = (path / "episode.json").exists()
    events = sorted((path / "events").glob("event-*.json"))
    require(events, "claimed arm has no event log")
    records = [read(p)["payload"] for p in events]
    _audit_events(path, "run_finished" if has_episode else "run_failed")
    identity = records[0]["identity"]
    require(
        identity["partition"] == "train"
        and identity["root"] == row["root"]
        and identity["model_sha256"] == old.lab.canonical_sha256(model.to_dict())
        and identity["offset"] == offset
        and identity["two_turn_telemetry"] is True
        and identity["first_slot"] == (1 if arm == "probe" else None)
        and identity["horizon"] == (1 if arm == "probe" else None),
        "actor binding differs",
    )
    completed = [e["decision"] for e in records if e["event"] == "decision_completed"]
    episode = (
        read(path / "episode.json")
        if has_episode
        else {"capture_id": identity["capture_id"], "decisions": completed}
    )
    require(episode["decisions"] == completed, "event/episode join")
    if arm != "probe":
        behavior = full_audit.audit_decisions(episode, model, catalog)
    else:
        behavior = Counter()
        require(len(completed) <= 1, "probe owns more than one choice")
        for d in completed:
            require(
                d["kind"] == "attack" and d["move_slot"] == 1,
                "forced execution probe choice differs",
            )
            require(
                d["observation_sha256"] == old.lab.canonical_sha256(d["observation"]),
                "probe observation hash",
            )
            require(
                full_audit.prepared_from_observation(
                    d["observation"], catalog
                ).supported_candidate_mask[0],
                "forced move illegal",
            )
    counts = trace_counts(records, row, episode)
    counts["selected_move_pp_spends"] = sum(
        d["kind"] == "attack" and d["outcome"]["move_executed"] for d in completed
    )
    counts.update(
        {
            "events": len(records),
            "completed_decisions": len(completed),
            "learned_completed_decisions": len(completed) if arm != "probe" else 0,
            "forced_completed_decisions": len(completed) if arm == "probe" else 0,
            "completed_episodes": int(has_episode),
            "failed_episodes": int(not has_episode),
        }
    )
    terminal = read(path / "final-state.json")
    require(old.sha(path / "final.state") == terminal["state_sha256"], "terminal hash")
    require(
        terminal["completed_actions"] <= terminal["attempted_actions"] <= 5000
        and terminal["frame_delta"] <= 120000,
        "native cost cap",
    )
    # On failure the last interrupted macro may lack its post-action telemetry.
    require(counts["sampled_actions"] <= terminal["completed_actions"], "telemetry count")
    if has_episode:
        require(
            counts["sampled_actions"] == terminal["completed_actions"], "missing action telemetry"
        )
        require(terminal["wall_elapsed_seconds"] <= 45, "native wall cap")
        require(
            episode["memory_write_actions"] == episode["teacher_queries"] == 0, "teacher action"
        )
    counts.update(
        {
            "controller_actions": terminal["completed_actions"],
            "attempted_actions": terminal["attempted_actions"],
            "frames": terminal["frame_delta"],
            "own_faints": behavior["own_faints"],
        }
    )
    return counts


def audit(output):
    plan = read(output / "PLAN.json")
    _audit_source(plan)
    for path, digest in plan["protected_inputs"].items():
        require(old.sha(Path(path)) == digest, "protected input changed")
    cartridge, catalog, sources, _, admitted = old.inputs()
    candidate = old.TrainerPracticeThreeHeadModel.from_dict(read(packet.composition.CANDIDATE))
    packet.composition.assert_models(admitted, candidate)
    require(plan["rows"] == packet.recipes(cartridge, catalog, sources), "recipe reconstruction")
    totals = {a: Counter() for a in ("probe", "admitted", "candidate")}
    pairs = []
    claims = []
    for row in plan["rows"]:
        directory = output / row["id"]
        if directory.exists():
            require(read(directory / "setup.json")["recipe"] == row, "setup binding")
        for offset in packet.OFFSETS:
            arms = (["probe"] if row["player_charge"] else []) + plan["orders"][
                f"{row['id']}:{offset}"
            ]
            for arm in arms:
                path = directory / f"offset-{offset}-{arm}"
                claim_path = path.with_suffix(".claim.json")
                if not claim_path.exists():
                    continue
                claim = read(claim_path)
                require(
                    claim["plan_sha256"] == old.sha(output / "PLAN.json")
                    and claim["elapsed_seconds"] < packet.MAX_SECONDS,
                    "claim cap/binding",
                )
                claims.append(claim)
                totals[arm].update(
                    audit_arm(
                        path,
                        row,
                        arm,
                        offset,
                        admitted if arm == "admitted" else candidate,
                        catalog,
                    )
                )
            pair_path = directory / f"pair-{offset}.json"
            if pair_path.exists():
                pair = read(pair_path)
                require(pair["row"] == row["id"] and pair["offset"] == offset, "pair identity")
                for arm in ("admitted", "candidate"):
                    path = directory / f"offset-{offset}-{arm}"
                    ep, term = read(path / "episode.json"), read(path / "final-state.json")
                    metrics = old._composition_metrics(ep, path)
                    metrics.update(
                        {
                            "actual_frames": term["frame_delta"],
                            "actual_actions": term["completed_actions"],
                            "terminal_sha256": term["state_sha256"],
                        }
                    )
                    require(metrics == pair[arm], "paired metrics differ")
                pairs.append(pair)
    failed = (output / "FAILURE.json").exists()
    failures = []
    corrected_spend_summary = None
    if failed:
        failure = read(output / "FAILURE.json")
        require(
            failure["completed_pairs"] == len(pairs)
            and failure["active"] == {k: claims[-1][k] for k in ("row", "offset", "arm")},
            "failure identity",
        )
        failures.append("native_packet_interrupted")
    else:
        result = read(output / "RESULT.json")
        require(
            len(claims) == 64 and len(pairs) == 24 and result["pairs"] == pairs,
            "complete inventory differs",
        )
        summary = packet.summarize(pairs)
        require(all(result[k] == v for k, v in summary.items()), "result reaggregation")
        failures.extend(summary["behavior_failures"])
        corrected_pairs = []
        for pair in pairs:
            corrected = dict(pair)
            for arm in ("admitted", "candidate"):
                ep = read(output / pair["row"] / f"offset-{pair['offset']}-{arm}" / "episode.json")
                corrected[arm] = {
                    **pair[arm],
                    "pp_spent": sum(
                        d["kind"] == "attack" and d["outcome"]["move_executed"]
                        for d in ep["decisions"]
                    ),
                }
            corrected_pairs.append(corrected)
        corrected_spend_summary = packet.summarize(corrected_pairs)
        failures.extend(f"actual_spend_{f}" for f in corrected_spend_summary["behavior_failures"])
    for a, counts in totals.items():
        if counts["choices_during_charge"] or counts["completed_while_charging"]:
            failures.append(f"{a}_charge_boundary")
    for move in (19, 91):
        if not sum(c[f"observed_player_charge_{move}"] for c in totals.values()):
            failures.append(f"player_charge_{move}_unobserved")
        if not sum(c[f"enemy_charge_samples_{move}"] for c in totals.values()):
            failures.append(f"enemy_charge_{move}_unobserved")
        if not totals["candidate"][f"selected_{move}"]:
            failures.append(f"candidate_move_{move}_unselected")
    return {
        "schema": "pokemon.red.two-turn-compatibility-audit.v1",
        "audit_passed": True,
        "compatibility_passed": not failures,
        "gate_failures": failures,
        "counts": totals,
        "claimed_arms": len(claims),
        "completed_pairs": len(pairs),
        "plan_sha256": old.sha(output / "PLAN.json"),
        "result_sha256": old.sha(output / "RESULT.json") if not failed else None,
        "failure_sha256": old.sha(output / "FAILURE.json") if failed else None,
        "audit_source_sha256": old.sha(Path(__file__)),
        "protected_inputs_unchanged": True,
        "fits": 0,
        "promotions": 0,
        "story_actions": 0,
        "actual_spend_summary": corrected_spend_summary,
        "audit_correction": "Original endpoint PP depletion can hide a final spend when native "
        "post-battle healing restores PP. Charge proof uses live telemetry; "
        "report selected-move spends separately, retaining original results.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=packet.OUTPUT)
    args = parser.parse_args()
    report = audit(args.output)
    old.write_once(args.output / "AUDIT.json", report)
    print(json.dumps(report))
