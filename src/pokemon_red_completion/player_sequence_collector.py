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
from .player_short_sequence import SequenceEnd, measure_sequence
from .provenance import canonical_sha256
from .recorded_branch_history import RecordedBranchHistory, recorded_branch_history
from .red_sequence_receipts import RecordedSequenceProjection, read_sequence_prefix


class SequenceTraceCollector:
    def __init__(self, *, source_sha256: str, partition: str, horizon: int):
        if (
            type(source_sha256) is not str or re.fullmatch(r"[0-9a-f]{64}", source_sha256) is None
            or partition not in {"train", "development"}
            or type(horizon) is not int or not 1 <= horizon <= 4
        ):
            raise ValueError("sequence collection declaration differs")
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
        if (plan.get("continuous_player") is not True
            or plan.get("teacher_actions_allowed") is not False):
            raise ValueError("sequence collector requires the continuous actor")
        self.plan_sha = canonical_sha256(plan)
        self.model_sha = plan["model_sha256"]
        self.root = output
        (output / "sequence").mkdir()
        self._write("declaration.json", dict(
            schema="pokemon.player.sequence-collection.v1", source_sha256=self.source,
            partition=self.partition, behavior_plan_sha256=self.plan_sha,
            behavior_model_sha256=self.model_sha, horizon=self.horizon,
            windows="nonoverlapping-model-choices-with-attached-support",
            feature_contract="v6-candidate-plus-eight-observed-branch-history-values-v1",
            training_eligible=False, scoring_changed="sequence_policy" in plan,
        ))

    def _prefix(self, boundary_sha256: str) -> RecordedSequenceProjection:
        if self.root is None or self.finished:
            raise ValueError("sequence collector is not active")
        return read_sequence_prefix(
            self.root, expected_plan_sha256=self.plan_sha, source_sha256=self.source,
            outcome_sha256=self.receipts, boundary_sha256=boundary_sha256,
        )

    def choice_context(self, options, *, boundary_sha256: str) -> SequenceChoiceContext:
        """Build pre-choice history only from this run's completed receipt prefix."""
        prefix = self._prefix(boundary_sha256)
        histories = tuple(
            recorded_branch_history(
                prefix, objective_ref=b.story_objective_ref, boundary_sha256=boundary_sha256,
                expected_source_sha256=self.source, expected_plan_sha256=self.plan_sha,
            ) if b.story_objective_ref is not None and prefix.choices
            else RecordedBranchHistory(0, 0, 0, 0, 0, 0, 0, 0)
            for b in options.bindings
        )
        return SequenceChoiceContext(options.menu.policy_sha256, canonical_sha256(dict(
            source_sha256=self.source, plan_sha256=self.plan_sha, boundary_sha256=boundary_sha256,
            outcome_sha256=list(self.receipts))), histories)

    def before_execution(self, *, ordinal: int, boundary_sha256: str, choice: Any) -> None:
        """Called after budget admission, before executing the selected binding."""
        if ordinal != len(self.receipts):
            raise ValueError("sequence choice ordinal differs")
        prefix = self._prefix(boundary_sha256)
        document = choice.public_dict()
        if document.get("mode") != "model_exploration":
            return
        if len(prefix.choices) != len(self.anchors):
            raise ValueError("sequence sampled-choice census differs")
        self._emit(prefix, final=False)
        assert self.root is not None
        intent = json.loads((self.root / f"step-{ordinal:03d}" / "intent.json").read_text())
        persisted = json.loads((self.root / f"step-{ordinal:03d}" / "decision.json").read_text())
        menu = restore_living_dex_policy_menu(intent["menu"]["menu"])
        if (
            persisted != document or intent["state_sha256"] != boundary_sha256
            or document.get("model_sha256") != self.model_sha
            or menu.policy_sha256 != document["menu_sha256"]
        ):
            raise ValueError("sequence pre-input decision differs")
        selected = document["selected_candidate_index"]
        if type(selected) is not int or selected not in menu.available_indices:
            raise ValueError("sequence candidate was not available")
        context = choice.selected_binding.story_objective_ref
        history = RecordedBranchHistory(0, 0, 0, 0, 0, 0, 0, 0)
        if context is not None and prefix.choices:
            history = recorded_branch_history(
                prefix, objective_ref=context, boundary_sha256=boundary_sha256,
                expected_source_sha256=self.source, expected_plan_sha256=self.plan_sha,
            )
        features = (
            menu.candidates[selected].vector(menu.context, feature_version=6) + history.vector()
        )
        if "sequence_context" in intent:
            expected_context = self.choice_context(choice.options, boundary_sha256=boundary_sha256)
            if canonical_sha256(intent["sequence_context"]) != canonical_sha256(
                expected_context.document()
            ):
                raise ValueError("sequence selection did not use the recorded past")
        anchor = dict(
            schema="pokemon.player.sequence-anchor.v1", ordinal=ordinal,
            model_choice_index=len(self.anchors), before_sha256=boundary_sha256,
            decision_sha256=canonical_sha256(dict(intent=intent, decision=document)),
            previous_outcome_sha256=list(self.receipts), selected_candidate_index=selected,
            behavior_probability=document["probabilities"][selected],
            features=list(features), private_identity_feature_count=0,
            training_eligible=False,
        )
        self._write(f"anchor-{len(self.anchors):03d}.json", anchor)
        self.anchors.append(anchor)

    def after_outcome(self, outcome: dict[str, Any]) -> None:
        if self.root is None or self.finished or outcome.get("ordinal") != len(self.receipts):
            raise ValueError("sequence outcome ordinal differs")
        ordinal = len(self.receipts)
        persisted = json.loads((self.root / f"step-{ordinal:03d}" / "outcome.json").read_text())
        if persisted != outcome:
            raise ValueError("sequence outcome was not persisted exactly")
        digest = canonical_sha256(persisted)
        self.receipts += (digest,)
        self.outcomes.append(persisted)
        self._write(f"receipt-{ordinal:03d}.json", dict(
            schema="pokemon.player.sequence-prefix.v1", ordinal=ordinal,
            outcome_sha256=digest, prefix_sha256=canonical_sha256(list(self.receipts)),
            observed_cost=persisted.get("observed_cost"), training_eligible=False,
        ))

    def _emit(self, prefix: RecordedSequenceProjection, *, final: bool) -> None:
        while self.emitted_choices < len(prefix.choices):
            start = self.emitted_choices
            count = min(self.horizon, len(prefix.choices) - start)
            if count < self.horizon and not final:
                break
            steps = prefix.choices[start:start + count]
            if len(self.anchors) < start + count:
                raise ValueError("sequence observed choices lack pre-input anchors")
            if any(s.decision_sha256 != a["decision_sha256"] for s, a in zip(
                steps, self.anchors[start:start + count], strict=True,
            )):
                raise ValueError("sequence anchor/observed choice differs")
            initial = prefix.initial_quests if start == 0 else prefix.choices[start - 1].quests
            end = SequenceEnd.HORIZON if count == self.horizon else SequenceEnd.INTERRUPTED
            measured = measure_sequence(
                steps, horizon=self.horizon, end=end, initial_quests=initial,
            )
            self._write(f"window-{self.windows:03d}.json", dict(
                schema="pokemon.player.sequence-window-candidate.v1",
                anchor_sha256=canonical_sha256(self.anchors[start]),
                first_model_choice=start, prefix_outcome_sha256=list(self.receipts),
                measurement=asdict(measured), complete_window=measured.complete_window,
                cash_accounting_basis=measured.cash_accounting_basis,
                native_verification_required=True, loss_accounting_complete=False,
                training_eligible=False,
            ))
            self.emitted_choices += count
            self.windows += 1

    def finish(self) -> None:
        if self.root is None or self.finished:
            raise ValueError("sequence collector is not active")
        boundary = self.source if not self.outcomes else self.outcomes[-1]["terminal_state_sha256"]
        error = None
        try:
            prefix = self._prefix(boundary)
            self._emit(prefix, final=True)
        except (ValueError, KeyError, TypeError, OSError) as caught:
            # Preserve exceptional/partial records, never manufacture a full target.
            error = dict(type=type(caught).__name__, message=str(caught))
        self._write("result.json", dict(
            schema="pokemon.player.sequence-collection-result.v1", horizon=self.horizon,
            anchors=len(self.anchors), windows=self.windows,
            outcome_sha256=list(self.receipts), projection_error=error,
            unprojected_observed_costs=[row.get("observed_cost") for row in self.outcomes]
            if error is not None else [],
            training_eligible=False, fit_calls=0, promotions=0,
        ))
        self.finished = True
