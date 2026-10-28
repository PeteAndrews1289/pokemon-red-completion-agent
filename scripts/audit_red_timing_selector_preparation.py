"""Read-only verification and fail-closed next-stage readiness for the combined battler."""

import argparse
from pathlib import Path

import numpy as np
import run_red_timing_selector_preparation as prep
from audit_red_closed_loop_status import verify_screen
from audit_red_status_learning import audit
from build_red_status_reward_view import validate_view

from pokemon_red_completion.red_effect_selector_learning import prepare_combination
from pokemon_red_completion.red_status_retention_fit import group_metrics

combined, lab = prep.combined, prep.combined.lab


def readiness(later, fit, screen):
    """A passing numerical error alone cannot bypass missing labels or later gates."""
    coverage = prep.require_observed_cells(later)
    later_pass = (later["observed_awake"] >= 8 and np.isfinite(later["brier"])
                  and later["brier"] <= .125 and coverage["passed"])
    fit_pass = bool(fit is not None and fit["solver_success"] and
        fit["protected_preferences"] == 182 and fit["minimum_slack"] >= -1e-8 and
        fit["retention_regressions"] == 0 and
        fit["groups"][0]["candidate"]["regret"] <= fit["groups"][0]["initial"]["regret"] and
        sum(g["candidate"]["regret"] for g in fit["groups"][1:]) <=
        .75 * sum(g["initial"]["regret"] for g in fit["groups"][1:]))
    screen_pass = bool(screen is not None and
        screen["wins"]["candidate"] >= screen["wins"]["frozen"] and
        screen["concerning_selections"] == 0 and screen["improved_won_status_cases"] > 0 and
        screen["decisions"]["candidate"] <= 1.25 * screen["decisions"]["frozen"])
    gates = {"later_effect_qualification": later_pass, "retained_selector_fit": fit_pass,
             "native_train_screen": screen_pass}
    if (fit is not None and not later_pass) or (screen is not None and not fit_pass):
        raise ValueError("a downstream stage ran through a failed prerequisite")
    return {"schema": "pokemon.red.battler-finish-readiness.v1", "gates": gates,
            "first_unpassed_gate": next((k for k, passed in gates.items() if not passed), None),
            "ready_to_prepare_reserved_comparison": all(gates.values()),
            "natural_party_qualified": False, "live_story_ready": False,
            "full_battler_complete": False}


