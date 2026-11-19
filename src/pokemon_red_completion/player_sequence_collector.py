"""Passive, prospectively bounded sequence diagnostics for the existing actor.

No model fit or native TRAIN admission. Source/partition declarations alone are
not proof. Independent native verification and a separate target contract remain
required. This observer has no emulator, controller, executor or scoring method.
"""

import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .living_dex_policy_codec import restore_living_dex_policy_menu
from .player_sequence_policy import SequenceChoiceContext
from .player_sequence_targets import (
    SEQUENCE_TARGET_CONTRACT,
    TASK_TERMINAL_TARGET_CONTRACT,
    TASK_TARGET_CONTRACTS,
    validate_sequence_target_contract,
)
from .player_sequence_value import sequence_feature_contract, sequence_feature_width
from .player_short_sequence import SequenceEnd, measure_sequence
from .provenance import canonical_sha256
from .recorded_branch_history import RecordedBranchHistory, recorded_option_history, STORY_HISTORY, validate_history_contract
from .red_sequence_receipts import RecordedSequenceProjection, read_sequence_prefix, recorded_story_continuation


class SequenceTraceCollector:
    def __init__(
        self,
        *,
        source_sha256: str,
        partition: str,
        horizon: int,
        feature_version: int = 6,
        target_contract: str = SEQUENCE_TARGET_CONTRACT,
        task_sha256: str | None = None,
        declaration_store=None,
        window_stride: int | None = None,
        history_contract: str = STORY_HISTORY,
        selection_history_contract: str | None = None,
    ):
        if (
            type(source_sha256) is not str
            or re.fullmatch(r"[0-9a-f]{64}", source_sha256) is None
            or partition not in {"train", "development"}
            or type(horizon) is not int
            or not 1 <= horizon <= 4
        ):
            raise ValueError("sequence collection declaration differs")
        validate_sequence_target_contract(target_contract)
        if (target_contract in TASK_TARGET_CONTRACTS) != (
            type(task_sha256) is str and re.fullmatch(r"[0-9a-f]{64}", task_sha256) is not None
        ):
            raise ValueError("task collection requires one explicit task identity")
        if target_contract == SEQUENCE_TARGET_CONTRACT and task_sha256 is not None:
            raise ValueError("legacy collection cannot claim task closure")
        if declaration_store is not None:
            from .private_artifacts import PrivateArtifactRoot
            if type(declaration_store) is not PrivateArtifactRoot:
                raise TypeError("sequence declaration requires the existing private journal")
        if window_stride is not None and (
            type(window_stride) is not int or not 1 <= window_stride <= horizon
        ):
            raise ValueError("sequence window stride must be in 1..horizon")
        self.window_stride = horizon if window_stride is None else window_stride
        self.overlapping = self.window_stride < horizon
        self.declaration_store = declaration_store
        self.target_contract, self.task_sha256, self.task_terminal = (
            target_contract,
            task_sha256,
            None,
        )
        sequence_feature_width(feature_version)
        validate_history_contract(history_contract)
        self.history_contract = history_contract
        self.selection_history_contract = history_contract if selection_history_contract is None else selection_history_contract
        validate_history_contract(self.selection_history_contract)
        self.feature_version = feature_version
        self.source = source_sha256
        self.partition = partition
        self.horizon = horizon
        self.root: Path | None = None
        self.receipts: tuple[str, ...] = ()
        self.anchors: list[dict[str, Any]] = []
        self.outcomes: list[dict[str, Any]] = []
        self.emitted_choices = 0
        self.windows = 0
        self.finished = False

    def _write(self, name: str, document: dict[str, Any]) -> None:
        from .red_autonomous_player import _record

        assert self.root is not None
        _record(self.root / "sequence" / name, document)

    def start(self, output: Path) -> None:
        if self.root is not None:
            raise ValueError("sequence collector cannot be reused")
        plan = json.loads((output / "plan.json").read_text())
        if (
            plan.get("continuous_player") is not True
            or plan.get("teacher_actions_allowed") is not False
        ):
            raise ValueError("sequence collector requires the continuous actor")
        self.plan_sha = canonical_sha256(plan)
        self.model_sha = plan["model_sha256"]
        self.root = output
        (output / "sequence").mkdir()
        declaration = dict(
                schema=(
                    "pokemon.player.sequence-collection.v4"
                    if self.overlapping
                    else "pokemon.player.sequence-collection.v3"
                    if self.task_sha256 is not None
                    else "pokemon.player.sequence-collection.v1"
                    if self.feature_version == 6
                    else "pokemon.player.sequence-collection.v2"
                ),
                **({"feature_version": self.feature_version} if self.feature_version != 6 else {}),
                **(
                    {"target_contract": self.target_contract, "task_sha256": self.task_sha256}
                    if self.task_sha256 is not None
                    else {}
                ),
                source_sha256=self.source,
                partition=self.partition,
                behavior_plan_sha256=self.plan_sha,
                behavior_model_sha256=self.model_sha,
                horizon=self.horizon,
                **({"window_stride": self.window_stride} if self.overlapping else {}),
                windows=("overlapping-model-choices-with-attached-support" if self.overlapping
                         else "nonoverlapping-model-choices-with-attached-support"),
                feature_contract=sequence_feature_contract(self.feature_version, self.history_contract),
                **({"history_contract": self.history_contract} if self.history_contract != STORY_HISTORY else {}),
                **({"selection_history_contract": self.selection_history_contract}
                   if self.selection_history_contract != self.history_contract else {}),
                training_eligible=False,
                scoring_changed="sequence_policy" in plan,
            )
        self._write("declaration.json", declaration)
        if self.declaration_store is not None:
            self.declaration_store.publish_sealed_record(
                "rnp-sequence-" + canonical_sha256(declaration),
                kind="red_native_sequence_declaration", record=declaration)

    def _prefix(self, boundary_sha256: str) -> RecordedSequenceProjection:
        if self.root is None or self.finished:
            raise ValueError("sequence collector is not active")
        return read_sequence_prefix(
            self.root,
            expected_plan_sha256=self.plan_sha,
            source_sha256=self.source,
            outcome_sha256=self.receipts,
            boundary_sha256=boundary_sha256,
        )

    def choice_context(self, options, *, boundary_sha256: str) -> SequenceChoiceContext:
        """Build pre-choice history only from this run's completed receipt prefix."""
        prefix = self._prefix(boundary_sha256)
        histories = tuple(
            recorded_option_history(prefix, kind=b.kind.value, objective_ref=b.story_objective_ref,
                history_contract=self.selection_history_contract, boundary_sha256=boundary_sha256,
                expected_source_sha256=self.source, expected_plan_sha256=self.plan_sha)
            for b in options.bindings)
        return SequenceChoiceContext(
            options.menu.policy_sha256,
            canonical_sha256(
                dict(
                    source_sha256=self.source,
                    plan_sha256=self.plan_sha,
                    boundary_sha256=boundary_sha256,
                    outcome_sha256=list(self.receipts),
                )
            ),
            histories,
            self.feature_version,
            history_contract=self.selection_history_contract,
        )

    def before_execution(self, *, ordinal: int, boundary_sha256: str, choice: Any) -> None:
        """Called after budget admission, before executing the selected binding."""
        if ordinal != len(self.receipts):
            raise ValueError("sequence choice ordinal differs")
        prefix = self._prefix(boundary_sha256)
        document = choice.public_dict()
        if document.get("mode") not in {"model_exploration", "model_greedy"}:
            return
        if len(prefix.choices) != len(self.anchors):
            raise ValueError("sequence sampled-choice census differs")
        assert self.root is not None
        intent = json.loads((self.root / f"step-{ordinal:03d}" / "intent.json").read_text())
        persisted = json.loads((self.root / f"step-{ordinal:03d}" / "decision.json").read_text())
        menu = restore_living_dex_policy_menu(intent["menu"]["menu"])
        if (
            canonical_sha256(persisted) != canonical_sha256(document)
            or intent["state_sha256"] != boundary_sha256
            or menu.policy_sha256 != document["menu_sha256"]
        ):
            raise ValueError("sequence pre-input decision differs")
        if recorded_story_continuation(self.root / f"step-{ordinal:03d}",
                                       json.loads((self.root / "plan.json").read_bytes()),
                                       intent, persisted):
            return
        if document.get("model_sha256") != self.model_sha:
            raise ValueError("sequence pre-input model differs")
        self._emit(prefix, final=False)
        selected = document["selected_candidate_index"]
        if type(selected) is not int or selected not in menu.available_indices:
            raise ValueError("sequence candidate was not available")
        history = recorded_option_history(prefix, kind=choice.selected_binding.kind.value,
            objective_ref=choice.selected_binding.story_objective_ref,
            history_contract=self.history_contract, boundary_sha256=boundary_sha256,
            expected_source_sha256=self.source, expected_plan_sha256=self.plan_sha)
        features = (
            menu.candidates[selected].vector(menu.context, feature_version=self.feature_version)
            + history.vector()
        )
        if "sequence_context" in intent:
            expected_context = self.choice_context(choice.options, boundary_sha256=boundary_sha256)
            if choice.sequence_policy is not None and choice.sequence_policy.selection_mode == "stable_costly_recurrence":
                from dataclasses import replace
                from .goal_search_memory import GoalSearchMemory
                from .red_costly_search_recurrence import search_contexts, witnesses
                step = self.root / f"step-{ordinal:03d}"
                before = json.loads((step / "before.json").read_bytes())
                private = json.loads((step / "costly-search-memory-before.json").read_bytes())
                contexts = search_contexts(choice.options, before["facts"])
                if (private["state_sha256"] != boundary_sha256
                        or canonical_sha256(private["contexts"]) != canonical_sha256(contexts)):
                    raise ValueError("costly search pre-input binding differs")
                memory = GoalSearchMemory.from_private_dict(private["memory"])
                expected_context = replace(expected_context, costly_search_witnesses=
                                           witnesses(contexts, memory, before["facts"]))
            if canonical_sha256(intent["sequence_context"]) != canonical_sha256(
                expected_context.document()
            ):
                raise ValueError("sequence selection did not use the recorded past")
        anchor = dict(
            schema="pokemon.player.sequence-anchor.v1",
            ordinal=ordinal,
            model_choice_index=len(self.anchors),
            before_sha256=boundary_sha256,
            decision_sha256=canonical_sha256(dict(intent=intent, decision=document)),
            previous_outcome_sha256=list(self.receipts),
            selected_candidate_index=selected,
            behavior_probability=document["probabilities"][selected],
            features=list(features),
            private_identity_feature_count=0,
            training_eligible=False,
        )
        self._write(f"anchor-{len(self.anchors):03d}.json", anchor)
        self.anchors.append(anchor)

    def after_outcome(self, outcome: dict[str, Any]) -> None:
        if self.root is None or self.finished or outcome.get("ordinal") != len(self.receipts):
            raise ValueError("sequence outcome ordinal differs")
        ordinal = len(self.receipts)
        persisted = json.loads((self.root / f"step-{ordinal:03d}" / "outcome.json").read_text())
        # Compare the exact JSON representation: native evidence contains tuples.
        # Canonical JSON preserves every recorded value while normalizing arrays.
        if canonical_sha256(persisted) != canonical_sha256(outcome):
            raise ValueError("sequence outcome was not persisted exactly")
        digest = canonical_sha256(persisted)
        self.receipts += (digest,)
        self.outcomes.append(persisted)
        self._write(
            f"receipt-{ordinal:03d}.json",
            dict(
                schema="pokemon.player.sequence-prefix.v1",
                ordinal=ordinal,
                outcome_sha256=digest,
                prefix_sha256=canonical_sha256(list(self.receipts)),
                observed_cost=persisted.get("observed_cost"),
                training_eligible=False,
            ),
        )

    def mark_task_terminal(self, *, task_sha256: str, boundary_sha256: str) -> None:
        """Seal a native adapter claim,not native proof or dataset admission.

        The independent native reader must bind the declared task and decode its
        initial/terminal predicate before the new target contract can be used.
        """
        if (
            self.root is None
            or self.finished
            or self.task_terminal is not None
            or self.target_contract not in TASK_TARGET_CONTRACTS
            or task_sha256 != self.task_sha256
            or not self.outcomes
        ):
            raise ValueError("task terminal claim has no matching prospective scope")
        last = self.outcomes[-1]
        from hashlib import sha256

        state = self.root / f"step-{len(self.outcomes) - 1:03d}" / "terminal.state"
        if (
            boundary_sha256 != last["terminal_state_sha256"]
            or sha256(state.read_bytes()).hexdigest() != boundary_sha256
            or last.get("safe_terminal") is not True
            or last.get("error_type") is not None
            or last.get("verification") != "succeeded"
        ):
            raise ValueError("task terminal claim lacks a clean matching boundary")
        self.task_terminal = dict(
            schema="pokemon.player.task-terminal-claim.v1",
            task_sha256=task_sha256,
            source_sha256=self.source,
            behavior_plan_sha256=self.plan_sha,
            terminal_sha256=boundary_sha256,
            last_outcome_sha256=self.receipts[-1],
            native_verification_required=True,
            training_eligible=False,
        )
        self._write("task-terminal.json", self.task_terminal)

    def _emit(self, prefix: RecordedSequenceProjection, *, final: bool) -> None:
        while self.emitted_choices < len(prefix.choices):
            start = self.emitted_choices
            count = min(self.horizon, len(prefix.choices) - start)
            if count < self.horizon and not final:
                break
            steps = prefix.choices[start : start + count]
            if len(self.anchors) < start + count:
                raise ValueError("sequence observed choices lack pre-input anchors")
            if any(
                s.decision_sha256 != a["decision_sha256"]
                for s, a in zip(
                    steps,
                    self.anchors[start : start + count],
                    strict=True,
                )
            ):
                raise ValueError("sequence anchor/observed choice differs")
            initial = prefix.initial_quests if start == 0 else prefix.choices[start - 1].quests
            end = (
                SequenceEnd.TASK_TERMINAL
                if final and self.task_terminal is not None and start + count == len(prefix.choices)
                else SequenceEnd.HORIZON
                if count == self.horizon
                else SequenceEnd.INTERRUPTED
            )
            measured = measure_sequence(
                steps,
                horizon=self.horizon,
                end=end,
                initial_quests=initial,
            )
            self._write(
                f"window-{self.windows:03d}.json",
                dict(
                    schema="pokemon.player.sequence-window-candidate.v2"
                    if self.task_sha256 is not None
                    else "pokemon.player.sequence-window-candidate.v1",
                    **(
                        {
                            "target_contract": self.target_contract,
                            "task_terminal": measured.end is SequenceEnd.TASK_TERMINAL,
                        }
                        if self.task_sha256 is not None
                        else {}
                    ),
                    anchor_sha256=canonical_sha256(self.anchors[start]),
                    first_model_choice=start,
                    prefix_outcome_sha256=list(self.receipts),
                    measurement=asdict(measured),
                    complete_window=measured.complete_window,
                    cash_accounting_basis=measured.cash_accounting_basis,
                    native_verification_required=True,
                    loss_accounting_complete=False,
                    training_eligible=False,
                ),
            )
            self.emitted_choices += min(self.window_stride, count)
            self.windows += 1

    def finish(self) -> None:
        if self.root is None or self.finished:
            raise ValueError("sequence collector is not active")
        boundary = self.source if not self.outcomes else self.outcomes[-1]["terminal_state_sha256"]
        error = None
        try:
            prefix = self._prefix(boundary)
            if self.task_terminal is not None:
                actor = json.loads((self.root / "result.json").read_bytes())
                if actor.get("stop_reason") != "declared_consequence_complete":
                    raise ValueError("task terminal claim conflicts with actual actor stop")
            self._emit(prefix, final=True)
        except (ValueError, KeyError, TypeError, OSError) as caught:
            # Preserve exceptional/partial records, never manufacture a full target.
            error = dict(type=type(caught).__name__, message=str(caught))
        self._write(
            "result.json",
            dict(
                schema="pokemon.player.sequence-collection-result.v3"
                if self.overlapping
                else "pokemon.player.sequence-collection-result.v2"
                if self.task_sha256 is not None
                else "pokemon.player.sequence-collection-result.v1",
                **(
                    {
                        "target_contract": self.target_contract,
                        "task_terminal_claim_sha256": None
                        if self.task_terminal is None
                        else canonical_sha256(self.task_terminal),
                    }
                    if self.task_sha256 is not None
                    else {}
                ),
                horizon=self.horizon,
                **({"window_stride": self.window_stride} if self.overlapping else {}),
                anchors=len(self.anchors),
                windows=self.windows,
                outcome_sha256=list(self.receipts),
                projection_error=error,
                unprojected_observed_costs=[row.get("observed_cost") for row in self.outcomes]
                if error is not None
                else [],
                training_eligible=False,
                fit_calls=0,
                promotions=0,
            ),
        )
        self.finished = True
