"""Independent outcome-pilot audit; never fit, play, or open reserved comparisons."""

import argparse
import json
from pathlib import Path

import numpy as np
import run_red_outcome_value_pilot as pilot
from audit_red_closed_loop_status import (
    BattleFeatureProjector,
    PokemonRedBattleCatalog,
    project_balanced_status_moves,
    status_choice_slots,
)
from audit_red_status_learning import audit

from pokemon_red_completion.red_status_battle_features import STATUS_MOVE_NAMES
from pokemon_red_completion.red_status_retention_fit import group_metrics

combined = pilot.combined
loop, lab = combined.loop, combined.lab


def metrics_equal(left, right):
    return (left.keys() == right.keys() and all(
        abs(left[k]-right[k]) <= 1e-10 if k == "regret" else left[k] == right[k]
        for k in left))


def verify_frozen(candidate, actor, targets, *, allow_hidden=False):
    hidden_changed = (not np.array_equal(candidate.move.weights1, actor.move.weights1) or
                      not np.array_equal(candidate.move.bias1, actor.move.bias1))
    if (candidate.control.to_dict() != actor.control.to_dict() or
            candidate.switch.to_dict() != actor.switch.to_dict() or
            candidate.damage_reference.to_dict() != actor.damage_reference.to_dict() or
            candidate.train_root_ids != actor.train_root_ids or
            candidate.move.weights1.shape != actor.move.weights1.shape or
            np.count_nonzero(candidate.move.weights1[:len(STATUS_MOVE_NAMES)]) or
            (not allow_hidden and hidden_changed) or
            candidate.move.effect_weights != actor.move.effect_weights or
            candidate.move.effect_sha256 != actor.move.effect_sha256 or
            set(candidate.train_capture_ids) !=
            {*actor.train_capture_ids, *(t["capture_id"] for t in targets)}):
        raise ValueError("fitted checkpoint changed frozen components or target ancestry")


def verify_choices(directory, actor, frozen):
    """Recompute every learned attack, including forced-first branch continuations."""
    count = 0
    projector = BattleFeatureProjector(PokemonRedBattleCatalog())
    for path in sorted(directory.glob("**/episode.json")):
        identity = loop.load(path.parent / "events/event-00001.json")["payload"]["identity"]
        if identity["model_sha256"] != loop.canonical_sha256(actor.to_dict()):
            raise ValueError("trajectory actor binding differs")
        episode = loop.load(path)
        for index, step in enumerate(episode["decisions"]):
            if index == 0 and identity["first_slot"] is not None:
                if step["move_slot"] != identity["first_slot"]:
                    raise ValueError("forced branch action differs")
                continue
            if step["kind"] != "attack":
                raise ValueError("single-member pilot contains an unaudited non-attack")
            obs = step["observation"]
            view = project_balanced_status_moves(obs, projector.project(obs))
            slots = status_choice_slots(view, tuple(step["legal_move_slots"]), frozen.move)
            vectors = [view.candidate_vectors[view.candidate_slots.index(s)] for s in slots]
            if step["move_slot"] != slots[actor.move.predict_index(vectors)]:
                raise ValueError("native learned choice differs from checkpoint")
            count += 1
    return count