def inspect(root, packet):
    loop, bind = combined.loop, lab.common._binding
    outer = loop.load(packet / "preparation-plan.json")
    directory = packet / "combination"
    plan, result = (loop.load(directory / name) for name in ("plan.json", "result.json"))
    if type(result["fits"]) is not int or result["fits"] not in (0, 1):
        raise ValueError("one-fit cap differs")
    for key, expected in (("frozen", lab.K_SHA), ("prior", combined.PRIOR_SHA),
                          ("effect", prep.EFFECT_SHA)):
        binding = plan[key]
        if binding["sha256"] != expected or bind(Path(binding["path"])) != binding:
            raise ValueError("frozen source binding differs")
    if plan["protocol"]["preparation"] != bind(packet / "preparation-plan.json"):
        raise ValueError("native preparation binding differs")
    if plan["protocol"]["derived"] != bind(packet / "derived-later.json"):
        raise ValueError("derived snapshot binding differs")
    fresh = outer.get("fresh_native", False)
    consumed = prep.all_consumed_bindings(root) if fresh else prep.consumed_bindings(root)
    if plan["protocol"]["consumed"] != consumed or outer["consumed"] != consumed:
        raise ValueError("consumed exclusions differ")
    effect_path = root / "red-timing-effect-learning-20260922-v1/fit.json"
    if bind(effect_path)["sha256"] != prep.EFFECT_SHA or plan["effect"] != bind(effect_path):
        raise ValueError("effect predictor differs")
    effect = loop.load(effect_path)
    native = audit(packet, plan_path=packet / "preparation-plan.json")
    episode_cap, frame_cap = (150, 15470000) if fresh else (142, 15430000)
    if native["episodes"] > episode_cap or native["frames"] > frame_cap:
        raise ValueError("preparation execution cap exceeded")
    for recipe, row in zip(outer["recipes"], loop.load(packet / "derived-later.json"), strict=True):
        run = packet / "primers" / recipe["id"] / "primer"
        folder = Path(row["capture"])
        c = loop.open_battle_scenario_capture(folder / "intermediate.state",
                                              folder / "intermediate.state.json")
        target_ref = lab.pokemon_red_move_ref(lab.FAMILIES[recipe["family"]])
        slot = next(i+1 for i, m in enumerate(recipe["practice"]["actor_moves"])
                    if m["move_ref"] == target_ref)
        if (c.manifest.partition is not loop.ScenarioPartition.TRAIN or
                c.manifest.state_sha256 != bind(run / "final.state")["sha256"] or
                c.manifest.root_lineage_id != recipe["root"] or
                prep.derive_later_row(c, folder, recipe, loop.load(run / "episode.json"),
                                     bind(run / "episode.json"), target_slot=slot) != row):
            raise ValueError("native primer-to-later-state chain differs")
    identities = ("capture_id", "manifest_sha256", "state_sha256")
    for key in identities:
        selected = [r[key] for r in plan["later_cases"]]
        if len(set(selected)) != len(selected) or set(selected) & {r[key] for r in consumed}:
            raise ValueError("qualification reused an excluded or duplicate state")
    saved_later = loop.load(directory / "later-qualification.json")
    rederived, suppressions = [], []
    for recipe, saved in zip(plan["later_cases"], saved_later["rows"], strict=True):
        folder, name = Path(recipe["capture"]), recipe.get("state_name", "capture.state")
        c = loop.open_battle_scenario_capture(folder / name, folder / (name + ".json"))
        if (c.manifest_sha256 != recipe["manifest_sha256"] or
                c.manifest.state_sha256 != recipe["state_sha256"]):
            raise ValueError("qualification source changed")
        run = directory / recipe["id"]
        row = combined.authenticate_row(run, c, {**recipe, "role": "train"}, allow_terminal=True)
        row["asleep_before_choice"] = recipe["asleep"]
        row["probability_conditional_on_execution"] = float(combined.effect_values(
            [recipe["vector"]], effect["weights"])[0, 1])
        if (row != saved or row != loop.load(run / "measured.json") or
                row["features"] != recipe["vector"][-len(combined.COMPACT_STATUS_NAMES):]):
            raise ValueError("measured later-effect evidence differs")
        rederived.append(row)
        if row["evidence"]["kind"] == "suppressed":
            ep = loop.load(run / "episode.json")
            step = ep["decisions"][0]
            suppressions.append({"case": recipe["id"], "asleep_before": recipe["asleep"],
                "player_fainted": step["outcome"]["player_fainted"],
                "hp_before": step["state_before"]["active_hp"],
                "hp_after": step["state_after"]["active_hp"], "stop": ep["stop_reason"]})
    observed = [r for r in rederived if not r["asleep_before_choice"] and
                r["evidence"]["kind"] == "observed"]
    brier = float(np.mean([(r["probability_conditional_on_execution"] -
                          r["evidence"]["application_success"])**2 for r in observed]))
    if (saved_later["observed_awake"] != len(observed) or saved_later["brier"] != brier or
            saved_later["additional_coverage"] != prep.require_observed_cells(saved_later)):
        raise ValueError("qualification aggregate differs")
    fit, screen = None, None
    if result["fits"]:
        fit = loop.load(directory / "fit.json")
        if fit["candidate"] != bind(directory / "candidate-model.json"):
            raise ValueError("selector checkpoint differs")
        candidate = combined.model(directory / "candidate-model.json")
        _, inputs, originals, initial, frozen = combined.previous.load_inputs(root)
        if loop.canonical_sha256(inputs) != plan["inputs_sha256"]:
            raise ValueError("fitting inputs differ")
        groups = validate_view(Path(plan["reward"]["path"]), root)["groups"]
        prior = combined.model(Path(plan["prior"]["path"]))
        problem = prepare_combination(groups, initial, frozen, prior, originals, effect)
        weights = np.append(candidate.move.weights2, candidate.move.effect_readout)
        if (len(problem.protected) != 182 or not np.isfinite(weights).all() or
                np.min(problem.constraints @ weights - problem.minimum) < -1e-8 or
                not np.array_equal(prior.move.weights1, candidate.move.weights1) or
                candidate.control.to_dict() != frozen.control.to_dict() or
                candidate.switch.to_dict() != frozen.switch.to_dict() or
                candidate.damage_reference.to_dict() != frozen.move.to_dict() or
                list(candidate.move.effect_weights) != effect["weights"]):
            raise ValueError("frozen components or retention constraints differ")
        for group, reported in zip(groups, fit["groups"], strict=True):
            if group_metrics(group, candidate) != reported["candidate"]:
                raise ValueError("selector fit metrics differ")
        if result["screen"] is not None:
            base, _ = verify_screen(directory / "train-baseline", frozen, frozen)
            chosen, _ = verify_screen(directory / "train-screen", candidate, frozen)
            if len(base) != 64 or len(chosen) != 64:
                raise ValueError("screen size differs")
            screen = loop.gate(chosen, base)
            if screen != result["screen"]:
                raise ValueError("native screen gate differs")
    elif any((directory / name).exists() for name in
             ("fit.json", "candidate-model.json", "train-screen", "train-baseline")):
        raise ValueError("unreported fitting or screening artifacts")
    ready = readiness(saved_later, fit, screen)
    if ready["gates"]["later_effect_qualification"] != result["later_gate"]:
        raise ValueError("claimed later gate differs")
    if ready["gates"]["retained_selector_fit"] != result["fit_gate"]:
        raise ValueError("claimed fit gate differs")
    if result["withheld"] is not None or any((directory / n).exists() for n in
                                           ("held-candidate", "held-baseline")):
        raise ValueError("reserved comparisons accessed prematurely")
    return {**ready, "source_commit": outer["source_commit"], "native": native,
            "observed_awake": len(observed), "brier": brier,
            "correct_at_half": sum((r["probability_conditional_on_execution"] >= .5) ==
                                   bool(r["evidence"]["application_success"]) for r in observed),
            "positive_effects": sum(r["evidence"]["application_success"] for r in observed),
            "suppressions": suppressions, "fits": result["fits"],
            "bindings": {"preparation": bind(packet / "preparation-plan.json")["sha256"],
                         "plan": bind(directory / "plan.json")["sha256"],
                         "qualification": bind(directory / "later-qualification.json")["sha256"],
                         "result": bind(directory / "result.json")["sha256"]}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "packet", "output"):
        parser.add_argument("--"+name, type=Path, required=True)
    args = parser.parse_args()
    report = inspect(args.root, args.packet)
    lab.write(args.output, report)
    print(combined.json.dumps(report), flush=True)
