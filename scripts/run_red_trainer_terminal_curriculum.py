"""Collect terminal TRAIN branches, including actual intermediate boundaries.

The disclosed stat-damage continuation is a training teacher. The fitted actor
receives only semantic observations and learned heads. Existing source lineages
are preserved; reserved variations are TRAIN diagnostics, not natural transfer.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path

import materialize_red_teacher_battle_practice as materializer
import run_fresh_red_trainer_curriculum as original
import run_red_trainer_practice_baseline as baseline
import run_red_trainer_practice_model as model_runner
from fit_red_trainer_practice_outcomes import _bound_path

from pokemon_red_completion.battle_actions import BattleAction
from pokemon_red_completion.battle_scenario_capture import (
    OBSERVATION_SCHEMA_V2,
    build_battle_scenario_capture_payload,
    open_battle_scenario_capture,
)
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.executor import FrameBudgetController
from pokemon_red_completion.observation import PokemonRedStateReader
from pokemon_red_completion.red_battle_practice_cartridge import RedPracticeCartridge
from pokemon_red_completion.red_battle_scenario import prepare_red_battle_scenario
from pokemon_red_completion.red_trainer_practice_admission import inspect_trainer_practice_choices
from pokemon_red_completion.red_trainer_practice_counterfactual import (
    TrainerPracticeFirstChoice,
    collect_trainer_practice_counterfactuals,
)
from pokemon_red_completion.red_trainer_practice_episode import run_red_trainer_practice_episode
from pokemon_red_completion.red_trainer_practice_features import (
    project_trainer_move_features,
    project_trainer_switch_features,
)
from pokemon_red_completion.red_trainer_practice_fit import (
    TrainerPracticeThreeHeadModel,
    fit_trainer_practice_three_heads,
    summarize_trainer_practice_training,
)
from pokemon_red_completion.red_trainer_practice_log import (
    TrainerPracticeEventLog,
    verify_trainer_practice_event_log,
)
from pokemon_red_completion.red_trainer_practice_outcome_policy import (
    RedTrainerPracticeOutcomePolicy,
)
from pokemon_red_completion.red_trainer_practice_targets import (
    aggregate_trainer_timing_targets,
    extract_trainer_practice_targets,
)
from pokemon_red_completion.red_trajectory import PokemonRedObservationEncoder

ROOT = Path(__file__).resolve().parents[1]
HORIZON = 20
MAX_DECISIONS = 80
MOVE = "pokemon.red.gb.us.rev0:move"
SPECIES = "pokemon.red.gb.us.rev0:species"
MOVES = {
    84: ((85, 15), (98, 30), (34, 15), (84, 30)),
    177: ((57, 15), (61, 20), (33, 35), (58, 10)),
    153: ((75, 25), (22, 10), (34, 15), (72, 10)),
    176: ((53, 15), (52, 25), (34, 15), (163, 20)),
}
FOES = ((150, 17), (169, 74), (177, 7), (153, 1))
FOLLOWERS = ((177, 7), (176, 4), (153, 1), (150, 17))
NATURAL_MOVES = {
    84: ((85, 15), (98, 30), (34, 15), (84, 30)),
    177: ((55, 25), (33, 35)),
    153: ((22, 10), (33, 35)),
    176: ((52, 25), (10, 35)),
    169: ((88, 15), (33, 35)),
    106: ((2, 25), (67, 20)),
    150: ((16, 35), (98, 30)),
}
NATIONAL = {84: 25, 177: 7, 153: 1, 176: 4, 169: 74, 106: 66, 150: 17}


def hard_curriculum_cases(templates, *, reserved=False):
    """Balanced five-on-five TRAIN fights, with basic reserve moves and mixed foes."""
    cases = []
    opponents = (106, 169, 150, 177, 153)
    for root_index, template in enumerate(templates):
        for foe_index in (0, 2) if reserved else range(4):
            practice = deepcopy(template)
            actor = int(practice["actor_species_ref"].rsplit(":", 1)[1])

            def moves(species):
                values = NATURAL_MOVES[species]
                if reserved:
                    values = tuple(reversed(values))
                return [{"move_ref": f"{MOVE}:{m:03d}", "pp": pp} for m, pp in values]

            def member(species, slot, level):
                return {
                    "party_slot": slot,
                    "species_ref": f"{SPECIES}:{species:03d}",
                    "national_number": NATIONAL[species],
                    "level": level,
                    "moves": moves(species),
                }

            practice["actor_moves"] = moves(actor)
            practice["actor_level"] = 32
            practice["actor_hp"] = 45 if reserved else (50 if foe_index % 2 == 0 else 35)
            practice.pop("actor_stats", None)
            practice.pop("opponent_stats", None)
            practice["party_reserves"] = [
                member(species, slot, 32)
                for slot, species in enumerate(
                    (s for s in (84, 177, 153, 176, 169) if s != actor), 2
                )
            ]
            roster = opponents[foe_index:] + opponents[:foe_index]
            level = 29 if reserved else (28 if foe_index % 2 == 0 else 30)
            practice.update(
                {
                    "opponent_species_ref": f"{SPECIES}:{roster[0]:03d}",
                    "opponent_national_number": NATIONAL[roster[0]],
                    "opponent_level": level,
                    "opponent_moves": moves(roster[0]),
                    "opponent_party_count": 5,
                    "opponent_reserves": [
                        member(species, slot, level) for slot, species in enumerate(roster[1:], 2)
                    ],
                }
            )
            practice["opponent_hp"] = 53 if reserved else 55
            cases.append((root_index, foe_index, practice))
    return tuple(cases)


class StatDamageTeacher:
    """Training continuation: attack by visible damage factors, replace on faint."""

    policy_id = "train-teacher-stat-damage-decline-optional-v1"

    def __init__(self):
        from pokemon_red_completion.red_battle_catalog import PokemonRedBattleCatalog

        self.catalog = PokemonRedBattleCatalog()
        self.last_decision_diagnostics = {}

    def choose_main(self, observation, prepared):
        features = project_trainer_move_features(observation, prepared.features)
        power = features.feature_names.index("move.accuracy_weighted_effective_power_fraction")
        physical = features.feature_names.index(
            "interaction.physical_attack_over_estimated_defense"
        )
        special = features.feature_names.index("interaction.special_over_estimated_special")
        legal = [i for i, ok in enumerate(prepared.supported_candidate_mask) if ok]
        if not legal:
            party = observation["features"]["party"]
            slots = tuple(
                i + 1
                for i, member in enumerate(party["members"])
                if i != party["active_index"] and member["hp"] > 0
            )
            return BattleAction.switch(
                self.choose_switch(observation, slots, forced=True, may_decline=False)
            )
        scores = [row[power] * (row[physical] + row[special]) for row in features.candidate_vectors]
        chosen = max(legal, key=lambda i: scores[i])
        self.last_decision_diagnostics = {"training_teacher": True, "damage_scores": scores}
        return BattleAction.move(features.candidate_slots[chosen])

    def choose_switch(self, observation, legal_party_slots, *, forced, may_decline):
        if may_decline:
            self.last_decision_diagnostics = {"training_teacher": True, "decline_optional": True}
            return None
        features = project_trainer_switch_features(observation, self.catalog)
        names = features.feature_names
        scores = {}
        for slot, row in zip(features.candidate_slots, features.candidate_vectors, strict=True):
            if slot in legal_party_slots:
                scores[slot] = (
                    row[names.index("candidate.offensive_power")]
                    * max(
                        row[names.index("candidate.stat.attack")],
                        row[names.index("candidate.stat.special")],
                    )
                    * (0.5 + row[names.index("candidate.hp_ratio")])
                )
        if not scores:
            raise ValueError("teacher has no living replacement")
        self.last_decision_diagnostics = {
            "training_teacher": True,
            "reserve_scores": {str(slot): score for slot, score in scores.items()},
        }
        return max(scores, key=scores.get)


def curriculum_cases(templates, *, reserved=False):
    """Sixteen training recipes; eight reserved numeric and move-order variations."""
    cases = []
    for root_index, template in enumerate(templates):
        for foe_index in range(4) if not reserved else (0, 2):
            practice = deepcopy(template)
            actor = int(practice["actor_species_ref"].rsplit(":", 1)[1])
            moves = MOVES[actor]
            if reserved:
                moves = tuple(reversed(moves))
            practice["actor_moves"] = [{"move_ref": f"{MOVE}:{m:03d}", "pp": pp} for m, pp in moves]
            practice["actor_hp"] = max(
                12, template["actor_hp"] - (25 if foe_index % 2 else 0) - (5 if reserved else 0)
            )
            practice["actor_level"] = 32
            practice.pop("actor_stats", None)
            practice.pop("opponent_stats", None)
            reserves = deepcopy(template["party_reserves"][:2])
            for member in reserves:
                member["level"] = 32
                member.pop("stats", None)
                member.pop("hp", None)
                species = int(member["species_ref"].rsplit(":", 1)[1])
                member["moves"] = [
                    {"move_ref": f"{MOVE}:{m:03d}", "pp": pp} for m, pp in MOVES[species]
                ]
            practice["party_reserves"] = reserves
            foe, national = FOES[foe_index]
            follower, follower_national = FOLLOWERS[foe_index]
            practice.update(
                {
                    "opponent_species_ref": f"{SPECIES}:{foe:03d}",
                    "opponent_national_number": national,
                    "opponent_level": 31 if reserved else 30,
                    "opponent_hp": 57 if reserved else 60,
                    "opponent_moves": [
                        {"move_ref": f"{MOVE}:033", "pp": 35},
                        {"move_ref": f"{MOVE}:098", "pp": 30},
                    ],
                    "opponent_party_count": 2,
                    "opponent_reserves": [
                        {
                            "party_slot": 2,
                            "species_ref": f"{SPECIES}:{follower:03d}",
                            "national_number": follower_national,
                            "level": 31 if reserved else 30,
                            "moves": [
                                {"move_ref": f"{MOVE}:033", "pp": 35},
                                {"move_ref": f"{MOVE}:098", "pp": 30},
                            ],
                        }
                    ],
                }
            )
            cases.append((root_index, foe_index, practice))
    return tuple(cases)


def retained_targets(plan):
    """Recheck retained branch logs without replaying their cartridge actions."""
    targets = []
    for scenario in plan["scenarios"]:
        capture = open_battle_scenario_capture(
            _bound_path(scenario["state"], "state"), _bound_path(scenario["manifest"], "manifest")
        )
        timed = []
        for offset, trial in zip(original.OFFSETS, scenario["trials"], strict=True):
            choices_path = _bound_path(trial["choices"], "choices")
            choice_plan_path = _bound_path(trial["plan"], "plan")
            document = json.loads(choices_path.read_bytes())
            choice_plan = json.loads(choice_plan_path.read_bytes())
            refs = tuple(choice_plan["first_choice_refs"])
            logs = {
                ref: choices_path.parent / f"{trial['branch_log_prefix']}-{i:02d}-events"
                for i, ref in enumerate(refs)
            }
            admission = inspect_trainer_practice_choices(
                capture,
                document,
                expected_choice_refs=refs,
                continuation_policy_id=choice_plan["continuation_policy_id"],
                branch_event_logs=logs,
                plan_sha256=original._binding(choice_plan_path)["sha256"],
                model_sha256=choice_plan["model_sha256"],
                max_decisions=choice_plan["max_decisions"],
                expected_opening_idle_frames=offset,
            )
            timed.append(extract_trainer_practice_targets(admission, document))
        targets.append(
            aggregate_trainer_timing_targets(tuple(timed), expected_offsets=original.OFFSETS)
        )
    return targets


def terminal_anchor_targets(model_path, required_capture_ids):
    """Recover a warm start's earlier terminal examples from authenticated logs."""
    targets = []
    for target_path in sorted(model_path.parent.glob("train/*/target-*.json")):
        retained = json.loads(target_path.read_bytes())
        if retained.get("capture_id") not in required_capture_ids:
            continue
        directory = target_path.parent
        capture_index = int(target_path.stem.rsplit("-", 1)[1])
        state_path = (
            directory / "materialized" / "assisted.state"
            if capture_index == 0
            else directory / f"intermediate-{capture_index:02d}.state"
        )
        capture = open_battle_scenario_capture(state_path, state_path.with_suffix(".state.json"))
        timed = []
        for offset in original.OFFSETS:
            branch_dir = directory / f"capture-{capture_index:02d}-timing-{offset:02d}"
            plan_path = branch_dir / "plan.json"
            plan = json.loads(plan_path.read_bytes())
            choices = json.loads((branch_dir / "choices.json").read_bytes())
            if plan["continuation_policy_id"] != StatDamageTeacher.policy_id:
                raise ValueError("terminal anchor continuation differs")
            refs = tuple(plan["first_choice_refs"])
            admission = inspect_trainer_practice_choices(
                capture,
                choices,
                expected_choice_refs=refs,
                continuation_policy_id=StatDamageTeacher.policy_id,
                branch_event_logs={
                    ref: branch_dir / f"branch-{i:02d}-events" for i, ref in enumerate(refs)
                },
                plan_sha256=original._binding(plan_path)["sha256"],
                model_sha256=plan["model_sha256"],
                max_decisions=plan["max_decisions"],
                expected_opening_idle_frames=offset,
            )
            timed.append(extract_trainer_practice_targets(admission, choices))
        target = aggregate_trainer_timing_targets(tuple(timed), expected_offsets=original.OFFSETS)
        if json.loads(json.dumps(target)) != retained:
            raise ValueError("terminal anchor target differs from measured branches")
        targets.append(target)
    if {target["capture_id"] for target in targets} != set(required_capture_ids):
        raise ValueError("warm-start terminal anchors are missing")
    return targets


