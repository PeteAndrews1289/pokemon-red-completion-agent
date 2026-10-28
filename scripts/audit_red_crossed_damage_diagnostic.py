"""Read-only reconstruction of the crossed TRAIN diagnostic and category shortcut."""

import argparse
import json
from collections import Counter
from pathlib import Path
from statistics import fmean

import numpy as np
import run_red_crossed_damage_diagnostic as packet

old = packet.old


def audit(output: Path, prior: Path) -> dict:
    plan = json.loads((output / "PLAN.json").read_bytes())
    result = json.loads((output / "RESULT.json").read_bytes())
    packet.validate_crossing(plan["recipes"])
    catalog = packet.lab.PokemonRedBattleCatalog()
    candidate = json.loads((prior / "candidate-model.json").read_bytes())["damage_reference"]
    k = json.loads(old.K.read_bytes())["move"]
    targets, event_count = [], 0
    cost = Counter()
    for recipe in plan["recipes"]:
        directory = output / recipe["id"]
        target = json.loads((directory / "target.json").read_bytes())
        assert json.loads((directory / "setup.json").read_bytes())["recipe"] == recipe
        assert target["root"] == recipe["root"]
        assert old.sha(directory / "capture.state") == target["capture_sha256"]
        assert {(b["slot"], b["offset"]) for b in target["branches"]} == {
            (s, o) for s in range(1, 5) for o in old.OFFSETS
        }
        for branch in target["branches"]:
            path = directory / f"branch-{branch['offset']}-{branch['slot']}"
            episode = json.loads((path / "episode.json").read_bytes())
            assert old.sha(path / "episode.json") == branch["episode_sha256"]
            assert len(episode["decisions"]) == 1
            decision = episode["decisions"][0]
            assert decision["kind"] == "attack" and decision["move_slot"] == branch["slot"]
            assert decision["model_input"]["legal_mask"] == [True] * 4
            obs = decision["observation"]
            projected = old.project_trainer_move_features(
                obs, packet.lab.BattleFeatureProjector(catalog).project(obs)
            )
            np.testing.assert_allclose(
                projected.candidate_vectors, target["vectors"], atol=1e-12, rtol=0
            )
            cap = obs["features"]["battle"]["opponent_max_hp"]
            damage = (decision["opponent_hp_before"] - decision["opponent_hp_after"]) / cap
            assert abs(damage - branch["damage_fraction"]) <= 1e-12
            endpoint = json.loads((path / "final-state.json").read_bytes())
            assert old.sha(path / "final.state") == endpoint["state_sha256"]
            assert 0 < endpoint["completed_actions"] <= endpoint["attempted_actions"] <= 5000
            for key in result["costs"]:
                cost[key] += endpoint[key]
            previous = None
            for sequence, event_path in enumerate(
                sorted((path / "events").glob("event-*.json")), 1
            ):
                event = json.loads(event_path.read_bytes())
                digest = event.pop("record_sha256")
                assert event["sequence"] == sequence and event["previous_sha256"] == previous
                assert packet.lab.canonical_sha256(event) == digest
                previous = digest
                event_count += 1
            assert previous is not None and event["payload"]["event"] == "run_finished"
            assert event["payload"]["outcome"]["episode_sha256"] == packet.lab.canonical_sha256(
                episode
            )
        means = [
            fmean(b["damage_fraction"] for b in target["branches"] if b["slot"] == slot)
            for slot in range(1, 5)
        ]
        np.testing.assert_allclose(means, target["mean_damage"], atol=1e-12, rtol=0)
        for name, head in (("K", k), ("rejected", candidate)):
            # Independent matrix evaluation, not the production scores/predict helpers.
            scores = np.tanh(
                np.asarray(target["vectors"]) @ np.asarray(head["weights1"])
                + np.asarray(head["bias1"])
            ) @ np.asarray(head["weights2"])
            choice = target["choices"][name]
            pick = int(np.argmax(scores))
            np.testing.assert_allclose(scores, choice["scores"], atol=1e-12, rtol=0)
            assert pick + 1 == choice["slot"]
            assert abs(max(means) - means[pick] - choice["regret"]) <= 1e-12
        targets.append(target)
    assert packet.summarize(targets) == {key: result[key] for key in packet.summarize(targets)}
    for key, value in cost.items():
        assert abs(value - result["costs"][key]) <= 1e-9
    for path, digest in plan["protected_inputs"].items():
        assert old.sha(Path(path)) == digest
    for path, digest in plan["source_overlay_sha256"].items():
        source = output / "executed-source" / path
        assert old.sha(source if source.exists() else old.ROOT / path) == digest
    at = old.MOVE_FEATURE_NAMES.index("move.category.special")
    shortcut = {}
    for name, rows in (
        ("original_train", json.loads((prior / "train-targets.json").read_bytes())),
        ("opened_original_holdout", json.loads((prior / "holdout-targets.json").read_bytes())),
        ("crossed_diagnostic", targets),
    ):
        picked_special, special_among_best, strict_best = 0, 0, 0
        for row in rows:
            x = np.asarray(row["vectors"])
            score = (
                np.tanh(x @ np.asarray(candidate["weights1"]) + candidate["bias1"])
                @ candidate["weights2"]
            )
            pick = int(np.argmax(score))
            best = max(row["mean_damage"])
            picked_special += int(x[pick, at] == 1)
            special_among_best += int(
                any(
                    x[i, at] == 1 and abs(value - best) <= 1e-12
                    for i, value in enumerate(row["mean_damage"])
                )
            )
            strict_best += int(abs(row["mean_damage"][pick] - best) <= 1e-12)
        shortcut[name] = {
            "configurations": len(rows),
            "picked_special": picked_special,
            "special_among_strict_best": special_among_best,
            "strict_best_choices": strict_best,
        }
    return {
        "passed": True,
        "branches_verified": 768,
        "event_records_verified": event_count,
        "raw_projection_width": len(old.MOVE_FEATURE_NAMES),
        "actual_costs": dict(cost),
        "category_shortcut": shortcut,
        "protected_inputs_unchanged": True,
        "limitation": (
            "Crossed families favor special attacks; "
            "do not use their aggregate to overturn rejection."
        ),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prior", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.output, args.prior)
    old.write_once(args.report, report)
    print(json.dumps(report, indent=2))
