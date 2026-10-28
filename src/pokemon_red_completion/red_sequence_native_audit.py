"""Read-only recorded policy/trace audit, not full native TRAIN admission."""

import json
import math
import random
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from .actions import MacroAction, MacroActionKind
from .living_dex_goal_policy import DEFAULT_LIVING_DEX_GOAL_UTILITY
from .living_dex_option_value import LivingDexOptionValueModel
from .living_dex_policy_codec import restore_living_dex_policy_menu
from .player_sequence_policy import SequenceChoiceContext, SequencePolicy
from .private_artifacts import PrivateArtifactRoot
from .provenance import canonical_sha256
from .recorded_branch_history import RecordedBranchHistory, recorded_branch_history
from .red_live_option_menu import RED_LIVE_MIXED_OPTION_POLICY
from .red_native_player import NativeExecutionIdentity, NativePlayerLimits
from .red_player_lesson_runtime import native_action_record_id
from .red_recorded_selection_authority import replay_selection_authority
from .red_sequence_receipts import read_sequence_prefix, read_sequence_receipts


def _read(path: Path) -> dict[str, Any]:
    row = json.loads(path.read_bytes())
    if not isinstance(row, dict):
        raise ValueError("native sequence audit needs an object")
    return row


def replay_recorded_sequence_choice(
    model: LivingDexOptionValueModel, intent: dict[str, Any], decision: dict[str, Any],
    *, seed: int, ordinal: int, sequence_policy: SequencePolicy | None = None,
) -> str:
    """Replay sampling conditional on recorded authority; never certify safety.

    No executor is reconstructed or called. Support remains labeled unaudited
    here, even if another verifier already checked its underlying mechanics.
    """
    decision_seed = int(canonical_sha256({"seed": seed, "ordinal": ordinal})[:16], 16)
    if (
        type(seed) is not int or seed < 0 or type(ordinal) is not int or ordinal < 0
        or intent.get("selection_seed") != decision_seed
        or type(intent.get("selection_seed")) is not int
        or intent.get("model_sha256") != (model.model_sha256 if sequence_policy is None
                                         else sequence_policy.model_sha256)
    ):
        raise ValueError("sequence policy seed/model differs")
    mode = decision.get("mode")
    if (sequence_policy is not None
        and intent.get("menu", {}).get("schema") != "pokemon.red.player-support.v1"):
        context = SequenceChoiceContext.from_document(intent["sequence_context"])
        menu = restore_living_dex_policy_menu(intent["menu"]["menu"])
        vectors = context.vectors(menu)
        if intent.get("query_may_be_consumed") is not (
            len({vectors[i] for i in menu.available_indices}) > 1
        ):
            raise ValueError("sequence recorded query authority differs")
        replay_selection_authority(model, intent, decision, allow_earning_exploration=True,
                                   sequence_policy=sequence_policy)
        return "support_requires_authority_audit" if mode == "deterministic_safety" else str(mode)
    if intent.get("menu", {}).get("schema") == "pokemon.red.player-support.v1" or (
        mode == "deterministic_safety"
    ):
        return "support_requires_authority_audit"
    menu = restore_living_dex_policy_menu(intent["menu"]["menu"])
    if model.feature_version < menu.feature_version:
        raise ValueError("sequence policy feature version differs")
    available = menu.available_indices
    distinct = len({menu.candidate_vector(i) for i in available}) > 1
    if intent.get("query_may_be_consumed") is not distinct:
        raise ValueError("sequence recorded query authority differs")
    if mode == "model_greedy":
        # Existing DEVELOPMENT selection,not a sampled sequence learner.
        # Authenticate its explicit opt-in,scores,one-hot choice and binding;
        # keep the shared seed and query checks above. Full TRAIN admission
        # remains governed separately by the sequence receipt protocol.
        replay_selection_authority(model, intent, decision, allow_earning_exploration=True)
        return "model_greedy"
    scores: tuple[float | None, ...]
    if not distinct:
        expected_mode = "equivalent_exploration"
        scores = (None,) * len(menu.candidates)
        probabilities = tuple(1.0 / len(available) if i in available else 0.0
                              for i in range(len(menu.candidates)))
        selected = random.Random(decision_seed).choice(available)
    else:
        expected_mode = "model_exploration"
        scores = model.scores(menu, DEFAULT_LIVING_DEX_GOAL_UTILITY)
        concrete = [scores[i] for i in available]
        if any(value is None or not math.isfinite(value) for value in concrete):
            raise ValueError("sequence replay produced invalid model scores")
        values = [float(value) for value in concrete if value is not None]
        peak = max(values)
        weights = [math.exp(value - peak) for value in values]
        balanced = decision.get("policy_id") == "red-live-kind-balanced-option-v1"
        kind_counts = {
            kind: sum(menu.candidates[i].features.kind == kind for i in available)
            for kind in {menu.candidates[i].features.kind for i in available}
        }
        if balanced:
            weights = [weight / kind_counts[menu.candidates[i].features.kind]
                       for i, weight in zip(available, weights, strict=True)]
        total = sum(weights)
        distribution = [0.0] * len(menu.candidates)
        for i, weight in zip(available, weights, strict=True):
            exploratory = (1.0 / (len(kind_counts) * kind_counts[menu.candidates[i].features.kind])
                           if balanced else 1.0 / len(available))
            distribution[i] = 0.75 * weight / total + 0.25 * exploratory
        probabilities = tuple(distribution)
        selected = random.Random(decision_seed).choices(
            range(len(distribution)), weights=distribution, k=1,
        )[0]
    expected = dict(
        actions_executed=0, candidate_count=len(menu.candidates), emulator_frames=0,
        menu_sha256=menu.policy_sha256, mode=expected_mode, model_sha256=model.model_sha256,
        policy_id=RED_LIVE_MIXED_OPTION_POLICY, private_binding_fields=0, private_path_fields=0,
        probabilities=list(probabilities), schema="pokemon.red.live-mixed-option-choice.v1",
        scores=[None if value is None else float(value) for value in scores],
        selected_candidate_index=selected,
        selected_option_kind=menu.candidates[selected].features.kind.value, teacher_labels=0,
    )
    if distinct and decision.get("policy_id") == "red-live-kind-balanced-option-v1":
        expected["policy_id"] = "red-live-kind-balanced-option-v1"
        expected["sampling_rule"] = "mean_exponential_weight_per_public_option_kind"
    if canonical_sha256(decision) != canonical_sha256(expected):
        raise ValueError("recorded sequence choice does not replay")
    return expected_mode