def inspect(root, directory):
    plan, result = loop.load(directory / "plan.json"), loop.load(directory / "result.json")
    bind = lab.common._binding
    if bind(Path(plan["actor"]["path"])) != plan["actor"]:
        raise ValueError("pilot actor changed")
    actor = combined.model(Path(plan["actor"]["path"]))
    _, inputs, originals, initial, frozen = combined.previous.load_inputs(root)
    if loop.canonical_sha256(inputs) != plan["inputs_sha256"]:
        raise ValueError("original input bindings differ")
    prior = root / "red-native-later-effect-qualification-20260922-v1/combination/plan.json"
    original_plan = loop.load(prior)
    groups = combined.validate_view(Path(original_plan["reward"]["path"]), root)["groups"]
    basis = combined.model(Path(original_plan["prior"]["path"]))
    effect = loop.load(Path(original_plan["effect"]["path"]))
    problem = combined.prepare_combination(groups, initial, frozen, basis, originals, effect)
    retained = []
    for binding in plan.get("retained_train_inputs", []):
        path = Path(binding["path"])
        if bind(path) != binding:
            raise ValueError("retained TRAIN input differs")
        if path.name == "target.json":
            retained.append(loop.load(path))
    if retained:
        problem = pilot.extend_problem(problem, actor, retained)
        groups = [*groups, retained]
    targets = [loop.load(p) for p in sorted((directory / "targets").glob("*/target.json"))]
    coverage = loop.load(directory / "coverage.json")
    measured = [r for r in coverage if r["status"] == "measured"]
    broad = plan.get("broad_successor", False)
    diagnostics = pilot.target_diagnostics(targets, actor)
    collection = bool(len(targets) >= (64 if broad else 8) and
        {r["family"] for r in measured} == {r["family"] for r in plan["train"]} and
        sum(r["kind"].startswith("later") for r in measured) >= (16 if broad else 4) and
        diagnostics["frozen_actor_errors"] >= 2)
    if collection != result["collection_gate"] or len(measured) != len(targets):
        raise ValueError("collection gate or coverage differs")
    seen = set(plan["excluded_state_sha256"])
    for name, recipes in (("starts", plan["train"]), ("screen-starts", plan["screen"])):
        if name == "screen-starts" and result["screen"] is None:
            continue
        for recipe in recipes:
            folder = directory / name / recipe["id"]
            if loop.load(folder / "setup.json")["recipe"] != recipe:
                raise ValueError("materialized recipe differs from frozen plan")
            c = loop.open_battle_scenario_capture(folder / "capture.state",
                                                   folder / "capture.state.json")
            if c.manifest.state_sha256 in seen:
                raise ValueError("captured start overlaps a retired or other start")
            seen.add(c.manifest.state_sha256)
            if name == "screen-starts" and (c.manifest.capture_id in actor.train_capture_ids or
                    c.manifest.state_sha256 in {t["state_sha256"] for t in targets}):
                raise ValueError("screen capture overlaps fitting ancestry")
    pilot.verify_targets(directory / "targets", actor)
    target_audit = audit(directory / "targets", projector=project_balanced_status_moves,
                         return_value=pilot.win_conditioned_return,
                         plan_path=directory / "plan.json")
    native = audit(directory)
    choices = verify_choices(directory / "targets", actor, frozen)
    choices += verify_choices(directory / "trajectories", actor, frozen)
    fit_passed = False
    screen = None
    if result["fits"]:
        candidate = combined.model(directory / "candidate-model.json")
        verify_frozen(candidate, actor, targets)
        fit = loop.load(directory / "fit.json")
        if fit["candidate"] != bind(directory / "candidate-model.json"):
            raise ValueError("fit checkpoint binding differs")
        problem = pilot.extend_problem(problem, actor, targets)
        theta = np.append(candidate.move.weights2, candidate.move.effect_readout)
        slack = float(np.min(problem.constraints @ theta-problem.minimum))
        old_targets = [t for g in groups for t in g]
        regressions = sum(candidate.move.predict_index(old_targets[i]["vectors"]) ==
                          problem.status_indices[i] for i in problem.protected)
        old = [{"initial": group_metrics(g, initial), "candidate": group_metrics(g, candidate)}
               for g in groups]
        new = {"actor": group_metrics(targets, actor),
               "candidate": group_metrics(targets, candidate)}
        fit_passed = bool(fit["solver_success"] and slack >= -1e-8 and regressions == 0 and
                          old[0]["candidate"]["regret"] <= old[0]["initial"]["regret"] and
                          new["candidate"]["regret"] <= .75*new["actor"]["regret"])
        if (regressions != fit["retention_regressions"] or
                len(problem.protected) != fit["protected_preferences"] or
                old != fit["old_groups"] or any(not metrics_equal(new[k], fit["new_group"][k])
                                           for k in new) or
                abs(slack-fit["minimum_slack"]) > 1e-10 or fit_passed != fit["passed"]):
            raise ValueError("recomputed fit evidence differs")
        if result["screen"] is not None:
            baseline, _ = combined.verify_screen(directory / "screen-baseline", frozen, frozen)
            selected, n = combined.verify_screen(directory / "screen-candidate", candidate, frozen)
            choices += n
            screen = pilot.outcome_gate(selected, baseline)
            if screen != result["screen"] or len(selected) != len(plan["screen"]):
                raise ValueError("recomputed screen differs")
    if (native != result["native"] or native["episodes"] > plan["max_episodes"] or
            native["frames"] > plan["max_frames"] or result["fits"] > plan["max_fits"] or
            result["seconds"] > plan["max_minutes"]*60 or result["actor_promotions"] != 0):
        raise ValueError("native totals differ")
    return {"plan": bind(directory / "plan.json"), "result": bind(directory / "result.json"),
        "native": native, "targets": target_audit["new_target_contexts"],
        "recomputed_learned_attacks": choices, "fit_passed": fit_passed,
        "screen": screen, "ready": bool(collection and fit_passed and screen and screen["passed"]),
        "actor_promotions": 0}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--packet", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(inspect(args.root, args.packet), indent=2))
