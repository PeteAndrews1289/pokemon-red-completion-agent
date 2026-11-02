"""Read the existing live battler's authenticated, changing aftermath.

Bind before the first battle. This is a read-only provider for NativePlayerSession;
it opens neither an emulator nor unrelated historical runs. Missing/incomplete
new battles refuse fresh inference instead of silently returning stale history.
"""

import json
from hashlib import sha256

from .battle_scenario_capture import open_battle_scenario_capture
from .post_battle_strategy import BattleAftermath
from .provenance import canonical_sha256
from .red_learned_trainer import FrozenTrainerBattler, story_battle_authority
from .red_post_battle_strategy import red_battle_aftermath
from .red_trainer_practice_log import verify_trainer_practice_event_log
from .scenario_lab import ScenarioPartition


class NativeBattlerHistory:
    def __init__(self, battler, *, initial=None):
        if not isinstance(battler, FrozenTrainerBattler) or battler.calls != 0:
            raise ValueError("battle history must bind the fresh live battler")
        if initial is not None and not isinstance(initial, BattleAftermath):
            raise ValueError("initial battle history must be explicitly observed")
        self.battler = battler
        self.initial = initial
        self.identity = self._identity()
        self.receipts = ()
        self.outcomes = ()

    def _identity(self):
        b = self.battler
        return (
            b.output.resolve(),
            b.source_commit,
            b.root_lineage_id,
            b.source_state_sha256,
            b.model_sha256,
            b.qualification_sha256,
            b.source_partition,
            b.train_funding_diagnostic,
            b.train_story_contract,
            b.train_risk_story_scope,
            b.evaluation_story_scope,
            b.development_story_scope,
            b.development_preparation_scope,
            b.pp_depleted_switch_screen,
            b.mechanics_aware_tower_choices,
            b.diagnostic_tower_productive_stay,
        )

    def __call__(self):
        return self._completed_history(self.battler.calls)

    def checkpoint_after_budget_stop(self, *, terminal_state_sha256, error_type, error=None):
        """Authenticate a completed prefix plus ONE explicitly censored attempt.

        This is only a checkpoint/export API, not fresh battle inference. The
        normal provider still refuses an unfinished newest battle. No outcome
        is invented for the censored attempt; its actual final state and closed
        failure log must match the retained budget terminal.
        """
        if error_type not in {
            "ControllerWallTimeBudgetExhausted",
            "ControllerFrameBudgetExhausted",
            "ControllerActionBudgetExhausted",
        } and not (
            error_type == "ControllerFrameBudgetError"
            and error == "controller exhausted its hard frame budget"
        ):
            raise ValueError("checkpoint requires an explicit controller budget stop")
        return self._checkpoint_after_closed_failure(
            terminal_state_sha256=terminal_state_sha256, error_type=error_type
        )

    def checkpoint_after_execution_failure(self, *, terminal_state_sha256, error_type):
        """Export a failed or explicitly interrupted execution without a result.

        This does not admit the failed battle to normal strategy inference or
        convert it to a loss. A separate retained-state continuation is needed.
        """
        if error_type not in {
            "BattleRuntimeError",
            "BattleRuntimeTimeoutError",
            "ProtectedRecoveryError",
            "KeyboardInterrupt",
        }:
            raise ValueError("checkpoint requires an explicit battle execution failure")
        return self._checkpoint_after_closed_failure(
            terminal_state_sha256=terminal_state_sha256, error_type=error_type
        )

    def _checkpoint_after_closed_failure(self, *, terminal_state_sha256, error_type):
        b = self.battler
        if type(b.calls) is not int or b.calls < 1 or self._identity() != self.identity:
            raise ValueError("checkpoint battle identity or sequence changed")
        directory = b.output / f"battle-{b.calls:04d}"
        if not (directory / "initial.state").exists() and not (
            directory / "initial.state.json"
        ).exists():
            return self._checkpoint_before_capture(
                terminal_state_sha256=terminal_state_sha256, error_type=error_type,
            )
        capture = open_battle_scenario_capture(
            directory / "initial.state", directory / "initial.state.json"
        )
        m = capture.manifest
        endpoint = json.loads((directory / "endpoint.json").read_bytes())
        log = verify_trainer_practice_event_log(directory / "events")
        first = json.loads((directory / "events/event-00001.json").read_bytes())["payload"]
        last = json.loads(
            (directory / "events" / f"event-{log['event_count']:05d}.json").read_bytes()
        )["payload"]
        identity = first.get("identity", {})
        if (
            (directory / "outcome.json").exists()
            or (
                m.capture_id,
                m.root_lineage_id,
                m.source_commit,
                m.source_state_sha256,
                m.partition,
            )
            != (
                f"player-trainer-{b.calls:04d}",
                b.root_lineage_id,
                b.source_commit,
                b.source_state_sha256,
                b.source_partition,
            )
            or endpoint.get("final_state_sha256") != terminal_state_sha256
            or sha256((directory / "final.state").read_bytes()).hexdigest() != terminal_state_sha256
            or endpoint.get("model_sha256") != b.model_sha256
            or endpoint.get("qualification_sha256") != b.qualification_sha256
            or endpoint.get("outcome_sha256") is not None
            or endpoint.get("actor_returned_win") is not False
            or endpoint.get("outer_goal_verification_required") is not True
            or not log["complete"]
            or log["terminal_event"] != "run_failed"
            or last.get("error_type") != error_type
            or first.get("event") != "run_identity"
            or any(
                identity.get(k) != v
                for k, v in {
                    "model_sha256": b.model_sha256,
                    "qualification_sha256": b.qualification_sha256,
                    "source_commit": b.source_commit,
                    "root_lineage_id": b.root_lineage_id,
                    "parent_state_sha256": b.source_state_sha256,
                }.items()
            )
        ):
            raise ValueError("censored battle checkpoint differs from the actual failed terminal")
        latest = self._completed_history(b.calls - 1)
        receipt = dict(
            schema="pokemon.red.censored-battle-checkpoint.v1",
            ordinal=b.calls,
            manifest_sha256=capture.manifest_sha256,
            terminal_state_sha256=terminal_state_sha256,
            endpoint_sha256=canonical_sha256(endpoint),
            log=log,
            error_type=error_type,
            outcome=None,
            fresh_inference=False,
        )
        return latest, receipt

    def checkpoint_after_legacy_action_budget_stop(
        self, *, terminal_state_sha256, error_type, error,
    ):
        """Export the exact old action-limit defect without rewriting its log.

        This compatibility path is checkpoint-only and requires the closed
        pre-capture failure. Arbitrary RuntimeError or completed battles refuse.
        """
        if error_type != "RuntimeError" or error != "native lesson action budget exhausted":
            raise ValueError("legacy checkpoint requires the exact retained action-budget error")
        return self._checkpoint_before_capture(
            terminal_state_sha256=terminal_state_sha256, error_type=error_type,
        )

    def _checkpoint_before_capture(self, *, terminal_state_sha256, error_type):
        """Retain a closed entry failure with no model inference or invented outcome."""
        b = self.battler
        if type(b.calls) is not int or b.calls < 1 or self._identity() != self.identity:
            raise ValueError("pre-capture checkpoint identity or sequence changed")
        directory = b.output / f"battle-{b.calls:04d}"
        endpoint = json.loads((directory / "endpoint.json").read_bytes())
        log = verify_trainer_practice_event_log(directory / "events")
        first = json.loads((directory / "events/event-00001.json").read_bytes())["payload"]
        last = json.loads((directory / "events/event-00002.json").read_bytes())["payload"]
        identity = first.get("identity", {})
        diagnostic = last.get("battle_runtime_diagnostic") or {}
        if (
            any((directory / name).exists() for name in (
                "initial.state", "initial.state.json", "outcome.json",
            ))
            or endpoint.get("final_state_sha256") != terminal_state_sha256
            or sha256((directory / "final.state").read_bytes()).hexdigest() != terminal_state_sha256
            or endpoint.get("model_sha256") != b.model_sha256
            or endpoint.get("qualification_sha256") != b.qualification_sha256
            or endpoint.get("outcome_sha256") is not None
            or endpoint.get("actor_returned_win") is not False
            or endpoint.get("outer_goal_verification_required") is not True
            or not log["complete"] or log["terminal_event"] != "run_failed"
            or log["event_count"] != 2
            or any(log.get(key, 0) for key in ("started_decisions", "completed_decisions"))
            or first.get("event") != "run_identity"
            or last.get("error_type") != error_type
            or last.get("completed_events_before_failure") != 1
            or last.get("failure_after_event") != "run_identity"
            or diagnostic.get("phase") != "entry"
            or diagnostic.get("schema") != "pokemon.battle-runtime-diagnostic.v1"
            or diagnostic.get("recording_failures") != 0
            or diagnostic.get("selection") is not None
            or any(identity.get(k) != v for k, v in {
                "model_sha256": b.model_sha256,
                "qualification_sha256": b.qualification_sha256,
                "source_commit": b.source_commit,
                "root_lineage_id": b.root_lineage_id,
                "parent_state_sha256": b.source_state_sha256,
            }.items())
        ):
            raise ValueError("pre-capture checkpoint is not the closed no-inference entry failure")
        latest = self._completed_history(b.calls - 1)
        return latest, dict(
            schema="pokemon.red.censored-battle-checkpoint.v2", ordinal=b.calls,
            capture_stage="before_initial_capture", manifest_sha256=None,
            terminal_state_sha256=terminal_state_sha256,
            endpoint_sha256=canonical_sha256(endpoint), log=log,
            error_type=error_type, outcome=None, fresh_inference=False,
        )

    def _completed_history(self, completed_calls):
        b = self.battler
        if (
            self._identity() != self.identity
            or type(b.calls) is not int
            or b.calls < len(self.receipts)
            or type(completed_calls) is not int
            or not len(self.receipts) <= completed_calls <= b.calls
        ):
            raise ValueError("live battle identity or sequence changed")
        latest = self.initial
        receipts = []
        outcomes = []
        if set(b.output.glob("battle-*")) != {
            b.output / f"battle-{i:04d}" for i in range(1, b.calls + 1)
        }:
            raise ValueError("live battle artifact census differs")
        for ordinal in range(1, completed_calls + 1):
            directory = b.output / f"battle-{ordinal:04d}"
            capture = open_battle_scenario_capture(
                directory / "initial.state", directory / "initial.state.json"
            )
            m = capture.manifest
            if (m.capture_id, m.root_lineage_id, m.source_commit, m.source_state_sha256) != (
                f"player-trainer-{ordinal:04d}",
                b.root_lineage_id,
                b.source_commit,
                b.source_state_sha256,
            ) or m.partition is not b.source_partition:
                raise ValueError("live battle capture identity differs")
            payload = (directory / "outcome.json").read_bytes()
            episode = json.loads(payload)
            endpoint = json.loads((directory / "endpoint.json").read_bytes())
            if (
                episode.get("capture_id") != m.capture_id
                or episode.get("manifest_sha256") != capture.manifest_sha256
                or endpoint.get("model_sha256") != b.model_sha256
                or endpoint.get("qualification_sha256") != b.qualification_sha256
                or endpoint.get("outcome_sha256") != canonical_sha256(episode)
                or endpoint.get("final_state_sha256")
                != sha256((directory / "final.state").read_bytes()).hexdigest()
                or endpoint.get("actor_returned_win") is not episode.get("battle_won")
                or endpoint.get("outer_goal_verification_required") is not True
            ):
                raise ValueError("live battle outcome binding differs")
            log = verify_trainer_practice_event_log(directory / "events")
            first = json.loads((directory / "events" / "event-00001.json").read_bytes())
            identity = first["payload"].get("identity", {})
            expected = dict(
                model_sha256=b.model_sha256,
                qualification_sha256=b.qualification_sha256,
                source_commit=b.source_commit,
                root_lineage_id=b.root_lineage_id,
                parent_state_sha256=b.source_state_sha256,
            )
            if b.pp_depleted_switch_screen:
                # Use the same authenticated scope hook as execution. A declared
                # DEVELOPMENT League adapter may reuse K's PP screen; the base
                # battler still refuses that authority by default. History must
                # not misclassify a correctly recorded live League screen.
                screened = m.expected_battle_state == 2 and b.pp_reentry_screen_active(
                    identity.get("authority")
                )
                if identity.get("pp_depleted_switch_screen", False) is not screened:
                    raise ValueError("live battle PP screen scope differs")
                if screened:
                    expected.update(
                        pp_depleted_switch_screen=True,
                        source_partition="development",
                        fit_allowed=False,
                    )
            if b.source_partition is ScenarioPartition.TRAIN:
                expected.update(source_partition="train", fit_allowed=False)
            tower_mechanics = b.tower_mechanics_active(m.expected_map, identity.get("authority"))
            if identity.get("mechanics_aware_tower_choices", False) is not tower_mechanics:
                raise ValueError("live battle Tower mechanics scope differs")
            if tower_mechanics:
                expected.update(
                    mechanics_aware_tower_choices=True,
                    mechanics_aware_choices=True,
                    tower_mechanics_revision="damaging-only-v1",
                    source_partition="development",
                    fit_allowed=False,
                    allow_status_moves=False,
                )
            diagnostic_stay = tower_mechanics and b.diagnostic_tower_productive_stay
            if identity.get("diagnostic_tower_productive_stay", False) is not diagnostic_stay:
                raise ValueError("live battle Tower diagnostic control scope differs")
            if diagnostic_stay:
                expected.update(
                    diagnostic_tower_productive_stay=True, diagnostic_stay_when_productive=True
                )
            if b.development_story_scope is not None:
                b.story_limit()
                expected.update(
                    development_story_scope=b.development_story_scope.document(),
                    authority=b.story_authority(),
                    mechanics_aware_choices=True,
                    diagnostic_stay_when_productive=(
                        b.development_story_scope.diagnostic_stay_when_productive
                    ),
                    source_partition=b.source_partition.value,
                    fit_allowed=False,
                )
                if (
                    not b.development_story_scope.admits_map(m.expected_map)
                    or m.expected_battle_state != 2
                ):
                    raise ValueError("development history outside declared story scope")
            if b.development_preparation_scope is not None:
                expected.update(
                    development_preparation_scope=b.development_preparation_scope.document(),
                    authority=b.wild_authority(m.expected_map),
                    mechanics_aware_choices=True,
                    diagnostic_stay_when_productive=False,
                    allow_status_moves=True,
                    source_partition=b.source_partition.value,
                    fit_allowed=False,
                )
                if m.expected_battle_state != 1:
                    raise ValueError("development preparation history is not wild")
            if b.evaluation_story_scope is not None:
                scope = b.require_evaluation_story_scope()
                expected.update(
                    source_partition="development",
                    fit_allowed=False,
                    evaluation_story_scope=json.loads(
                        json.dumps(b.evaluation_story_scope.document())
                    ),
                    allow_status_moves=True,
                    allow_stranded_accuracy_move=True,
                    authority=story_battle_authority(b.model_sha256, b.qualification_sha256),
                )
                if m.expected_map != scope.map_id:
                    raise ValueError("evaluation history changed declared challenge")
            if (
                not log["complete"]
                or first["payload"].get("event") != "run_identity"
                or any(identity.get(key) != value for key, value in expected.items())
            ):
                raise ValueError("live battle event identity differs")
            kind = "wild" if m.expected_battle_state == 1 else "trainer"
            if b.source_partition is ScenarioPartition.TRAIN and kind == "trainer":
                if b.train_story_contract is not None:
                    scope = b.require_train_story_scope()
                    if (
                        canonical_sha256(identity.get("train_story_contract"))
                        != canonical_sha256(b._train_story_document())
                        or identity.get("train_funding_diagnostic", False) is not False
                        or identity.get("authority")
                        != (b.story_authority() if b.development_story_scope is not None else
                            story_battle_authority(b.model_sha256, b.qualification_sha256))
                        or m.expected_map != scope.map_id
                    ):
                        raise ValueError("TRAIN story history lacks its exact lesson scope")
                    if b.train_risk_story_scope is not None and (
                        identity.get("train_risk_story_scope")
                        != json.loads(json.dumps(b.train_risk_story_scope.document()))
                        or identity.get("allow_status_moves") is not True
                        or identity.get("allow_stranded_accuracy_move") is not True
                    ):
                        raise ValueError("TRAIN risk story history lacks its exact action scope")
                else:
                    b.require_funding_scope()
                    if identity.get("train_funding_diagnostic") is not True:
                        raise ValueError("TRAIN trainer history lacks its funding diagnostic scope")
            if identity.get("wild_training", False) is not (kind == "wild") or any(
                row["observation"]["features"]["battle"]["kind"] != kind
                for row in episode["decisions"]
            ):
                raise ValueError("live battle mode differs from capture")
            if log["terminal_event"] == "run_finished":
                last = json.loads(
                    (directory / "events" / f"event-{log['event_count']:05d}.json").read_bytes()
                )
                if last["payload"].get("outcome") != endpoint:
                    raise ValueError("live battle terminal differs")
            # A loss may have a run_failed terminal from the outer require-win
            # check. Its valid outcome remains a loss, never an erased attempt.
            receipt = canonical_sha256(
                dict(
                    manifest=capture.manifest_sha256,
                    endpoint=endpoint,
                    episode_sha256=sha256(payload).hexdigest(),
                    log=log,
                )
            )
            if ordinal <= len(self.receipts) and receipt != self.receipts[ordinal - 1]:
                raise ValueError("previously observed battle was modified")
            latest = red_battle_aftermath(payload, expected_sha256=sha256(payload).hexdigest())
            receipts.append(receipt)
            outcomes.append(latest)
        self.receipts = tuple(receipts)
        self.outcomes = tuple(outcomes)
        return latest