@dataclass(frozen=True)
class NativeSequenceTraceAudit:
    native_plan_sha256: str
    source_sha256: str
    partition: str
    model_choices_replayed: int
    equivalent_choices_replayed: int
    support_requiring_authority_audit: int
    actions: int
    frames: int
    trace_sha256: str
    training_eligible: bool = False
    native_state_facts_verified: bool = False
    source_ancestry_verified: bool = False
    safety_and_executor_authority_verified: bool = False
    recorded_selector_and_binding_replayed: int = 0


def audit_native_sequence_trace(
    root: Path, *, store: PrivateArtifactRoot, model: LivingDexOptionValueModel,
    expected_native_plan_sha256: str, expected_actor_result_sha256: str, source_sha256: str,
    sequence_policy: SequencePolicy | None = None,
) -> NativeSequenceTraceAudit:
    """Reuse sealed input receipts, with no emulator or new model selection."""
    plan, costs = _read(root / "native-plan.json"), _read(root / "native-costs.json")
    policy_sha256 = model.model_sha256 if sequence_policy is None else sequence_policy.model_sha256
    if sequence_policy is not None and sequence_policy.baseline_sha256 != model.model_sha256:
        raise ValueError("native sequence audit baseline differs")
    execution = NativeExecutionIdentity(**plan["execution"])
    limits = NativePlayerLimits(**plan["limits"])
    claim = store.find_sealed_record(
        execution.claim_id, expected_kind="red_native_player_execution",
    )
    if (
        canonical_sha256(plan) != expected_native_plan_sha256
        or claim is None or canonical_sha256(claim.read()) != expected_native_plan_sha256
        or plan.get("schema") != "pokemon.red.native-continuous-player.v2"
        or plan.get("automatic_fit") is not False or plan.get("promotion") is not False
        or plan["source"].get("state_sha256") != source_sha256
        or sha256((root / "source.state").read_bytes()).hexdigest() != source_sha256
        or plan["source"].get("partition") not in {"train", "development"}
        or execution.model_sha256 != policy_sha256
    ):
        raise ValueError("native sequence source/execution declaration differs")
    episode = root / "episode"
    actor_plan = _read(episode / "plan.json")
    if (
        actor_plan.get("seed") != execution.seed
        or actor_plan.get("model_sha256") != policy_sha256
        or actor_plan.get("provenance") != {"source": plan["source"]}
        or actor_plan.get("exploration_mix") != (
            .25 if sequence_policy is None else sequence_policy.exploration_mix)
        or canonical_sha256(actor_plan.get("sequence_policy")) != canonical_sha256(
            None if sequence_policy is None else sequence_policy.document())
        or actor_plan.get("maximum_decisions") != limits.decisions
        or actor_plan.get("maximum_seconds") != limits.seconds
        or actor_plan.get("maximum_cash_spent") != limits.cash_debits
    ):
        raise ValueError("native sequence actor plan differs")
    projection = read_sequence_receipts(
        episode, expected_plan_sha256=canonical_sha256(actor_plan),
        expected_result_sha256=expected_actor_result_sha256, source_sha256=source_sha256,
    )
    outcomes = _read(episode / "result.json")["outcomes"]
    final_sha = outcomes[-1]["terminal_state_sha256"]
    if sha256((root / "terminal.state").read_bytes()).hexdigest() != final_sha:
        raise ValueError("native sequence final state differs")
    n = costs.get("actions_attempted")
    if (
        costs.get("schema") != "pokemon.red.native-player-costs.v1"
        or type(n) is not int or not 0 < n <= limits.actions
        or type(costs.get("actions_completed")) is not int or costs["actions_completed"] != n
        or type(costs.get("frames")) is not int or not 0 < costs["frames"] <= limits.frames
        or costs.get("automatic_fit") is not False or costs.get("promotions") != 0
        or costs.get("buttons_released") is not True
        or type(costs.get("goal_attempts")) is not int
        or costs["goal_attempts"] != len(outcomes) or len(outcomes) > limits.decisions
        or type(costs.get("seconds")) not in (int, float)
        or not math.isfinite(costs["seconds"]) or not 0 <= costs["seconds"] <= limits.seconds
        or type(costs.get("restore_attempts")) is not int
        or not 0 <= costs["restore_attempts"] <= limits.heals
        or type(costs.get("nested_restore_attempts")) is not int
        or not 0 <= costs["nested_restore_attempts"] <= costs["restore_attempts"]
    ):
        raise ValueError("native sequence cost coverage is incomplete")
    traces: list[dict[str, Any]] = []
    frame = 0
    for index in range(n):
        a = store.find_sealed_record(
            native_action_record_id("action", expected_native_plan_sha256, index),
            expected_kind="red_native_lesson_action")
        b = store.find_sealed_record(
            native_action_record_id("trace", expected_native_plan_sha256, index),
            expected_kind="red_native_lesson_trace")
        if a is None or b is None:
            raise ValueError("native sequence action/trace receipt missing")
        intent: dict[str, Any] = dict(a.read())
        trace: dict[str, Any] = dict(b.read())
        MacroAction(MacroActionKind(intent["action"]), intent["value"], intent["repeat"])
        if (
            set(intent) != {"ordinal", "before_frame", "action", "value", "repeat"}
            or set(trace) != {"ordinal", "before_frame", "after_frame", "succeeded"}
            or type(intent.get("ordinal")) is not int or type(trace.get("ordinal")) is not int
            or type(intent.get("before_frame")) is not int
            or type(trace.get("before_frame")) is not int
            or intent.get("ordinal") != index or trace.get("ordinal") != index
            or intent.get("before_frame") != frame or trace.get("before_frame") != frame
            or trace.get("succeeded") is not True
            or type(trace.get("after_frame")) is not int or trace["after_frame"] <= frame
        ):
            raise ValueError("native sequence action/trace continuity differs")
        traces.append(dict(intent=intent, trace=trace))
        frame = trace["after_frame"]
    if frame != costs["frames"]:
        raise ValueError("native sequence frame total differs")
    if any(store.find_sealed_record(
               native_action_record_id(kind, expected_native_plan_sha256, n)) is not None
           for kind in ("action", "trace")):
        raise ValueError("native sequence omits an additional attempted input")
    offset = 0
    modes = []
    authority_replays = 0
    for ordinal, outcome in enumerate(outcomes):
        before, after, observed = outcome["before"], outcome["after"], outcome["observed_cost"]
        count = observed["actions"]
        part = traces[offset:offset + count]
        if (
            len(part) != count or not part or before["actions"] != offset
            or before["completed_actions"] != offset or after["actions"] != offset + count
            or after["completed_actions"] != offset + count
            or part[0]["trace"]["before_frame"] != before["frames"]
            or part[-1]["trace"]["after_frame"] != after["frames"]
        ):
            raise ValueError("native sequence goal owns a different trace interval")
        step = episode / f"step-{ordinal:03d}"
        intent, decision = _read(step / "intent.json"), _read(step / "decision.json")
        sequence_query = (sequence_policy is not None
                          and intent["menu"]["schema"] != "pokemon.red.player-support.v1")
        if sequence_query:
            receipts = tuple(canonical_sha256(row) for row in outcomes[:ordinal])
            boundary = intent["state_sha256"]
            prefix = read_sequence_prefix(
                episode, expected_plan_sha256=canonical_sha256(actor_plan),
                source_sha256=source_sha256,
                outcome_sha256=receipts, boundary_sha256=boundary)
            bindings = intent["private_selection_authority"]["live_bindings"]
            private = intent.get("private_story_contexts", [
                dict(binding_ref=b["binding_ref"], objective_ref=None) for b in bindings])
            if (len(private) != len(bindings)
                or any(p["binding_ref"] != b["binding_ref"]
                       for p, b in zip(private, bindings, strict=True))):
                raise ValueError("sequence history binding order differs")
            histories = tuple(recorded_branch_history(
                prefix, objective_ref=p["objective_ref"], boundary_sha256=boundary,
                expected_source_sha256=source_sha256,
                expected_plan_sha256=canonical_sha256(actor_plan))
                if p["objective_ref"] is not None and prefix.choices
                else RecordedBranchHistory(0, 0, 0, 0, 0, 0, 0, 0) for p in private)
            expected_context = SequenceChoiceContext(intent["menu"]["menu_sha256"],
                canonical_sha256(dict(source_sha256=source_sha256,
                plan_sha256=canonical_sha256(actor_plan),
                boundary_sha256=boundary, outcome_sha256=list(receipts))), histories)
            if canonical_sha256(intent["sequence_context"]) != canonical_sha256(
                expected_context.document()
            ):
                raise ValueError("sequence scoring history differs from completed prefix")
        if "private_selection_authority" in intent:
            selected_ref = replay_selection_authority(
                model, intent, decision, allow_earning_exploration=True,
                sequence_policy=sequence_policy if sequence_query else None,
            )
            if selected_ref != _read(step / "execution-started.json")["selected_binding_ref"]:
                raise ValueError("recorded selection executed a different binding")
            authority_replays += 1
        modes.append(replay_recorded_sequence_choice(
            model, intent, decision,
            seed=execution.seed, ordinal=ordinal,
            sequence_policy=sequence_policy,
        ))
        offset += count
    if offset != n or modes.count("model_exploration") != len(projection.choices):
        raise ValueError("native sequence action/choice census differs")
    return NativeSequenceTraceAudit(
        expected_native_plan_sha256, source_sha256, plan["source"]["partition"],
        modes.count("model_exploration"), modes.count("equivalent_exploration"),
        modes.count("support_requires_authority_audit"), n, frame, canonical_sha256(traces),
        recorded_selector_and_binding_replayed=authority_replays,
    )
