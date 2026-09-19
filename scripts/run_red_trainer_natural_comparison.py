"""Compare one TRAIN-qualified challenger with frozen and fixed controls.

All three plans are frozen before the DEVELOPMENT capture is executed. This is
one descriptive natural-battle comparison, never an authority promotion.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import run_red_trainer_practice_baseline as baseline
import run_red_trainer_practice_model as challenger

from pokemon_red_completion.battle_scenario_capture import open_battle_scenario_capture
from pokemon_red_completion.red_trainer_practice_ancestry import trainer_origin_cluster
from pokemon_red_completion.red_trainer_practice_fit import TrainerPracticeThreeHeadModel
from pokemon_red_completion.scenario_lab import ScenarioPartition

ROOT = Path(__file__).resolve().parents[1]
ROM_SHA256 = "5ca7ba01642a3b27b0cc0b5349b52792795b62d3ed977e98a09390659af96b7b"


def qualified_fit_receipt(fit: Path) -> dict[str, object]:
    """Admit the retention successor without inventing a legacy fit receipt."""
    if (fit / "result.json").is_file():
        from run_red_trainer_retention import admitted_cache, gates

        result = json.loads((fit / "result.json").read_bytes())
        plan = json.loads((fit / "plan.json").read_bytes())
        if "policy_id" in plan:
            from fit_red_trainer_learner_continuation import qualified_policy_fit_receipt

            return qualified_policy_fit_receipt(fit)
        if (
            _binding(fit / "model.json") != result.get("model")
            or result.get("train_qualified") is not True
            or result.get("fits") != 1
        ):
            raise ValueError("retention challenger failed its unchanged TRAIN gates")
        broader = "before_broad" in result
        late = plan.get("profile") == "late"
        if broader:
            from run_red_trainer_broad_fit import broad_gates, prior_broad_gates

            checks = broad_gates(
                result["before"], result["after"], result["before_broad"], result["after_broad"]
            )
            if late:
                checks.update(
                    prior_broad_gates(
                        result.get("before_prior_broad"), result.get("after_prior_broad")
                    )
                )
        else:
            checks = gates(result["before"], result["after"])
        if not all(checks.values()):
            raise ValueError("retention challenger failed its unchanged TRAIN gates")
        manifest_binding = plan["audit"] if broader else plan["manifest"]
        manifest = Path(manifest_binding["path"])
        if _binding(manifest) != manifest_binding:
            raise ValueError("retention corpus manifest differs")
        ancestor, targets = admitted_cache(manifest.parent)
        model = TrainerPracticeThreeHeadModel.from_dict(
            json.loads((fit / "model.json").read_bytes())
        )
        if broader:
            from run_red_trainer_broad_fit import admitted_supply

            if late:
                prior_receipt = Path(plan["prior_supply"]["path"])
                if _binding(prior_receipt) != plan["prior_supply"]:
                    raise ValueError("prior broad supply receipt differs")
                targets += admitted_supply(
                    prior_receipt.parent,
                    set(ancestor.train_root_ids),
                    {t["capture_id"] for t in targets},
                )
            supply_receipt = Path(plan["supply"]["path"])
            if _binding(supply_receipt) != plan["supply"]:
                raise ValueError("broader supply receipt differs")
            extra = admitted_supply(
                supply_receipt.parent,
                set(ancestor.train_root_ids),
                {t["capture_id"] for t in targets},
                late=late,
            )
            if late:
                move_receipt = Path(plan["late_move_supply"]["path"])
                if _binding(move_receipt) != plan["late_move_supply"]:
                    raise ValueError("late move supply receipt differs")
                extra += admitted_supply(
                    move_receipt.parent,
                    set(ancestor.train_root_ids),
                    {t["capture_id"] for t in targets + extra},
                    late=True,
                    late_main=True,
                )
            if len(extra) != result["new_contexts"]:
                raise ValueError("broader supply count differs")
            targets = targets + extra
        if (
            set(model.train_capture_ids) != {t["capture_id"] for t in targets}
            or set(model.train_root_ids) != set(ancestor.train_root_ids)
            or len(set(model.train_root_ids)) != 4
        ):
            raise ValueError("retention challenger TRAIN ancestry differs")
        return {
            "qualification_tier": "independent_root_train",
            "independent_train_supply_gate_passed": True,
            "distinct_upstream_train_roots": 4,
            "scenario_count": len(targets),
            "model_sha256": _binding(fit / "model.json")["sha256"],
        }
    return json.loads((fit / "receipt.json").read_bytes())


def _binding(path: Path) -> dict[str, str]:
    return {"path": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def _write(path: Path, value: dict[str, object]) -> None:
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")


def _result(output: Path) -> dict[str, object]:
    outcome = json.loads((output / "outcome.json").read_bytes())
    verification = json.loads((output / "event-log-verification.json").read_bytes())
    metrics = outcome.get("metrics")
    if (
        verification.get("complete") is not True
        or verification.get("failed_runs") != 0
        or verification.get("incomplete_decisions") != 0
        or outcome.get("teacher_queries") != 0
        or not isinstance(metrics, dict)
        or metrics.get("invalid_action_failures") != 0
    ):
        raise ValueError("natural trainer comparison log or action admission failed")
    return {
        "battle_won": outcome.get("battle_won"),
        "stop_reason": outcome.get("stop_reason"),
        "decision_count": outcome.get("decision_count"),
        "action_counts": outcome.get("action_counts"),
        "opponent_faints": metrics.get("opponent_faints"),
        "party_faints": metrics.get("party_faints"),
        "party_hp_lost": metrics.get("party_hp_lost"),
        "attack_turn_utility_sum": metrics.get("attack_turn_utility_sum"),
        "policy_latency_ns_mean": metrics.get("policy_latency_ns_mean"),
        "event_count": verification.get("event_count"),
        "event_log_complete": True,
        "teacher_queries": 0,
        "invalid_actions": 0,
    }


def comparison_verdict(summary: dict[str, object]) -> dict[str, object]:
    """Persist the no-integration decision separately from merely winning."""
    results = summary["results"]
    candidate, frozen = results["challenger"], results["frozen"]
    checks = {
        "candidate_won": candidate["battle_won"] is True,
        "all_logs_complete_and_unassisted": all(
            arm["event_log_complete"] is True
            and arm["teacher_queries"] == 0
            and arm["invalid_actions"] == 0
            for arm in results.values()
        ),
        "no_more_party_faints_than_frozen": candidate["party_faints"] <= frozen["party_faints"],
        "no_more_hp_loss_than_frozen": candidate["party_hp_lost"] <= frozen["party_hp_lost"],
        "strict_efficiency_improvement": (
            candidate["decision_count"] < frozen["decision_count"]
            or candidate["party_hp_lost"] < frozen["party_hp_lost"]
        ),
    }
    return {
        "schema": "pokemon.red.trainer-natural-verdict.v1",
        "model_sha256": summary["model_sha256"],
        "capture_id": summary["capture_id"],
        "checks": checks,
        "natural_comparison_passed": all(checks.values()),
        "independent_replicated_transfer": False,
        "final_player_ready": False,
        "authority_promotions": 0,
        "reason": "Unfavorable natural comparison"
        if not all(checks.values())
        else "Single descriptive comparison; independent qualification still required",
    }


def run(args: argparse.Namespace) -> dict[str, object]:
    if args.output.exists():
        raise ValueError("natural trainer comparison output must be new")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip():
        raise ValueError("commit comparison source before DEVELOPMENT execution")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    rom = _binding(args.rom)
    if rom["sha256"] != ROM_SHA256:
        raise ValueError("natural trainer comparison Red cartridge differs")
    model_path = args.fit / "model.json"
    fit_receipt = qualified_fit_receipt(args.fit)
    if (
        fit_receipt.get("qualification_tier") != "independent_root_train"
        or fit_receipt.get("independent_train_supply_gate_passed") is not True
        or fit_receipt.get("distinct_upstream_train_roots") != 4
        or not isinstance(fit_receipt.get("scenario_count"), int)
        or fit_receipt["scenario_count"] < 16
        or fit_receipt.get("model_sha256") != _binding(model_path)["sha256"]
    ):
        raise ValueError("natural trainer challenger is not TRAIN-qualified")
    model = TrainerPracticeThreeHeadModel.from_dict(json.loads(model_path.read_bytes()))
    state = args.capture / "source.state"
    manifest = args.capture / "source.state.json"
    opened = open_battle_scenario_capture(state, manifest)
    if opened.manifest.partition is not ScenarioPartition.DEVELOPMENT or trainer_origin_cluster(
        opened.manifest.root_lineage_id
    ) in {trainer_origin_cluster(root) for root in model.train_root_ids}:
        raise ValueError("natural trainer DEVELOPMENT overlaps TRAIN ancestry")
    args.output.mkdir(parents=True, mode=0o700, exist_ok=False)
    bound_state, bound_manifest = _binding(state), _binding(manifest)
    common: dict[str, object] = {
        "source_commit": commit,
        "rom": rom,
        "capture_state": bound_state,
        "capture_manifest": bound_manifest,
        "max_decisions": 80,
        "maximum_frames": 120000,
    }
    plans = {
        "fixed": {
            **common,
            "schema": baseline.SCHEMA,
            "baseline_policy": "first-legal-attack",
            "output": str(args.output / "fixed"),
        },
        "frozen": {
            **common,
            "schema": baseline.SCHEMA,
            "baseline_policy": "frozen-attack",
            "model": _binding(args.frozen_model),
            "output": str(args.output / "frozen"),
        },
        "challenger": {
            **common,
            "schema": challenger.OUTCOME_SCHEMA,
            "outcome_model": _binding(model_path),
            "output": str(args.output / "challenger"),
        },
    }
    for name, plan in plans.items():
        _write(args.output / f"{name}-plan.json", plan)
    for name in ("fixed", "frozen"):
        baseline.run(args.output / f"{name}-plan.json", check_only=True)
    challenger.run(args.output / "challenger-plan.json", check_only=True)
    stage = "execution"
    results = {}
    try:
        for name in ("fixed", "frozen", "challenger"):
            stage = name
            if name == "challenger":
                challenger.run(args.output / f"{name}-plan.json")
            else:
                baseline.run(args.output / f"{name}-plan.json")
            results[name] = _result(args.output / name)
    except Exception as error:
        _write(
            args.output / "failure.json",
            {
                "schema": "pokemon.red.trainer-natural-comparison-failure.v1",
                "stage": stage,
                "completed_arms": list(results),
                "error_type": type(error).__name__,
            },
        )
        raise
    summary: dict[str, object] = {
        "schema": "pokemon.red.trainer-natural-comparison.v1",
        "classification": "descriptive_development_one_natural_trainer_battle",
        "capture_id": opened.manifest.capture_id,
        "capture_manifest_sha256": opened.manifest_sha256,
        "source_commit": commit,
        "model_sha256": fit_receipt["model_sha256"],
        "results": results,
        "development_scenarios": 1,
        "model_updates": 0,
        "authority_promotions": 0,
        "full_game_runs": 0,
    }
    _write(args.output / "summary.json", summary)
    _write(args.output / "candidate-verdict.json", comparison_verdict(summary))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--fit", type=Path, required=True)
    parser.add_argument("--frozen-model", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    print(json.dumps(run(parser.parse_args()), sort_keys=True))


if __name__ == "__main__":
    main()