def compatible_resume_declaration(previous, declaration):
    ignored = {"source_commit", "continuation_code_sha256"}
    # Additive retention of the already-bound warm start's prior TRAIN rows is
    # allowed before the first fit. It changes no executed recipe or branch.
    if "retained_terminal_anchor_ids" not in previous:
        ignored.add("retained_terminal_anchor_ids")
    return {k: v for k, v in previous.items() if k not in ignored} == json.loads(
        json.dumps({k: v for k, v in declaration.items() if k not in ignored})
    )


def run(args):
    resume = getattr(args, "resume", False)
    hard = getattr(args, "profile", "terminal") == "learner-five"
    recipes = hard_curriculum_cases if hard else curriculum_cases
    horizon = 40 if hard else HORIZON
    max_decisions = 160 if hard else MAX_DECISIONS
    maximum_frames = 240000 if hard else 120000
    capture_decisions = (2, 4, 6, 8) if hard else (2, 3)
    fit_seed = 2026091802 if hard else 2026091801
    if (
        args.output.exists() != resume
        or subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip()
    ):
        raise ValueError("terminal curriculum needs a new output and committed source")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    rom = original._binding(args.rom)
    if rom["sha256"] != original.ROM_SHA256:
        raise ValueError("terminal curriculum cartridge differs")
    sources = original._source_rows(args.batch)
    prior = json.loads(args.prior_plan.read_bytes())
    old_targets = retained_targets(prior)
    if len(old_targets) != 52:
        raise ValueError("terminal curriculum needs the retained 52-context anchor")
    frozen = TrainerPracticeThreeHeadModel.from_dict(json.loads(args.frozen_model.read_bytes()))
    if set(frozen.train_root_ids) != {row[1]["source_id"] for row in sources}:
        raise ValueError("terminal curriculum model roots differ")
    inherited_ids = set(frozen.train_capture_ids) - {target["capture_id"] for target in old_targets}
    inherited_targets = (
        terminal_anchor_targets(args.frozen_model, inherited_ids) if inherited_ids else []
    )
    templates = []
    for index in (0, 4, 8, 12):
        path = _bound_path(prior["scenarios"][index]["state"], "template state")
        templates.append(
            json.loads((path.parent.parent / "materialize-plan.json").read_bytes())["practice"]
        )
    if resume and (args.output / "model.json").exists():
        raise ValueError("collection resume cannot repeat a completed fit")
    args.output.mkdir(mode=0o700, parents=True, exist_ok=resume)
    code_sha = original._binding(Path(__file__))["sha256"]
    declaration = {
        "source_commit": commit,
        "prior_plan": original._binding(args.prior_plan),
        "frozen_model": original._binding(args.frozen_model),
        "rom": rom,
        "training_recipes": recipes(templates),
        "reserved_recipes": recipes(templates, reserved=True),
        "continuation": StatDamageTeacher.policy_id,
        "continuation_code_sha256": code_sha,
        "horizon": horizon,
        "max_intermediate_captures_per_recipe": len(capture_decisions),
        "timing_offsets": list(original.OFFSETS),
        "fit_seed": fit_seed,
        "epochs": 1200,
        "control_target_mode": "fitted_components",
        "promotion_eligible": False,
    }
    if hard:
        declaration.update(
            {
                "profile": "learner-five",
                "capture_decisions": list(capture_decisions),
                "trajectory_policy": "frozen-learner",
                "maximum_frames": maximum_frames,
                "max_decisions": max_decisions,
            }
        )
    if inherited_ids:
        declaration["retained_terminal_anchor_ids"] = sorted(inherited_ids)
    if resume:
        previous = json.loads((args.output / "plan.json").read_bytes())
        if not compatible_resume_declaration(previous, declaration):
            raise ValueError("resume changes a declared input or experiment")
        original._write(args.output / f"resume-{commit[:12]}.json", declaration)
    else:
        original._write(args.output / "plan.json", declaration)
    stats = RedPracticeCartridge(args.rom.read_bytes()).public_base_stats
    active = []

    @contextmanager
    def session_factory():
        with PyBoyAdapter(args.rom, watch=False, speed=None) as emulator:
            active.append(emulator)
            try:
                yield FrameBudgetController(emulator, maximum_frames=maximum_frames)
            finally:
                active.pop()

    def materialize(case, parent):
        root_index, foe_index, practice = case
        directory = parent / f"root-{root_index + 1:02d}-foe-{foe_index:02d}"
        source, receipt = sources[root_index]
        practice["root_lineage_id"] = receipt["source_id"]
        practice["source_state_sha256"] = original._binding(source / "source.state")["sha256"]
        if resume and directory.exists():
            declared = json.loads((directory / "materialize-plan.json").read_bytes())
            if declared["practice"] != practice or declared["rom"] != rom:
                raise ValueError("resumed materialization changes its recipe")
            state = directory / "materialized" / "assisted.state"
            restored = open_battle_scenario_capture(state, state.with_suffix(".state.json"))
            if restored.manifest.root_lineage_id != sources[root_index][1]["source_id"]:
                raise ValueError("resumed capture root differs")
            return directory, state
        directory.mkdir(mode=0o700, parents=True, exist_ok=False)
        path = directory / "materialize-plan.json"
        original._write(
            path,
            {
                "schema": materializer.TRAINER_SCHEMA,
                "source_commit": commit,
                "rom": rom,
                "source_state": original._binding(source / "source.state"),
                "source_capture_manifest": original._binding(source / "source.state.json"),
                "practice": practice,
                "observation_schema": OBSERVATION_SCHEMA_V2,
                "output": str(directory / "materialized"),
            },
        )
        materializer.run(path, check_only=True)
        materializer.run(path)
        return directory, directory / "materialized" / "assisted.state"

    def choices_for(capture):
        with session_factory() as session:
            session.load_state_bytes(capture.state_bytes)
            reader = PokemonRedStateReader(session)
            raw = reader.read()
            switches = tuple(
                TrainerPracticeFirstChoice(BattleAction.switch(i + 1))
                for i, hp in enumerate(raw.party_hp)
                if hp > 0 and i != raw.active_party_index
            )
            if raw.battler_hp == 0:
                return switches
            if reader.trainer_switch_prompt_visible(raw):
                return (TrainerPracticeFirstChoice(None), *switches)
            prepared = prepare_red_battle_scenario(
                PokemonRedObservationEncoder.from_state_reader(
                    reader, include_battle_stats=True, public_species_base_stats=stats
                ),
                raw,
                allow_no_attack=True,
            )
            return baseline._all_legal_opening_choices(
                prepared, raw.party_hp, raw.active_party_index
            )

    targets = []
    traces = []
    try:
        for case in recipes(templates):
            directory, state_path = materialize(case, args.output / "train")
            capture = open_battle_scenario_capture(
                state_path, state_path.with_suffix(".state.json")
            )
            paths = [state_path]
            trace_path = directory / "teacher-outcome.json"
            log = (
                None
                if trace_path.exists()
                else TrainerPracticeEventLog(
                    directory / "teacher-events",
                    run_identity={
                        "source_commit": commit,
                        "capture_manifest_sha256": capture.manifest_sha256,
                        "partition": "train",
                        "policy_id": "train-frozen-learner-trajectory-v1"
                        if hard
                        else StatDamageTeacher.policy_id,
                        "model_sha256": declaration["frozen_model"]["sha256"] if hard else code_sha,
                    },
                )
            )

            def save_intermediate(
                event, log=log, paths=paths, directory=directory, capture=capture
            ):
                log.emit(event)
                if (
                    event.get("event") != "decision_started"
                    or event.get("decision_index") not in capture_decisions
                    or len(paths) > len(capture_decisions)
                ):
                    return
                payload = active[-1].save_state_bytes()
                digest = hashlib.sha256(payload).hexdigest()
                path = directory / f"intermediate-{len(paths):02d}.state"
                path.write_bytes(payload)
                path.with_suffix(".state.json").write_bytes(
                    build_battle_scenario_capture_payload(
                        capture_id=f"terminal-intermediate-{digest[:24]}",
                        root_lineage_id=capture.manifest.root_lineage_id,
                        partition=capture.manifest.partition,
                        state_bytes=payload,
                        initial_observation_sha256=event["observation_sha256"],
                        source_commit=commit,
                        expected_map=capture.manifest.expected_map,
                        expected_battle_state=2,
                        source_state_sha256=capture.manifest.state_sha256,
                        observation_schema=OBSERVATION_SCHEMA_V2,
                    )
                )
                paths.append(path)

            if trace_path.exists():
                check = verify_trainer_practice_event_log(directory / "teacher-events")
                if not check["complete"]:
                    raise ValueError("resumed teacher trace is incomplete")
                trace_document = json.loads(trace_path.read_bytes())
                paths.extend(sorted(directory.glob("intermediate-*.state")))
                for path in paths[1:]:
                    child = open_battle_scenario_capture(path, path.with_suffix(".state.json"))
                    if child.manifest.source_state_sha256 != capture.manifest.state_sha256:
                        raise ValueError("resumed intermediate capture parent differs")
            else:
                trace = run_red_trainer_practice_episode(
                    capture,
                    session_factory=session_factory,
                    policy=(
                        RedTrainerPracticeOutcomePolicy(
                            policy_id="train-frozen-learner-trajectory-v1",
                            battle_plan_id=capture.manifest.capture_id,
                            model=frozen,
                        )
                        if hard
                        else StatDamageTeacher()
                    ),
                    max_decisions=max_decisions,
                    max_player_turns=horizon,
                    event_sink=save_intermediate,
                    public_species_base_stats=stats,
                )
                log.finish({"stop_reason": trace.stop_reason})
                trace_document = trace.public_dict()
                original._write(trace_path, trace_document)
                original._write(
                    directory / "teacher-log-check.json",
                    verify_trainer_practice_event_log(log.directory),
                )
            traces.append(trace_document["stop_reason"])
            for capture_index, path in enumerate(paths):
                current = open_battle_scenario_capture(path, path.with_suffix(".state.json"))
                first_choices = choices_for(current)
                if len(first_choices) < 2:
                    continue
                timed = []
                for offset in original.OFFSETS:
                    branch_dir = directory / f"capture-{capture_index:02d}-timing-{offset:02d}"
                    branch_dir.mkdir(mode=0o700, exist_ok=resume)
                    refs = tuple(choice.semantic_ref for choice in first_choices)
                    plan = {
                        "source_commit": current.manifest.source_commit,
                        "execution_source_commit": commit,
                        "capture_manifest_sha256": current.manifest_sha256,
                        "model_sha256": code_sha,
                        "continuation_policy_id": StatDamageTeacher.policy_id,
                        "first_choice_refs": list(refs),
                        "player_turn_horizon": horizon,
                        "max_decisions": max_decisions,
                        "opening_idle_frames": offset,
                    }
                    if (branch_dir / "plan.json").exists():
                        plan = json.loads((branch_dir / "plan.json").read_bytes())
                        if (
                            plan["first_choice_refs"] != list(refs)
                            or plan["capture_manifest_sha256"] != current.manifest_sha256
                            or plan["player_turn_horizon"] != horizon
                            or plan["opening_idle_frames"] != offset
                        ):
                            raise ValueError("resumed branch plan differs")
                    else:
                        original._write(branch_dir / "plan.json", plan)
                    plan_sha = original._binding(branch_dir / "plan.json")["sha256"]

                    def event_log(
                        index,
                        choice,
                        branch_dir=branch_dir,
                        plan=plan,
                        current=current,
                        plan_sha=plan_sha,
                    ):
                        return TrainerPracticeEventLog(
                            branch_dir / f"branch-{index:02d}-events",
                            run_identity={
                                **plan,
                                "capture_id": current.manifest.capture_id,
                                "root_lineage_id": current.manifest.root_lineage_id,
                                "partition": "train",
                                "policy_id": StatDamageTeacher.policy_id,
                                "plan_sha256": plan_sha,
                                "first_choice_ref": choice.semantic_ref,
                            },
                        )

                    def retain(index, choice, episode, branch_dir=branch_dir):
                        original._write(
                            branch_dir / f"branch-{index:02d}.json",
                            {
                                "first_choice_ref": choice.semantic_ref,
                                "episode": episode.public_dict(),
                            },
                        )

                    if not (branch_dir / "choices.json").exists():
                        measured = collect_trainer_practice_counterfactuals(
                            current,
                            session_factory=session_factory,
                            continuation_policy_factory=StatDamageTeacher,
                            first_choices=first_choices,
                            max_decisions=max_decisions,
                            player_turn_horizon=horizon,
                            branch_sink=retain,
                            branch_event_log_factory=event_log,
                            public_species_base_stats=stats,
                            opening_idle_frames=offset,
                        )
                        original._write(branch_dir / "choices.json", measured.public_dict())
                    document = json.loads((branch_dir / "choices.json").read_bytes())
                    if any(
                        b["episode"]["stop_reason"] not in {"battle_won", "party_defeated"}
                        for b in document["branches"]
                    ):
                        raise ValueError("terminal curriculum produced a truncated branch")
                    admission = inspect_trainer_practice_choices(
                        current,
                        document,
                        expected_choice_refs=refs,
                        continuation_policy_id=StatDamageTeacher.policy_id,
                        branch_event_logs={
                            ref: branch_dir / f"branch-{i:02d}-events" for i, ref in enumerate(refs)
                        },
                        plan_sha256=plan_sha,
                        model_sha256=plan["model_sha256"],
                        max_decisions=max_decisions,
                        expected_opening_idle_frames=offset,
                    )
                    timed.append(extract_trainer_practice_targets(admission, document))
                target = aggregate_trainer_timing_targets(
                    tuple(timed), expected_offsets=original.OFFSETS
                )
                original._write(directory / f"target-{capture_index:02d}.json", target)
                targets.append(target)
            print(
                json.dumps(
                    {"training_recipe_completed": len(traces), "terminal_targets": len(targets)}
                ),
                flush=True,
            )
        if len(targets) < 24:
            raise ValueError("terminal curriculum lacks intermediate decision supply")
        all_targets = old_targets + inherited_targets + targets
        fitted = fit_trainer_practice_three_heads(
            all_targets,
            seed=fit_seed,
            epochs=1200,
            require_corpus_floor=False,
            warm_start_move=frozen,
            warm_start_move_epochs=1200,
            control_target_mode="fitted_components",
        )
        model_path = args.output / "model.json"
        original._write(model_path, fitted.to_dict())
        reports = {
            "original44": summarize_trainer_practice_training(
                old_targets[:44], fitted, initial_move_model=frozen.move
            ),
            "retained52": summarize_trainer_practice_training(
                old_targets, fitted, initial_move_model=frozen.move
            ),
            "new_terminal": summarize_trainer_practice_training(
                targets, fitted, initial_move_model=frozen.move
            ),
        }
        if inherited_targets:
            reports["inherited_terminal"] = summarize_trainer_practice_training(
                inherited_targets, fitted, initial_move_model=frozen.move
            )
        original._write(
            args.output / "fit-receipt.json",
            {
                "new_terminal_contexts": len(targets),
                "retained_contexts": len(old_targets) + len(inherited_targets),
                "legacy_retained_contexts": len(old_targets),
                "inherited_terminal_contexts": len(inherited_targets),
                "source_commit": commit,
                "model": original._binding(model_path),
                "control_target_mode": fitted.control_target_mode,
                "reports": reports,
                "fits": 1,
                "authority_promotions": 0,
            },
        )
        # This is a TRAIN diagnostic regardless of retention. Its result cannot
        # promote a candidate which regresses on the original gates.
        evaluations = []
        for case in recipes(templates, reserved=True):
            directory, state_path = materialize(case, args.output / "reserved")
            for label, model in (("frozen", args.frozen_model), ("candidate", model_path)):
                plan_path = directory / f"{label}-plan.json"
                original._write(
                    plan_path,
                    {
                        "schema": model_runner.OUTCOME_SCHEMA,
                        "source_commit": commit,
                        "rom": rom,
                        "outcome_model": original._binding(model),
                        "capture_state": original._binding(state_path),
                        "capture_manifest": original._binding(
                            state_path.with_suffix(".state.json")
                        ),
                        "max_decisions": max_decisions,
                        "maximum_frames": maximum_frames,
                        "opening_idle_frames": 0,
                        "output": str(directory / label),
                    },
                )
                result = model_runner.run(plan_path)
                evaluations.append({"root": case[0], "foe": case[1], "model": label, **result})
        result = {
            "status": "terminal_curriculum_complete_train_only",
            "new_terminal_contexts": len(targets),
            "fits": 1,
            "authority_promotions": 0,
            "evaluations": evaluations,
            "reports": reports,
        }
        original._write(args.output / "summary.json", result)
        return result
    except Exception as error:
        original._write(
            args.output / (f"failure-{commit[:12]}.json" if resume else "failure.json"),
            {
                "error": str(error),
                "error_type": type(error).__name__,
                "terminal_contexts": len(targets),
                "teacher_traces": len(traces),
                "source_commit": commit,
            },
        )
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("rom", "batch", "prior-plan", "frozen-model", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--profile", choices=("terminal", "learner-five"), default="terminal")
    result = run(parser.parse_args())
    print(
        json.dumps(
            {"status": result["status"], "new_terminal_contexts": result["new_terminal_contexts"]}
        )
    )


if __name__ == "__main__":
    main()
