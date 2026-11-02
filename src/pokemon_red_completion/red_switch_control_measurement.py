"""One validated configuration from TRAIN branch collection through admission.

The caller owns native resource limits, source authentication and packet claims.
This seam never fits a model, retries a branch or admits a censored terminal.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .battle_actions import BattleAction
from .red_trainer_practice_admission import _valid_status_stages, inspect_trainer_practice_choices
from .red_trainer_practice_counterfactual import (
    TrainerPracticeFirstChoice,
    collect_trainer_practice_counterfactuals,
)
from .red_trainer_practice_episode import validate_opening_idle_frames
from .red_trainer_practice_log import TrainerPracticeEventLog
from .red_trainer_practice_targets import extract_trainer_practice_targets
from .scenario_lab import ScenarioPartition


@dataclass(frozen=True)
class SwitchMeasurementContract:
    max_decisions: int = 160
    player_turn_horizon: int = 80
    offsets: tuple[int, ...] = (0, 4, 8, 11, 12)
    allow_forced_struggle: bool = False

    def __post_init__(self):
        if (
            type(self.allow_forced_struggle) is not bool
            or type(self.max_decisions) is not int
            or not 2 <= self.max_decisions <= 160
            or type(self.player_turn_horizon) is not int
            or not 1 <= self.player_turn_horizon <= min(80, self.max_decisions)
            or not isinstance(self.offsets, tuple)
            or len(self.offsets) < 5
            or len(set(self.offsets)) != len(self.offsets)
        ):
            raise ValueError("incompatible measured-branch contract")
        for offset in self.offsets:
            validate_opening_idle_frames(offset)


def _first_choice(ref):
    if ref == "pokemon.core:battle:decline-switch":
        return TrainerPracticeFirstChoice(None)
    match = re.fullmatch(r"pokemon.core:battle:(move|switch):([1-6])", ref)
    if match is None or (match[1] == "move" and int(match[2]) > 4):
        raise ValueError("invalid first-choice reference")
    return TrainerPracticeFirstChoice(
        BattleAction.move(int(match[2]))
        if match[1] == "move"
        else BattleAction.switch(int(match[2]))
    )


def _write_new(path, document):
    with Path(path).open("x") as stream:
        json.dump(document, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")


def collect_admitted_switch_timing(
    capture,
    *,
    contract,
    offset,
    refs,
    policy_id,
    model_sha256,
    status_context,
    directory,
    session_factory,
    continuation_policy_factory,
    before_branch,
    public_species_base_stats=None,
    action_executor=None,
    decision_guard=None,
):
    """Freeze one timing, collect all legal alternatives, verify, then label.

    before_branch reserves the caller's endpoint/runtime budget before each log.
    The authenticated capture and all legal refs must be supplied prospectively.
    Losses are valid; unfinished branches are retained and rejected.
    """
    if not isinstance(contract, SwitchMeasurementContract):
        raise ValueError("validated measurement contract required")
    # Recheck even an object reconstructed without the dataclass constructor.
    contract.__post_init__()
    if (
        capture.manifest.partition is not ScenarioPartition.TRAIN
        or capture.manifest.expected_battle_state != 2
        or offset not in contract.offsets
        or type(offset) is not int
        or not isinstance(refs, tuple)
        or not 2 <= len(refs) <= 10
        or len(set(refs)) != len(refs)
        or not isinstance(policy_id, str)
        or not policy_id
        or not isinstance(model_sha256, str)
        or re.fullmatch("[0-9a-f]{64}", model_sha256) is None
    ):
        raise ValueError("invalid prospective measurement identity")
    first_choices = tuple(_first_choice(ref) for ref in refs)
    if status_context is not None and (
        not isinstance(status_context, dict)
        or status_context.get("schema") != "pokemon.core.battle.status-context.v1"
        or any(
            type(status_context.get(k)) is not bool
            for k in ("player_confused", "opponent_confused")
        )
        or any(
            not _valid_status_stages(status_context.get(k))
            for k in ("player_stages", "opponent_stages")
        )
    ):
        raise ValueError("invalid prospective status context")
    directory = Path(directory)
    identity = dict(
        source_commit=capture.manifest.source_commit,
        capture_id=capture.manifest.capture_id,
        capture_manifest_sha256=capture.manifest_sha256,
        root_lineage_id=capture.manifest.root_lineage_id,
        partition="train",
        model_sha256=model_sha256,
        policy_id=policy_id,
        max_decisions=contract.max_decisions,
        player_turn_horizon=contract.player_turn_horizon,
        opening_idle_frames=offset,
        first_choice_refs=list(refs),
        **({"allow_forced_struggle": True} if contract.allow_forced_struggle else {}),
        **(
            {"allow_status_moves": True, "native_status_context": status_context}
            if status_context is not None
            else {}
        ),
    )
    directory.mkdir(mode=0o700)
    _write_new(directory / "plan.json", identity)
    import hashlib

    plan_sha = hashlib.sha256((directory / "plan.json").read_bytes()).hexdigest()

    def event_log(index, choice):
        before_branch(index)
        return TrainerPracticeEventLog(
            directory / f"branch-{index:02d}-events",
            run_identity={
                **identity,
                "plan_sha256": plan_sha,
                "first_choice_ref": choice.semantic_ref,
            },
        )

    def retain(index, _choice, episode):
        _write_new(directory / f"branch-{index:02d}.json", episode.public_dict())
        if episode.stop_reason not in ("battle_won", "party_defeated"):
            raise ValueError("censored branch: " + episode.stop_reason)

    document = collect_trainer_practice_counterfactuals(
        capture,
        session_factory=session_factory,
        continuation_policy_factory=continuation_policy_factory,
        first_choices=first_choices,
        max_decisions=contract.max_decisions,
        player_turn_horizon=contract.player_turn_horizon,
        branch_event_log_factory=event_log,
        branch_sink=retain,
        public_species_base_stats=public_species_base_stats,
        opening_idle_frames=offset,
        action_executor=action_executor,
        decision_guard=decision_guard,
        allow_status_moves=status_context is not None,
        **({"allow_forced_struggle": True} if contract.allow_forced_struggle else {}),
    ).public_dict()
    _write_new(directory / "choices.json", document)
    # The durable event log is JSON, while a live observation may contain
    # immutable tuples. Admit the exact serialized receipt, not a type-sensitive
    # comparison between its in-memory sequences and their JSON list form.
    # All original log, hash, identity and return checks still run unchanged.
    document = json.loads((directory / "choices.json").read_bytes())
    admission = inspect_trainer_practice_choices(
        capture,
        document,
        expected_choice_refs=refs,
        continuation_policy_id=policy_id,
        branch_event_logs={r: directory / f"branch-{i:02d}-events" for i, r in enumerate(refs)},
        plan_sha256=plan_sha,
        model_sha256=model_sha256,
        max_decisions=contract.max_decisions,
        expected_opening_idle_frames=offset,
        expected_status_context=status_context,
        **({"allow_forced_struggle": True} if contract.allow_forced_struggle else {}),
    )
    target = extract_trainer_practice_targets(admission, document)
    _write_new(directory / "admission.json", admission)
    _write_new(directory / "target.json", target)
    return target
