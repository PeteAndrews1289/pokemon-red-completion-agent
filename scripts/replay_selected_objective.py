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
    build_red_midgame_objective_skill_registry,
)
from pokemon_red_completion.red_player_observer import CapturedPokemonRedObserver
from pokemon_red_completion.red_trajectory import PokemonRedObservationEncoder
from pokemon_red_completion.rom import resolve_rom_path
from pokemon_red_completion.route import COMPLETION_QUEST
from pokemon_red_completion.specialists import SpecialistRegistry
from pokemon_red_completion.training_candidate_model import (
    TrainingCandidateMLP,
    TrainingCandidateShadowAudit,
    load_training_candidate_model,
)
from pokemon_red_completion.training_candidate_rank import TrainingCandidateDecision
from pokemon_red_completion.training_control import (
    TrainingControlAction,
    TrainingControlDecision,
    TrainingControlPhase,
)
from pokemon_red_completion.training_control_model import (
    TrainingControlMLP,
    TrainingControlShadowAudit,
    load_training_control_model,
)

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
    parser.add_argument(
        "--training-control-model",
        type=Path,
        help="authenticated seek/fight/flee/heal/stop model used inside the Blaine skill",
    )
    parser.add_argument("--training-control-model-sha256")
    parser.add_argument(
        "--training-candidate-model",
        type=Path,
        help="authenticated trainee/venue ranker used inside the Blaine skill",
    )
    parser.add_argument("--training-candidate-model-sha256")
    parser.add_argument(
        "--training-candidate-authority",
        action="store_true",
        help="let the candidate ranker execute trainee and venue choices",
    )
    parser.add_argument(
        "--training-control-battle-authority",
        action="store_true",
        help="let the training-control model execute battle fight/flee choices",
    )
    parser.add_argument(
        "--training-control-overworld-authority",
        action="store_true",
        help="let the training-control model execute overworld seek/heal/stop choices",
    )
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
        choices=tuple(range(1, 21)),
        default=1,
        help="execute one to twenty decisions through the registered Red skills",
    )
    args = parser.parse_args(argv)
    training_model_values = (
        args.training_control_model,
        args.training_control_model_sha256,
    )
    if any(value is not None for value in training_model_values) and not all(
        value is not None for value in training_model_values
    ):
        parser.error(
            "training control requires both --training-control-model and "
            "--training-control-model-sha256"
        )
    if (
        args.training_control_battle_authority
        or args.training_control_overworld_authority
    ) and args.training_control_model is None:
        parser.error("training-control authority requires an authenticated model")
    candidate_model_values = (
        args.training_candidate_model,
        args.training_candidate_model_sha256,
    )
    if any(value is not None for value in candidate_model_values) and not all(
        value is not None for value in candidate_model_values
    ):
        parser.error(
            "training candidate control requires both --training-candidate-model and "
            "--training-candidate-model-sha256"
        )
    if args.training_candidate_authority and args.training_candidate_model is None:
        parser.error("training-candidate authority requires an authenticated model")

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
    training_model: TrainingControlMLP | None = None
    training_audit: TrainingControlShadowAudit | None = None
    training_controlled_decisions = 0
    if args.training_control_model is not None:
        assert args.training_control_model_sha256 is not None
        training_model = load_training_control_model(
            args.training_control_model,
            expected_sha256=args.training_control_model_sha256,
        )
        training_audit = TrainingControlShadowAudit(training_model)
    training_candidate_model: TrainingCandidateMLP | None = None
    training_candidate_audit: TrainingCandidateShadowAudit | None = None
    training_candidate_controlled_decisions = 0
    if args.training_candidate_model is not None:
        assert args.training_candidate_model_sha256 is not None
        training_candidate_model = load_training_candidate_model(
            args.training_candidate_model,
            expected_sha256=args.training_candidate_model_sha256,
        )
        training_candidate_audit = TrainingCandidateShadowAudit(training_candidate_model)

    def training_decision_authority(
        decision: TrainingControlDecision,
    ) -> TrainingControlAction:
        nonlocal training_controlled_decisions
        assert training_audit is not None
        assert training_model is not None
        training_audit.observe(decision)
        controlled = (
            args.training_control_battle_authority
            if decision.observation.phase is TrainingControlPhase.BATTLE
            else args.training_control_overworld_authority
        )
        if controlled:
            training_controlled_decisions += 1
            return training_model.predict(decision.observation)
        return decision.action

    def training_candidate_decision_authority(
        decision: TrainingCandidateDecision,
    ) -> int:
        nonlocal training_candidate_controlled_decisions
        assert training_candidate_audit is not None
        assert training_candidate_model is not None
        training_candidate_audit.observe(decision)
        training_candidate_controlled_decisions += 1
        return training_candidate_model.predict(decision.observation)

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
        skills = build_red_midgame_objective_skill_registry(
            emulator,
            reader,
            executor,
            training_decision_authority=(
                training_decision_authority if training_model is not None else None
            ),
            training_candidate_decision_sink=(
                training_candidate_audit.observe
                if training_candidate_audit is not None and not args.training_candidate_authority
                else None
            ),
            training_candidate_decision_authority=(
                training_candidate_decision_authority
                if args.training_candidate_authority
                else None
            ),
        )
        loop = PortablePlayerLoop(
            graph=COMPLETION_QUEST,
            observer=observer,
            objective_policy=policy,
            # Composite skills are the only execution authority here. Any
            # unregistered choice is masked with a public reason rather than
            # falling back to a generic or fixed-route planner.
            specialists=SpecialistRegistry(()),
            executor=executor,
            objective_skills=skills,
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
            "training_control": _training_control_report(
                training_audit,
                model_file_sha256=args.training_control_model_sha256,
                battle_authority=args.training_control_battle_authority,
                overworld_authority=args.training_control_overworld_authority,
                controlled_decisions=training_controlled_decisions,
            ),
            "training_candidate_control": _training_candidate_control_report(
                training_candidate_audit,
                model_file_sha256=args.training_candidate_model_sha256,
                authority=args.training_candidate_authority,
                controlled_decisions=training_candidate_controlled_decisions,
            ),
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


def _training_control_report(
    audit: TrainingControlShadowAudit | None,
    *,
    model_file_sha256: str | None,
    battle_authority: bool,
    overworld_authority: bool,
    controlled_decisions: int,
) -> dict[str, object] | None:
    if audit is None:
        return None
    summary = audit.public_dict()
    summary.update(
        {
            "model_file_sha256": model_file_sha256,
            "authority_phases": [
                phase
                for phase, enabled in (
                    ("battle", battle_authority),
                    ("overworld", overworld_authority),
                )
                if enabled
            ],
            "controlled_decisions": controlled_decisions,
            "model_had_execution_authority": controlled_decisions > 0,
            "teacher_fallback_on_model_disagreement": False,
            "promotion_eligible": False,
        }
    )
    return summary


def _training_candidate_control_report(
    audit: TrainingCandidateShadowAudit | None,
    *,
    model_file_sha256: str | None,
    authority: bool,
    controlled_decisions: int,
) -> dict[str, object] | None:
    if audit is None:
        return None
    summary = audit.public_dict()
    summary.update(
        {
            "model_file_sha256": model_file_sha256,
            "authority_choice_kinds": ["trainee", "venue"] if authority else [],
            "controlled_decisions": controlled_decisions,
            "model_had_execution_authority": authority and controlled_decisions > 0,
            "teacher_fallback_on_model_disagreement": False if authority else None,
            "portable_runtime_recertified": False,
            "promotion_eligible": False,
        }
    )
    return summary


if __name__ == "__main__":
    raise SystemExit(main())
