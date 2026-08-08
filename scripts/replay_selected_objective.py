#!/usr/bin/env python3
"""Select and execute one bounded Red objective from an authenticated capture.

The objective model receives the reconstructed semantic state and legal choices,
but no expected route label.  Only a registered fixed skill may execute the
selected objective, and completion is accepted only when a fresh observation
contains every declared semantic effect.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING
from pokemon_red_completion.captured_progress import load_captured_progress, write_captured_progress
from pokemon_red_completion.collection_protocol import (
    collection_document_sha256,
    objective_graph_document,
)
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.executor import FrameSafeExecutor
from pokemon_red_completion.learned_planner_policy import ModelObjectivePolicy
from pokemon_red_completion.objective_skills import ObjectiveSkill, ObjectiveSkillRegistry
from pokemon_red_completion.observation import PokemonRedStateReader
from pokemon_red_completion.planner_model import load_objective_model_artifact
from pokemon_red_completion.planner_semantics import ObjectiveFeatureProjector
from pokemon_red_completion.play import (
    QUALIFIED_OBJECTIVE_COMPLETION_CHECKPOINTS,
    QUALIFIED_PLAY_CHECKPOINT_COUNT,
)
from pokemon_red_completion.player_loop import PortablePlayerLoop
from pokemon_red_completion.provenance import (
    detect_source_identity,
    require_clean_source,
    require_published_source,
)
from pokemon_red_completion.quest import quest_graph_payload
from pokemon_red_completion.red_objective_skills import (
    DefeatErikaObjectiveSkill,
    DefeatKogaObjectiveSkill,
    DefeatSabrinaObjectiveSkill,
    LiberateSilphObjectiveSkill,
    ObtainSecretKeyObjectiveSkill,
    ObtainStrengthObjectiveSkill,
    ObtainSurfObjectiveSkill,
    PokemonTowerObjectiveSkill,
    ReachCinnabarObjectiveSkill,
    ReachFuchsiaObjectiveSkill,
    ReachSaffronObjectiveSkill,
    RocketHideoutObjectiveSkill,
)
from pokemon_red_completion.red_player_observer import CapturedPokemonRedObserver
from pokemon_red_completion.red_trajectory import PokemonRedObservationEncoder
from pokemon_red_completion.rom import resolve_rom_path
from pokemon_red_completion.route import COMPLETION_QUEST
from pokemon_red_completion.specialists import SpecialistRegistry

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument(
        "--envelope",
        type=Path,
        help="defaults to <state>.json",
    )
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    parser.add_argument("--out", type=Path, help="also write the sanitized JSON report here")
    parser.add_argument(
        "--out-state",
        type=Path,
        help="also save the private terminal emulator state and authenticated progress envelope",
    )
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--speed", type=int, choices=(1, 2, 4), default=2)
    parser.add_argument(
        "--max-decisions",
        type=int,
        choices=(1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12),
        default=1,
        help="execute one to twelve decisions through the registered Red skills",
    )
    args = parser.parse_args(argv)

    source = detect_source_identity(REPOSITORY_ROOT, include_untracked=True)
    require_clean_source(source)
    require_published_source(REPOSITORY_ROOT, source)
    envelope_path = args.envelope or args.state.with_name(args.state.name + ".json")
    envelope = load_captured_progress(envelope_path, state_path=args.state)
    projector = ObjectiveFeatureProjector(COMPLETION_QUEST)
    model = load_objective_model_artifact(
        args.model,
        expected_feature_names=projector.feature_names,
        expected_objective_graph_sha256=collection_document_sha256(
            objective_graph_document(quest_graph_payload(COMPLETION_QUEST))
        ),
    )

    rom = resolve_rom_path(args.rom)
    with PyBoyAdapter(
        rom,
        watch=args.watch,
        speed=args.speed if args.watch else None,
    ) as emulator:
        emulator.load_state(args.state)
        reader = PokemonRedStateReader(emulator)
        observer = CapturedPokemonRedObserver(reader, COMPLETION_QUEST, envelope)
        before = observer.observe()
        available_before = tuple(
            objective.id for objective in COMPLETION_QUEST.available_objectives(before)
        )
        policy = ModelObjectivePolicy(
            model=model,
            graph=COMPLETION_QUEST,
            snapshot_provider=PokemonRedObservationEncoder.from_state_reader(reader),
        )
        executor = FrameSafeExecutor(emulator, DEFAULT_NEW_GAME_TIMING.controller_timing())
        skills: list[ObjectiveSkill] = [
            RocketHideoutObjectiveSkill(emulator, reader, executor),
            PokemonTowerObjectiveSkill(emulator, reader, executor),
            ReachFuchsiaObjectiveSkill(emulator, reader, executor),
            ObtainSurfObjectiveSkill(emulator, reader, executor),
            DefeatKogaObjectiveSkill(emulator, reader, executor),
            ObtainStrengthObjectiveSkill(emulator, reader, executor),
            DefeatErikaObjectiveSkill(emulator, reader, executor),
            ReachSaffronObjectiveSkill(emulator, reader, executor),
            LiberateSilphObjectiveSkill(emulator, reader, executor),
            DefeatSabrinaObjectiveSkill(emulator, reader, executor),
            ReachCinnabarObjectiveSkill(emulator, reader, executor),
            ObtainSecretKeyObjectiveSkill(emulator, reader, executor),
        ]
        loop = PortablePlayerLoop(
            graph=COMPLETION_QUEST,
            observer=observer,
            objective_policy=policy,
            # Composite skills are the only execution authority here. Any
            # unregistered choice is masked with a public reason rather than
            # falling back to a generic or fixed-route planner.
            specialists=SpecialistRegistry(()),
            executor=executor,
            objective_skills=ObjectiveSkillRegistry(skills),
        )
        steps = tuple(loop.step() for _ in range(args.max_decisions))
        after = observer.observe()
        if args.out_state is not None:
            args.out_state.parent.mkdir(parents=True, exist_ok=True)
            emulator.save_state(args.out_state)

        report = {
            "schema": "pokemon-model-selected-objective-execution-v3",
            "status": "ok",
            "claim": (
                "An affordance-masked learned ranker selected executable objectives without "
                "expected labels; registered fixed skills executed them; fresh emulator "
                "observations verified every declared objective and side effect."
            ),
            "source": source.public_dict(),
            "capture": {
                "state_sha256": envelope.state_sha256,
                "checkpoint_id": envelope.checkpoint_id,
                "checkpoints_completed": envelope.checkpoints_completed,
            },
            "before": {
                "mode": before.mode.value,
                "location": before.location,
                "completed_objectives": sorted(COMPLETION_QUEST.completed_ids(before)),
                "available_objectives": list(available_before),
            },
            "decisions_and_executions": [step.public_dict() for step in steps],
            "after": {
                "mode": after.mode.value,
                "location": after.location,
                "facts_added": sorted(after.facts.difference(before.facts)),
                "completed_objectives": sorted(COMPLETION_QUEST.completed_ids(after)),
                "available_objectives": [
                    objective.id for objective in COMPLETION_QUEST.available_objectives(after)
                ],
            },
            "policy": policy.public_dict(),
            "loop": dict(loop.public_dict()),
            "assistance": {
                "model_decisions_executed": len(steps),
                "branching_model_decisions": sum(
                    len(step.executable_objectives) > 1 for step in steps
                ),
                "singleton_dispatches": sum(
                    len(step.executable_objectives) == 1 for step in steps
                ),
                "candidate_set_mode": "dependency_legal_and_skill_affordance_masked",
                "objective_selection": "learned_ranker",
                "expected_route_label_provided": False,
                "mechanic_execution": "teacher_authored_bounded_skill",
                "teacher_fallbacks": 0,
            },
            "limitations": [
                "captured_state_diagnostic",
                "bounded_model_decision_sequence",
                "singleton_dispatches_do_not_measure_ranking_quality",
                "fixed_teacher_authored_mechanic_skills",
                "not_a_clean_start_evaluation",
                "not_end_to_end_learned_gameplay",
            ],
        }

    if args.out_state is not None:
        completed_ids = COMPLETION_QUEST.completed_ids(after)
        verified = tuple(
            objective_id
            for _, objective_id in QUALIFIED_OBJECTIVE_COMPLETION_CHECKPOINTS
            if objective_id in completed_ids
        )
        completed_checkpoints = max(
            checkpoint_count
            for checkpoint_count, objective_id in QUALIFIED_OBJECTIVE_COMPLETION_CHECKPOINTS
            if objective_id in completed_ids
        )
        final_objective = steps[-1].objective_id
        write_captured_progress(
            args.out_state.with_name(args.out_state.name + ".json"),
            state_path=args.out_state,
            checkpoint_id=f"portable_loop_{final_objective}_terminal",
            checkpoint_label=f"Portable loop completed {final_objective}",
            checkpoints_completed=completed_checkpoints,
            checkpoints_total=QUALIFIED_PLAY_CHECKPOINT_COUNT,
            verified_objective_ids=verified,
        )

    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload, encoding="ascii")
    print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
