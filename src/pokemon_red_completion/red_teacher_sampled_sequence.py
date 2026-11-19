"""Bounded model sampling inside the existing isolated direct TRAIN fixture.

This adapter owns no source selection, runtime factory, battler or fitting API.
The parent teacher authenticates those before passing its existing session.
"""

import json
from pathlib import Path

from .goal_search_memory import GoalSearchMemory
from .observation import event_flag_is_set
from .player_sequence_collector import SequenceTraceCollector
from .red_autonomous_player import run_autonomous_options
from .red_native_player import finalize_native_player_session


def run_sampled_teacher_sequence(session, model, *, source, spec, seed, contract, write, output):
    data = spec.document()
    if (
        not spec.sequence_mode
        or source["partition"] != "train"
        or model.feature_version != 16
        or session.consequence is not None
        or contract.defeated_event is None
    ):
        raise ValueError("sampled teacher requires authenticated V16 TRAIN session")

    def task_done():
        raw = session.runtime.reader.read()
        return event_flag_is_set(raw.event_flags, contract.defeated_event)

    if task_done():
        raise ValueError("sampled TRAIN task is already complete")
    from .player_sequence_targets import TASK_TERMINAL_TARGET_CONTRACT

    task_sha = None
    if getattr(spec, "terminal_sequence_mode", False):
        from .constants import POKEMON_RED_US_REV_0
        from .red_sequence_state_audit import scoped_trainer_task_sha256

        task_sha = scoped_trainer_task_sha256(
            rom_sha256=POKEMON_RED_US_REV_0.sha256,
            maps=tuple(sorted({data["restoration_home_map"], contract.map_id})),
            events=(contract.defeated_event,),
        )
    collector = SequenceTraceCollector(
        source_sha256=source["state_sha256"],
        partition="train",
        horizon=data["sequence_horizon"],
        feature_version=16,
        **(
            {"target_contract": TASK_TERMINAL_TARGET_CONTRACT, "task_sha256": task_sha}
            if task_sha is not None
            else {}
        ),
    )
    memory = GoalSearchMemory()

    def stop():
        session.finish_decision()
        complete = task_done()
        if complete and task_sha is not None:
            collector.mark_task_terminal(
                task_sha256=task_sha, boundary_sha256=session.snapshot().sha256
            )
        return complete

    try:
        episode = run_autonomous_options(
            model=model,
            output=session.output / "episode",
            snapshot=session.snapshot,
            observe=session.observe,
            seed=seed,
            maximum_decisions=session.limits.decisions,
            maximum_seconds=session.limits.seconds,
            maximum_cash_spent=session.limits.cash_debits,
            provenance=dict(source=source),
            continuous_player=True,
            sequence_collector=collector,
            stop_after_outcome=stop,
            initial_search_memory=memory,
        )
        complete = task_done()
        snapshot = session.snapshot()
        collection = json.loads((session.output / "episode/sequence/result.json").read_bytes())
        clean = (
            collector.finished
            and collection["projection_error"] is None
            and episode["stop_reason"]
            in {"declared_consequence_complete", "decision_budget", "wall_time_budget"}
            and bool(episode["outcomes"])
            and all(
                row["error_type"] is None
                and (
                    row["verification"] == "succeeded"
                    or (
                        row["verification"] == "failed"
                        and row.get("ordinary_setback") is True
                        and row.get("safe_terminal") is True
                    )
                )
                for row in episode["outcomes"]
            )
        )
        result = dict(
            passed=bool(snapshot.safe and clean),
            collection_closed_without_error=bool(clean),
            teacher_selected=False,
            teacher_task_scope_declared=True,
            sampled_student_choices=True,
            goal_policy_queries=episode["model_decisions"],
            episode=episode,
            task_event_completed=complete,
            model_feature_version=16,
            training_admission=False,
            admitted=False,
            fit_allowed=False,
            sequence_horizon=data["sequence_horizon"],
            **(
                {"sequence_target_contract": TASK_TERMINAL_TARGET_CONTRACT, "task_sha256": task_sha}
                if task_sha is not None
                else {}
            ),
            field_ready=snapshot.safe,
            actual_credit=0,
        )
        write(Path(output) / "SAMPLED-SEQUENCE-RESULT.json", result)
        return result
    finally:
        finalize_native_player_session(session, memory)
