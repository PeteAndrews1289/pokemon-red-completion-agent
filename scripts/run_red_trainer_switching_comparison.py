"""One bounded larger-party TRAIN measurement under frozen J; at most one fit.

Reuses retained TRAIN captures, never the consumed assisted DEVELOPMENT pilot.
Selection is return-blind. All branches, limits and retention gates are declared
before execution; terminal failures stop the batch without replacement cases.
"""
from __future__ import annotations

import argparse
import json
import time
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

import run_red_trainer_practice_model as player
from run_red_six_party_assisted_pilot import MODEL_SHA256, binding, revision, write_new
from run_red_trainer_budgeted_fit import composed_offset
from run_red_trainer_learner_continuation import first_choice
from run_red_trainer_retention import examples
from run_red_trainer_terminal_curriculum import terminal_anchor_targets

from pokemon_red_completion.battle_scenario_capture import open_battle_scenario_capture
from pokemon_red_completion.red_battle_catalog import PokemonRedBattleCatalog
from pokemon_red_completion.red_trainer_budgeted_fit import RegretBudget, fit_budgeted_head
from pokemon_red_completion.red_trainer_practice_admission import inspect_trainer_practice_choices
from pokemon_red_completion.red_trainer_practice_counterfactual import (
    collect_trainer_practice_counterfactuals,
)
from pokemon_red_completion.red_trainer_practice_fit import (
    TrainerPracticeThreeHeadModel,
    summarize_trainer_practice_training,
)
from pokemon_red_completion.red_trainer_practice_targets import (
    aggregate_trainer_timing_targets,
    extract_trainer_practice_targets,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition

POLICY = "train-frozen-J-large-party-continuation-v1"
OFFSETS = (0, 2, 4, 6, 8)
TURNS, DECISIONS, FRAMES, ACTIONS, SECONDS = 80, 160, 240000, 5000, 45
SCHEMA = "pokemon.red.large-party-J-comparison.v1"


def bound(pin):
    path = Path(pin["path"])
    if binding(path) != pin:
        raise ValueError("comparison input binding differs")
    return path


def read(pin):
    return json.loads(bound(pin).read_bytes())


def select_cases(rows):
    """Two openings and two later decisions per root, no reward-based selection."""
    if any(r["partition"] != "train" for r in rows):
        raise ValueError("TRAIN only")
    roots = sorted({r["root_lineage_id"] for r in rows})
    if len(roots) != 4 or len({r["capture_id"] for r in rows}) != len(rows):
        raise ValueError("four unique TRAIN origins and distinct captures required")
    groups = []
    for root in roots:
        group = sorted((r for r in rows if r["root_lineage_id"] == root
                        and r["observation"]["features"]["party"]["count"] == 5),
                       key=lambda r: r["capture_id"])
        openings = [r for r in group if r["capture_id"].startswith("assisted-train-")]
        later = [r for r in group if r["capture_id"].startswith("terminal-intermediate-")]
        main = [r for r in later if r["decision_context"] == "main"]
        replacement = [r for r in later if r["decision_context"] in {"forced", "prompt"}]
        if len(openings) < 2 or len(main) < 2:
            raise ValueError("insufficient declared larger-party TRAIN contexts")
        groups.append(openings[:2] + main[:1] + (replacement[:1] or main[1:2]))
    return [group[index] for index in range(4) for group in groups]


def load_training(model_path):
    if binding(model_path)["sha256"] != MODEL_SHA256:
        raise ValueError("frozen J differs")
    initial = TrainerPracticeThreeHeadModel.from_dict(json.loads(model_path.read_bytes()))
    fit_plan = json.loads((model_path.parent / "plan.json").read_bytes())
    containers = [read(pin) for pin in fit_plan["retention_sources"]]
    pools = [read(c["targets"]) for c in containers]
    retained, prior, late, late_main = pools
    policy = [w["target"] for w in read(read(fit_plan["policy_supply"])["targets"])]
    all_rows = sum(pools, [])
    if (len(all_rows) != 318 or len({t["capture_id"] for t in all_rows}) != 318
            or {t["capture_id"] for t in all_rows} != set(initial.train_capture_ids)
            or {t["root_lineage_id"] for t in all_rows} != set(initial.train_root_ids)
            or any(t["partition"] != "train" for t in all_rows + policy)):
        raise ValueError("retained TRAIN membership differs")
    return initial, all_rows, policy, {
        "original44": retained[:44], "retained52": retained[:52],
        "terminal128": retained[52:], "new80": retained[100:],
        "prior48": prior, "late90": late + late_main, "policy16": policy,
    }, fit_plan


def prepare(args):
    commit = revision()
    if args.output.exists() or binding(args.rom)["sha256"] != player.ROM_SHA256:
        raise ValueError("new comparison output and correct ROM required")
    initial, retained, _policy, groups, fit_plan = load_training(args.model)
    cached = {r["capture_id"]: r for r in retained}
    paths, rows = {}, []
    for path in sorted(args.source.glob("train/*/target-*.json")):
        row = json.loads(path.read_bytes())
        if cached.get(row["capture_id"]) != row:
            raise ValueError("source target differs from J's authenticated retention pool")
        paths[row["capture_id"]] = path
        rows.append(row)
    selected = select_cases(rows)
    ids = {r["capture_id"] for r in selected}
    # Read-only reconstruction against original state/manifest/branch event proofs.
    terminal_anchor_targets(args.source / "model.json", ids)
    cases = []
    for row in selected:
        path = paths[row["capture_id"]]
        index = int(path.stem.rsplit("-", 1)[1])
        state = path.parent / ("materialized/assisted.state" if index == 0
                               else f"intermediate-{index:02d}.state")
        manifest = state.with_suffix(".state.json")
        capture = open_battle_scenario_capture(state, manifest)
        if (capture.manifest.partition is not ScenarioPartition.TRAIN
                or capture.manifest.root_lineage_id not in initial.train_root_ids
                or capture.manifest.capture_id != row["capture_id"]):
            raise ValueError("TRAIN source identity differs")
        heads = row["heads"]
        refs = (heads.get("control") or heads.get("move") or heads["switch"])["choice_refs"]
        if not 2 <= len(refs) <= 8:
            raise ValueError("branch count differs")
        cases.append({"capture_id": row["capture_id"], "root": row["root_lineage_id"],
                      "context": row["decision_context"], "refs": refs,
                      "state": binding(state), "manifest": binding(manifest)})
    catalog = PokemonRedBattleCatalog()
    before = {name: report(rows, initial, catalog) for name, rows in groups.items()}
    limits = {f"{group}:{head}": values[head]["model_mean_train_regret"] + 1e-9
              for group, values in before.items() for head in ("switch", "composed_action")
              if values.get(head, {}).get("examples", 0)}
    plan = {
        "schema": SCHEMA, "source_commit": commit, "model": binding(args.model),
        "rom": binding(args.rom), "source": str(args.source.resolve()), "cases": cases,
        "initial_fit_plan": binding(args.model.parent / "plan.json"),
        "retention_sources": fit_plan["retention_sources"],
        "prior_policy_supply": fit_plan["policy_supply"], "before_retention": before,
        "limits": limits, "continuation_policy_id": POLICY,
        "history_initialization": "fresh actor at capture; forced first action observed",
        "timing_offsets": list(OFFSETS), "player_turn_horizon": TURNS,
        "max_decisions": DECISIONS, "maximum_frames": FRAMES,
        "maximum_controller_actions": ACTIONS, "maximum_wall_seconds": SECONDS,
        "maximum_collection_wall_seconds": 2700, "output": str(args.output.resolve()),
        "maximum_branches": sum(len(c["refs"]) for c in cases) * len(OFFSETS),
        "fit": {"maximum_fits": 1, "head_order": ["switch", "control"],
                "move_frozen": True, "epochs_per_head": 2400, "learning_rate": 0.005,
                "objective": "pairwise_regret", "minimum_composed_improvement_fraction": 0.1,
                "require_new_switch_regret_nonincrease": True},
        "new_origins": 0, "development_used": False, "production_promotion": False,
        "reset_authority": (
            "User-authorized new bounded current-J TRAIN measurement; old schedules untouched"
        ),
    }
    write_new(args.source / "current-J-switching-comparison-20260920-claim.json", plan)
    args.output.mkdir(mode=0o700)
    write_new(args.output / "plan.json", plan)
    return {"prepared_contexts": len(cases), "maximum_branches": plan["maximum_branches"]}


def report(rows, model, catalog):
    return summarize_trainer_practice_training(rows, model, catalog=catalog,
                                               initial_move_model=model.move)


def require_terminal(episode):
    if (episode["stop_reason"] not in {"battle_won", "party_defeated"}
            or episode["metrics"]["invalid_action_failures"]):
        raise ValueError("nonterminal or invalid branch; comparison stops")


def plan_path(output):
    amended = output / "amended-plan.json"
    return amended if amended.exists() else output / "plan.json"


def authenticated_plan(output):
    plan = json.loads(plan_path(output).read_bytes())
    original = read(plan["timing_amendment"]["original"]) if "timing_amendment" in plan else plan
    if "timing_amendment" in plan:
        validate_timing_amendment(plan, original)
    if (plan["schema"] != SCHEMA or plan["source_commit"] != revision()
            or plan["output"] != str(output.resolve())
            or read(binding(Path(plan["source"]) /
                            "current-J-switching-comparison-20260920-claim.json")) != original
            or plan["model"]["sha256"] != MODEL_SHA256):
        raise ValueError("comparison protocol differs")
    bound(plan["model"])
    bound(plan["rom"])
    bound(plan["initial_fit_plan"])
    return plan


def validate_timing_amendment(plan, original):
    amendment = plan["timing_amendment"]
    expected = {**original, "source_commit": plan["source_commit"],
                "timing_offsets": list(OFFSETS),
                "maximum_branches": sum(len(c["refs"]) for c in original["cases"]) * len(OFFSETS),
                "timing_amendment": amendment}
    if (plan != expected or amendment["replayed_branches"] != 0
            or [r["offset"] for r in amendment["retained_timings"]] != [0, 4, 8]
            or original["timing_offsets"] != [0, 4, 8]):
        raise ValueError("timing amendment may not alter cases, budgets, model or fit")
    bound(amendment["original_failure"])


def timing_target(capture, branch, case, offset):
    identity = json.loads((branch / "plan.json").read_bytes())
    choices = json.loads((branch / "choices.json").read_bytes())
    if (identity["continuation_policy_id"] != POLICY
            or identity["model_sha256"] != MODEL_SHA256
            or identity["first_choice_refs"] != case["refs"]
            or choices["player_turn_horizon"] != TURNS):
        raise ValueError("changed comparison measurement")
    for row in choices["branches"]:
        require_terminal(row["episode"])
    admitted = inspect_trainer_practice_choices(
        capture, choices, expected_choice_refs=tuple(case["refs"]),
        continuation_policy_id=POLICY,
        branch_event_logs={ref: branch / f"branch-{i:02d}-events"
                           for i, ref in enumerate(case["refs"])},
        plan_sha256=binding(branch / "plan.json")["sha256"],
        model_sha256=MODEL_SHA256, max_decisions=DECISIONS,
        expected_opening_idle_frames=offset,
    )
    for i in range(len(case["refs"])):
        endpoint = branch / f"branch-{i:02d}-endpoint"
        saved = json.loads((endpoint / "final-state.json").read_bytes())
        if binding(endpoint / "final.state")["sha256"] != saved["state_sha256"]:
            raise ValueError("comparison endpoint changed")
    return extract_trainer_practice_targets(admitted, choices)


def amend_timing_schedule(output):
    original = output / "plan.json"
    if binding(original)["sha256"] != (
        "7430e46c4e6e8ddde088533a6c0cbddbe086c219146efc42956dddb1ac3bfde6"
    ):
        raise ValueError("amendment is limited to the retained three-timing integration failure")
    plan = json.loads(original.read_bytes())
    failure = output / "failure.json"
    if json.loads(failure.read_bytes()) != {
        "branches_started": 24, "contexts_completed": 0,
        "error": "timing schedule differs from prospective offsets",
        "error_type": "TrainerPracticeTargetError", "fits": 0, "global_stop": True,
        "stage": "case-00-timing-08",
    }:
        raise ValueError("only aggregation failure may resume")
    if {p.name for p in output.iterdir()} != {
        "plan.json", "measurement-claim.json", "case-00", "failure.json"
    }:
        raise ValueError("comparison has other started or consumed work")
    if {p.name for p in (output / "case-00").iterdir()} != {
        "timing-00", "timing-04", "timing-08"
    }:
        raise ValueError("retained timing inventory differs")
    case = plan["cases"][0]
    capture = open_battle_scenario_capture(bound(case["state"]), bound(case["manifest"]))
    retained = []
    for offset in (0, 4, 8):
        branch = output / f"case-00/timing-{offset:02d}"
        timing_target(capture, branch, case, offset)
        retained.append({"offset": offset, "choices": binding(branch / "choices.json"),
                         "plan": binding(branch / "plan.json")})
    amendment = {
        "original": binding(original), "original_failure": binding(failure),
        "retained_timings": retained, "replayed_branches": 0,
        "reason": "Existing TRAIN aggregate requires five offsets; keep guard and all24 results",
        "old_maximum_branches": plan["maximum_branches"],
        "original_execution_source_commit": plan["source_commit"],
    }
    amended = {**plan, "source_commit": revision(), "timing_offsets": list(OFFSETS),
               "maximum_branches": sum(len(c["refs"]) for c in plan["cases"]) * len(OFFSETS),
               "timing_amendment": amendment}
    write_new(output / "amended-plan.json", amended)
    return {"retained_branches": 24, "amended_maximum_branches": amended["maximum_branches"]}


def measure(output, *, resume=False):
    plan = authenticated_plan(output)
    if list(OFFSETS) != plan["timing_offsets"]:
        raise ValueError("plan timing count differs before execution")
    if resume != ("timing_amendment" in plan):
        raise ValueError("explicit timing-amendment continuation required")
    if resume:
        for retained in plan["timing_amendment"]["retained_timings"]:
            bound(retained["choices"])
            bound(retained["plan"])
    claim = "continuation-claim.json" if resume else "measurement-claim.json"
    write_new(output / claim, {"plan": binding(plan_path(output))})
    model = TrainerPracticeThreeHeadModel.from_dict(read(plan["model"]))
    stats = player.RedPracticeCartridge(bound(plan["rom"]).read_bytes()).public_base_stats
    started, targets, stage = time.monotonic(), [], "setup"
    branch_count = 24 if resume else 0
    try:
        for ci, case in enumerate(plan["cases"]):
            capture = open_battle_scenario_capture(bound(case["state"]), bound(case["manifest"]))
            directory = output / f"case-{ci:02d}"
            directory.mkdir(mode=0o700, exist_ok=resume and ci == 0)
            timed = []
            for offset in OFFSETS:
                stage = f"case-{ci:02d}-timing-{offset:02d}"
                branch = directory / f"timing-{offset:02d}"
                if resume and ci == 0 and offset in (0, 4, 8):
                    timed.append(timing_target(capture, branch, case, offset))
                    continue
                branch.mkdir(mode=0o700)
                identity = {
                    "source_commit": capture.manifest.source_commit,
                    "execution_source_commit": plan["source_commit"],
                    "capture_id": capture.manifest.capture_id,
                    "capture_manifest_sha256": capture.manifest_sha256,
                    "root_lineage_id": capture.manifest.root_lineage_id, "partition": "train",
                    "model_sha256": MODEL_SHA256, "continuation_policy_id": POLICY,
                    "policy_id": POLICY, "max_decisions": DECISIONS,
                    "player_turn_horizon": TURNS, "opening_idle_frames": offset,
                    "first_choice_refs": case["refs"],
                }
                write_new(branch / "plan.json", identity)
                plan_sha = binding(branch / "plan.json")["sha256"]
                active = {}

                def event_log(index, choice, branch=branch, active=active,
                              identity=identity, plan_sha=plan_sha):
                    nonlocal branch_count
                    if time.monotonic() - started >= plan["maximum_collection_wall_seconds"]:
                        raise TimeoutError("comparison collection wall budget")
                    branch_count += 1
                    endpoint = branch / f"branch-{index:02d}-endpoint"
                    endpoint.mkdir(mode=0o700)
                    active["endpoint"] = endpoint
                    return player.TrainerPracticeEventLog(
                        branch / f"branch-{index:02d}-events",
                        run_identity={**identity, "plan_sha256": plan_sha,
                                      "first_choice_ref": choice.semantic_ref},
                    )

                @contextmanager
                def session_factory(active=active):
                    with (
                        player.PyBoyAdapter(
                            bound(plan["rom"]), watch=False, speed=None,
                        ) as emulator,
                        player.retained_session(
                            emulator, maximum_frames=FRAMES, output=active["endpoint"],
                            maximum_controller_actions=ACTIONS, maximum_wall_seconds=SECONDS,
                            action_metadata=lambda: {
                                "controller_actions_attempted": active["limiter"].attempted_actions,
                                "controller_actions_completed": active["limiter"].completed_actions,
                            },
                        ) as session,
                    ):
                        active["session"] = session
                        active["limiter"] = player.ControllerActionLimiter(
                            player.FrameSafeExecutor(session), maximum_actions=ACTIONS,
                            admit_action=session.check_wall_time_budget,
                        )
                        yield session
                        session.check_wall_time_budget()

                class Executor:
                    def __init__(self, active):
                        self.active = active

                    def execute(self, action):
                        return self.active["limiter"].execute(action)

                def retain(index, choice, episode, branch=branch):
                    write_new(branch / f"branch-{index:02d}.json", episode.public_dict())
                    require_terminal(episode.public_dict())

                result = collect_trainer_practice_counterfactuals(
                    capture, session_factory=session_factory,
                    continuation_policy_factory=lambda capture=capture: (
                        player.RedTrainerPracticeOutcomePolicy(
                            policy_id=POLICY, battle_plan_id=capture.manifest.capture_id,
                            model=model,
                        )
                    ),
                    first_choices=tuple(first_choice(ref) for ref in case["refs"]),
                    max_decisions=DECISIONS, player_turn_horizon=TURNS,
                    public_species_base_stats=stats, opening_idle_frames=offset,
                    branch_event_log_factory=event_log, branch_sink=retain,
                    action_executor=Executor(active),
                    decision_guard=lambda _raw, active=active: (
                        active["session"].check_wall_time_budget()
                    ),
                ).public_dict()
                write_new(branch / "choices.json", result)
                admitted = inspect_trainer_practice_choices(
                    capture, result, expected_choice_refs=tuple(case["refs"]),
                    continuation_policy_id=POLICY,
                    branch_event_logs={ref: branch / f"branch-{i:02d}-events"
                                       for i, ref in enumerate(case["refs"])},
                    plan_sha256=plan_sha, model_sha256=MODEL_SHA256,
                    max_decisions=DECISIONS, expected_opening_idle_frames=offset,
                )
                timed.append(extract_trainer_practice_targets(admitted, result))
            target = aggregate_trainer_timing_targets(tuple(timed), expected_offsets=OFFSETS)
            wrapper = {"schema": SCHEMA, "continuation_model_sha256": MODEL_SHA256,
                       "protocol": binding(plan_path(output)), "target": target}
            write_new(directory / "policy-target.json", wrapper)
            targets.append(wrapper)
            print(json.dumps({"contexts_completed": len(targets), "branches": branch_count}),
                  flush=True)
    except Exception as error:
        failure_name = "continuation-failure.json" if resume else "failure.json"
        write_new(output / failure_name, {"stage": stage, "error_type": type(error).__name__,
                  "error": str(error), "contexts_completed": len(targets),
                  "branches_started": branch_count, "global_stop": True, "fits": 0})
        raise
    write_new(output / "policy-targets.json", targets)
    write_new(output / "collection.json", {"plan": binding(plan_path(output)),
              "targets": binding(output / "policy-targets.json"), "contexts": len(targets),
              "branches": branch_count, "elapsed_seconds": time.monotonic() - started,
              "new_physical_contexts": 0, "fits": 0, "authority_promotions": 0})
    return {"measured_contexts": len(targets), "branches": branch_count}


def admitted_measurements(output, plan):
    receipt = json.loads((output / "collection.json").read_bytes())
    if receipt["plan"] != binding(plan_path(output)) or receipt["contexts"] != 16:
        raise ValueError("comparison measurement receipt differs")
    wrappers = read(receipt["targets"])
    if len(wrappers) != len(plan["cases"]):
        raise ValueError("comparison target inventory differs")
    targets = []
    for ci, (case, wrapper) in enumerate(zip(plan["cases"], wrappers, strict=True)):
        capture = open_battle_scenario_capture(bound(case["state"]), bound(case["manifest"]))
        timed = []
        for offset in OFFSETS:
            branch = output / f"case-{ci:02d}/timing-{offset:02d}"
            identity = json.loads((branch / "plan.json").read_bytes())
            choices = json.loads((branch / "choices.json").read_bytes())
            if (identity["continuation_policy_id"] != POLICY
                    or identity["model_sha256"] != MODEL_SHA256
                    or identity["first_choice_refs"] != case["refs"]
                    or choices["player_turn_horizon"] != TURNS
                    or any(row["episode"]["stop_reason"] not in {"battle_won", "party_defeated"}
                           for row in choices["branches"])):
                raise ValueError("incomplete or changed comparison measurement")
            admitted = inspect_trainer_practice_choices(
                capture, choices, expected_choice_refs=tuple(case["refs"]),
                continuation_policy_id=POLICY,
                branch_event_logs={ref: branch / f"branch-{i:02d}-events"
                                   for i, ref in enumerate(case["refs"])},
                plan_sha256=binding(branch / "plan.json")["sha256"],
                model_sha256=MODEL_SHA256, max_decisions=DECISIONS,
                expected_opening_idle_frames=offset,
            )
            for i in range(len(case["refs"])):
                endpoint = branch / f"branch-{i:02d}-endpoint"
                saved = json.loads((endpoint / "final-state.json").read_bytes())
                if binding(endpoint / "final.state")["sha256"] != saved["state_sha256"]:
                    raise ValueError("comparison endpoint changed")
            timed.append(extract_trainer_practice_targets(admitted, choices))
        target = aggregate_trainer_timing_targets(tuple(timed), expected_offsets=OFFSETS)
        expected = {"schema": SCHEMA, "continuation_model_sha256": MODEL_SHA256,
                    "protocol": binding(plan_path(output)), "target": target}
        if json.loads(json.dumps(expected)) != wrapper:
            raise ValueError("comparison target differs from authenticated branch returns")
        targets.append(target)
    return targets


def learning_checks(before, after, retention, limits):
    checks = {key: retention[group][head]["model_mean_train_regret"] <= maximum
              for key, maximum in limits.items() for group, head in [key.split(":")]}
    checks["new_composed_improves_ten_percent"] = (
        after["composed_action"]["model_mean_train_regret"]
        < 0.9 * before["composed_action"]["model_mean_train_regret"]
    )
    checks["new_switch_no_regression"] = (
        after["switch"]["model_mean_train_regret"]
        <= before["switch"]["model_mean_train_regret"] + 1e-9
    )
    return checks


def fit(output):
    plan = authenticated_plan(output)
    added = admitted_measurements(output, plan)
    initial, retained, prior_policy, groups, _ = load_training(bound(plan["model"]))
    catalog = PokemonRedBattleCatalog()
    before = report(added, initial, catalog)
    if before["composed_action"]["model_mean_train_regret"] <= 1e-9:
        write_new(output / "fit-result.json", {"fits": 0, "reason": "no_measured_regret",
                  "before": before, "authority_promotions": 0})
        return {"fits": 0, "reason": "no_measured_regret"}
    write_new(output / "fit-claim.json", {"protocol": binding(plan_path(output)),
              "collection": binding(output / "collection.json"), "maximum_fits": 1})
    added_ids = {r["capture_id"] for r in added}
    policy_ids = {r["capture_id"] for r in prior_policy}
    anchors = [r for r in retained if r["capture_id"] not in added_ids | policy_ids]
    anchors += [r for r in prior_policy if r["capture_id"] not in added_ids]
    started, model = time.monotonic(), initial
    for name in plan["fit"]["head_order"]:
        metric = "composed_action" if name == "control" else name
        budgets = []
        for key, maximum in plan["limits"].items():
            group, head = key.split(":")
            if head == metric:
                rows = tuple(examples(groups[group], model, catalog)[name])
                budgets.append(RegretBudget(key, rows, maximum,
                    composed_offset(groups[group], rows) if name == "control" else 0.0))
        fitted, receipt = fit_budgeted_head(
            getattr(model, name), tuple(examples(added, model, catalog)[name]),
            tuple(examples(anchors, model, catalog)[name]), tuple(budgets),
            epochs=plan["fit"]["epochs_per_head"], learning_rate=plan["fit"]["learning_rate"],
            objective=plan["fit"]["objective"],
        )
        write_new(output / f"{name}-optimizer.json", receipt)
        if fitted is None:
            result = {"fits": 1, "train_qualified": False, "reason": "no_feasible_checkpoint",
                      "head": name, "before": before, "authority_promotions": 0}
            write_new(output / "fit-result.json", result)
            return result
        model = replace(model, **{name: fitted})
        write_new(output / f"after-{name}-model.json", model.to_dict())
        print(json.dumps({"head_completed": name}), flush=True)
    after = report(added, model, catalog)
    after_old = {name: report(rows, model, catalog) for name, rows in groups.items()}
    gates = learning_checks(before, after, after_old, plan["limits"])
    if model.move.to_dict() != initial.move.to_dict():
        raise ValueError("frozen move head changed")
    write_new(output / "candidate-model.json", model.to_dict())
    result = {"fits": 1, "before": before, "after": after, "retention": after_old,
              "gates": gates, "train_qualified": all(gates.values()), "move_head_unchanged": True,
              "model": binding(output / "candidate-model.json"), "new_physical_contexts": 0,
              "new_policy_conditioned_measurements": len(added),
              "elapsed_seconds": time.monotonic() - started,
              "natural_qualified": False, "authority_promotions": 0}
    write_new(output / "fit-result.json", result)
    return {"train_qualified": result["train_qualified"], "gates": gates, "fits": 1}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("prepare", "measure", "amend", "resume", "fit"))
    parser.add_argument("--output", type=Path, required=True)
    for name in ("rom", "model", "source"):
        parser.add_argument("--" + name, type=Path)
    args = parser.parse_args()
    if args.stage == "prepare":
        result = prepare(args)
    elif args.stage == "amend":
        result = amend_timing_schedule(args.output)
    elif args.stage in {"measure", "resume"}:
        result = measure(args.output, resume=args.stage == "resume")
    else:
        result = fit(args.output)
    print(json.dumps(result), flush=True)
