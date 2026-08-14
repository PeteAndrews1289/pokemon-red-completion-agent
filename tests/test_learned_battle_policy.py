from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path

import numpy as np
import pytest

from pokemon_red_completion.battle_actions import (
    BattleAction,
    BattleActionKind,
    BattleBoostStat,
    BattleControlRequest,
    LearnedBattleControlRequest,
)
from pokemon_red_completion.battle_control_features import (
    CONTROL_CLASS_REFS,
    CONTROL_FEATURE_NAMES,
)
from pokemon_red_completion.battle_control_model import BattleControlMLP
from pokemon_red_completion.battle_model import MaskedLinearMoveRanker
from pokemon_red_completion.battle_neural_model import MaskedMLPMoveRanker
from pokemon_red_completion.battle_runtime import (
    BattleIntent,
    BattlePolicyObservation,
    BattleRecoveryCapability,
    BattleResourcePolicy,
    BattleSwitchCapability,
)
from pokemon_red_completion.battle_semantics import (
    FEATURE_NAMES,
    BattleFeatureBatch,
)
from pokemon_red_completion.battle_switch_target import SWITCH_TARGET_FEATURE_NAMES
from pokemon_red_completion.battle_switch_target_model import BattleSwitchTargetMLP
from pokemon_red_completion.learned_battle_policy import (
    LearnedBattlePolicyError,
    ModelAssistedBattlePolicy,
    load_battle_model_artifact,
)
from pokemon_red_completion.observation import RawGameState
from pokemon_red_completion.red_battle_catalog import (
    RED_BATTLE_CATALOG,
    pokemon_red_move_ref,
    pokemon_red_species_ref,
)
from pokemon_red_completion.red_training_dashboard import live_evaluation_state


def _model(*, power_weight: float = 10.0) -> MaskedLinearMoveRanker:
    weights = [0.0] * len(FEATURE_NAMES)
    weights[FEATURE_NAMES.index("move.power_fraction")] = power_weight
    return MaskedLinearMoveRanker(feature_names=FEATURE_NAMES, weights=weights)


def _batch() -> BattleFeatureBatch:
    first = [0.0] * len(FEATURE_NAMES)
    second = [0.0] * len(FEATURE_NAMES)
    second[FEATURE_NAMES.index("move.power_fraction")] = 1.0
    return BattleFeatureBatch(
        feature_names=FEATURE_NAMES,
        candidate_vectors=(tuple(first), tuple(second)),
        legal_mask=(True, True),
        current_pp=(10.0, 10.0),
        slot_indices=(0, 2),
    )


def _observation(
    *,
    recovery_capabilities: frozenset[BattleRecoveryCapability] = frozenset(),
    boost_capabilities: frozenset[BattleBoostStat] = frozenset(),
    boost_use_limits: tuple[tuple[BattleBoostStat, int], ...] = (),
    switch_capabilities: frozenset[BattleSwitchCapability] = frozenset(),
    switch_limit: int | None = None,
    required_boost_before_first_move: BattleBoostStat | None = None,
    require_status_clear_before_move: bool = False,
    minimum_hp_before_move: int | None = None,
    require_move_before_first_switch: bool = False,
    require_move_between_switches: bool = False,
    battler_status: int | None = None,
    battler_hp: int = 50,
    battler_max_hp: int = 100,
) -> BattlePolicyObservation:
    return BattlePolicyObservation(
        RawGameState(
            game_started=True,
            map_id=1,
            player_x=1,
            player_y=1,
            party_count=1,
            battle_state=2,
            first_party_moves=(33, 0, 55),
            first_party_pp=(10, 0, 10),
            first_party_hp=battler_hp,
            first_party_max_hp=battler_max_hp,
            first_party_status=battler_status,
        ),
        BattleIntent(
            "test_battle",
            "battle-test",
            resource_policy=(
                BattleResourcePolicy.BOUNDED_RECOVERY
                if recovery_capabilities
                else BattleResourcePolicy.NO_ADDITIONAL_CONSTRAINT
            ),
            recovery_capabilities=recovery_capabilities,
            boost_capabilities=boost_capabilities,
            boost_use_limits=boost_use_limits,
            switch_capabilities=switch_capabilities,
            switch_limit=switch_limit,
            required_boost_before_first_move=required_boost_before_first_move,
            minimum_hp_before_move=minimum_hp_before_move,
            require_status_clear_before_move=require_status_clear_before_move,
            require_move_before_first_switch=require_move_before_first_switch,
            require_move_between_switches=require_move_between_switches,
        ),
    )


class _Encoder:
    def snapshot_from_raw(self, raw: RawGameState) -> dict[str, object]:
        return {"battle_state": raw.battle_state}


class _RejectingEncoder:
    def snapshot_from_raw(self, raw: RawGameState) -> dict[str, object]:
        del raw
        raise ValueError("unsupported live observation")


class _ControlEncoder:
    class Snapshot:
        def to_dict(self) -> dict[str, object]:
            return {"schema": "semantic-snapshot-v1"}

    def snapshot_from_raw(self, raw: RawGameState) -> Snapshot:
        return self.Snapshot()


class _Projector:
    def project(
        self,
        snapshot: object,
        *,
        policy_context: object | None = None,
    ) -> BattleFeatureBatch:
        return _batch()


class _RejectingProjector:
    def project(
        self,
        snapshot: object,
        *,
        policy_context: object | None = None,
    ) -> BattleFeatureBatch:
        raise KeyError("missing semantic battle field")


class _TargetProjector(_Projector):
    catalog = RED_BATTLE_CATALOG


class _TargetEncoder:
    class Snapshot:
        def to_dict(self) -> dict[str, object]:
            def member(species_id: int, level: int, hp: int) -> dict[str, object]:
                return {
                    "species_ref": pokemon_red_species_ref(species_id),
                    "level": level,
                    "hp": hp,
                    "max_hp": 100,
                    "hp_ratio": hp / 100,
                    "status": None,
                    "moves": [
                        {
                            "slot_index": 0,
                            "move_ref": pokemon_red_move_ref(0x39),
                            "pp": 10,
                        }
                    ],
                }

            return {
                "schema_version": 1,
                "game_id": "pokemon-red",
                "mode": "battle",
                "location": "test",
                "facts": [],
                "features": {
                    "battle": {
                        "opponent_species_ref": pokemon_red_species_ref(0x78),
                        "opponent_level": 50,
                    },
                    "party": {
                        "count": 3,
                        "active_index": 0,
                        "members": [
                            member(0x1C, 60, 100),
                            member(0x68, 50, 20),
                            member(0x84, 50, 90),
                        ],
                    },
                },
            }

    def snapshot_from_raw(self, raw: RawGameState) -> Snapshot:
        return self.Snapshot()


def _switch_target_model() -> BattleSwitchTargetMLP:
    weights = np.zeros((len(SWITCH_TARGET_FEATURE_NAMES), 1))
    weights[0, 0] = 5.0
    return BattleSwitchTargetMLP(
        weights1=weights,
        bias1=np.zeros(1),
        weights2=np.ones(1),
        feature_mean=np.zeros(len(SWITCH_TARGET_FEATURE_NAMES)),
        feature_scale=np.ones(len(SWITCH_TARGET_FEATURE_NAMES)),
        training_seed=0,
    )


class _ShadowEncoder:
    class Snapshot:
        def __init__(self, status: str | None = None) -> None:
            self.status = status

        def to_dict(self) -> dict[str, object]:
            return {
                "schema_version": 1,
                "game_id": "pokemon-red",
                "mode": "battle",
                "location": "test",
                "facts": [],
                "features": {
                    "battle": {
                        "kind": "trainer",
                        "player_attack_stage": 0,
                        "player_special_stage": 0,
                        "player_accuracy_stage": 0,
                        "player_disabled_move_slot": None,
                        "opponent_level": 10,
                        "opponent_hp_ratio": 1.0,
                        "opponent_defense_stage": 0,
                        "opponent_using_trapping_move": False,
                    },
                    "party": {
                        "count": 2,
                        "active_index": 0,
                        "lead": {
                            "species_ref": "pokemon:test",
                            "level": 10,
                            "hp": 50,
                            "max_hp": 100,
                            "hp_ratio": 1.0,
                            "status": self.status,
                        },
                        "members": [
                            {
                                "species_ref": "pokemon:test",
                                "level": 10,
                                "hp": 50,
                                "max_hp": 100,
                                "hp_ratio": 1.0,
                                "status": self.status,
                            },
                            {
                                "species_ref": "pokemon:reserve",
                                "level": 12,
                                "hp": 80,
                                "max_hp": 100,
                                "hp_ratio": 0.8,
                                "status": None,
                            },
                        ],
                    },
                    "resources": {
                        "capture_item_count": 0,
                        "healing_item_count": 1,
                        "status_recovery_item_count": int(self.status is not None),
                        "revive_item_count": 0,
                        "accuracy_boost_count": 1,
                        "attack_boost_count": 1,
                        "special_boost_count": 1,
                    },
                    "progress": {"badge_count": 0},
                },
            }

    def snapshot_from_raw(self, raw: RawGameState) -> Snapshot:
        status = {0x40: "paralysis"}.get(raw.battler_status or 0)
        return self.Snapshot(status)


def _control_model(class_index: int = 1) -> BattleControlMLP:
    output_bias = [0.0, 0.0]
    output_bias[class_index] = 5.0
    return BattleControlMLP(
        feature_names=CONTROL_FEATURE_NAMES,
        class_refs=CONTROL_CLASS_REFS[:2],
        input_weights=[[0.0] * len(CONTROL_FEATURE_NAMES)] * 2,
        hidden_bias=[0.0, 0.0],
        output_weights=[[0.0, 0.0], [0.0, 0.0]],
        output_bias=output_bias,
    )


def _full_control_model(class_index: int) -> BattleControlMLP:
    output_bias = [0.0] * len(CONTROL_CLASS_REFS)
    output_bias[class_index] = 5.0
    return BattleControlMLP(
        feature_names=CONTROL_FEATURE_NAMES,
        class_refs=CONTROL_CLASS_REFS,
        input_weights=[[0.0] * len(CONTROL_FEATURE_NAMES)] * 2,
        hidden_bias=[0.0, 0.0],
        output_weights=[[0.0] * len(CONTROL_CLASS_REFS)] * 2,
        output_bias=output_bias,
    )


def test_model_assisted_policy_uses_confident_prediction_and_counts_coverage() -> None:
    policy = ModelAssistedBattlePolicy(
        model=_model(),
        encoder=_Encoder(),  # type: ignore[arg-type]
        projector=_Projector(),  # type: ignore[arg-type]
        confidence_threshold=0.9,
    )

    assert policy.choose_move(_observation(), lambda: 3) == 3
    assert policy.public_dict()["model_coverage"] == 1.0
    assert policy.teacher_fallbacks == 0
    assert policy.teacher_queries == 1


def test_model_assisted_policy_publishes_post_decision_progress_without_authority() -> None:
    updates: list[Mapping[str, object]] = []
    policy = ModelAssistedBattlePolicy(
        model=_model(),
        encoder=_Encoder(),  # type: ignore[arg-type]
        projector=_Projector(),  # type: ignore[arg-type]
        confidence_threshold=0.9,
        progress_sink=updates.append,
    )

    assert policy.choose_move(_observation(), lambda: 3) == 3
    assert len(updates) == 1
    assert updates[0]["decisions"] == 1
    assert updates[0]["teacher_queries"] == 1
    assert updates[0]["model_decisions"] == 1


def test_model_assisted_policy_ignores_progress_observer_failure() -> None:
    def broken_observer(update: Mapping[str, object]) -> None:
        del update
        raise RuntimeError("observer unavailable")

    policy = ModelAssistedBattlePolicy(
        model=_model(),
        encoder=_Encoder(),  # type: ignore[arg-type]
        projector=_Projector(),  # type: ignore[arg-type]
        confidence_threshold=0.9,
        progress_sink=broken_observer,
    )

    assert policy.choose_move(_observation(), lambda: 3) == 3
    assert policy.progress_sink_errors == 1


def test_model_assisted_policy_executes_and_counts_teacher_correction() -> None:
    policy = ModelAssistedBattlePolicy(
        model=_model(),
        encoder=_Encoder(),  # type: ignore[arg-type]
        projector=_Projector(),  # type: ignore[arg-type]
        confidence_threshold=0.9,
    )

    assert policy.choose_move(_observation(), lambda: 1) == 1
    assert policy.model_decisions == 0
    assert policy.teacher_fallbacks == 1
    assert policy.teacher_queries == 1
    assert policy.fallback_reasons == {"teacher_disagreement": 1}


def test_model_assisted_policy_defers_low_confidence_state_to_teacher() -> None:
    policy = ModelAssistedBattlePolicy(
        model=_model(power_weight=0.0),
        encoder=_Encoder(),  # type: ignore[arg-type]
        projector=_Projector(),  # type: ignore[arg-type]
        confidence_threshold=0.75,
    )

    assert policy.choose_move(_observation(), lambda: 1) == 1
    assert policy.model_decisions == 0
    assert policy.teacher_fallbacks == 1
    assert policy.teacher_queries == 1
    assert policy.fallback_reasons == {"low_confidence": 1}


def test_model_assisted_policy_emits_private_training_record_for_disagreement() -> None:
    records: list[dict[str, object]] = []
    policy = ModelAssistedBattlePolicy(
        model=_model(),
        encoder=_Encoder(),  # type: ignore[arg-type]
        projector=_Projector(),  # type: ignore[arg-type]
        confidence_threshold=0.9,
        correction_sink=lambda record: records.append(dict(record)),
    )

    assert policy.choose_move(_observation(), lambda: 1) == 1
    assert policy.correction_records == 1
    assert len(records) == 1
    record = records[0]
    assert record["reason"] == "teacher_disagreement"
    assert record["battle_plan_id"] == "battle-test"
    assert record["model"] == {
        "predicted_candidate_index": 1,
        "confidence": pytest.approx(0.9999546021312976),
    }
    assert record["teacher"] == {"chosen_candidate_index": 0}
    features = record["features"]
    assert isinstance(features, dict)
    assert features["slot_indices"] == [0, 2]
    assert len(features["candidate_vectors"]) == 2
    assert policy.public_dict()["correction_records"] == 1


def test_model_assisted_policy_records_low_confidence_teacher_label() -> None:
    records: list[dict[str, object]] = []
    policy = ModelAssistedBattlePolicy(
        model=_model(power_weight=0.0),
        encoder=_Encoder(),  # type: ignore[arg-type]
        projector=_Projector(),  # type: ignore[arg-type]
        confidence_threshold=0.75,
        correction_sink=lambda record: records.append(dict(record)),
    )

    assert policy.choose_move(_observation(), lambda: 1) == 1
    assert records[0]["reason"] == "low_confidence"
    assert records[0]["teacher"] == {"chosen_candidate_index": 0}


def test_shadow_teacher_records_disagreement_but_model_still_acts() -> None:
    records: list[dict[str, object]] = []
    policy = ModelAssistedBattlePolicy(
        model=_model(),
        encoder=_Encoder(),  # type: ignore[arg-type]
        projector=_Projector(),  # type: ignore[arg-type]
        confidence_threshold=0.0,
        require_teacher_agreement=False,
        observe_teacher_when_not_required=True,
        correction_sink=lambda record: records.append(dict(record)),
    )

    assert policy.choose_move(_observation(), lambda: 1) == 3
    assert policy.model_decisions == 1
    assert policy.teacher_fallbacks == 0
    assert policy.teacher_queries == 1
    assert policy.shadow_teacher_disagreements == 1
    assert records[0]["teacher"] == {"chosen_candidate_index": 0}


def test_teacher_free_policy_executes_confident_move_without_querying_teacher() -> None:
    policy = ModelAssistedBattlePolicy(
        model=_model(),
        encoder=_Encoder(),  # type: ignore[arg-type]
        projector=_Projector(),  # type: ignore[arg-type]
        confidence_threshold=0.9,
        require_teacher_agreement=False,
        allow_teacher_queries=False,
    )

    def teacher_must_not_run() -> int:
        raise AssertionError("teacher was queried")

    assert policy.choose_move(_observation(), teacher_must_not_run) == 3
    assert policy.teacher_queries == 0
    assert policy.public_dict()["teacher_queries_allowed"] is False


def test_teacher_free_policy_fails_instead_of_using_low_confidence_fallback() -> None:
    policy = ModelAssistedBattlePolicy(
        model=_model(power_weight=0.0),
        encoder=_Encoder(),  # type: ignore[arg-type]
        projector=_Projector(),  # type: ignore[arg-type]
        confidence_threshold=0.75,
        require_teacher_agreement=False,
        allow_teacher_queries=False,
    )

    with pytest.raises(LearnedBattlePolicyError, match="forbids teacher queries"):
        policy.choose_move(_observation(), lambda: 1)
    assert policy.teacher_queries == 0


def test_teacher_free_policy_preserves_unsupported_observation_cause() -> None:
    policy = ModelAssistedBattlePolicy(
        model=_model(),
        encoder=_Encoder(),  # type: ignore[arg-type]
        projector=_RejectingProjector(),  # type: ignore[arg-type]
        confidence_threshold=0.0,
        require_teacher_agreement=False,
        allow_teacher_queries=False,
    )

    with pytest.raises(LearnedBattlePolicyError, match="unsupported live observation") as raised:
        policy.choose_move(_observation(), lambda: 1)

    assert isinstance(raised.value.__cause__, KeyError)
    assert policy.teacher_queries == 0
    assert policy.teacher_fallbacks == 0
    assert policy.unsupported_observation_errors == {"KeyError": 1}
    assert policy.failed_decisions == 1
    assert policy.interrupted_decisions == 0
    assert policy.public_dict()["decision_accounting_complete"] is True
    assert policy.public_dict()["unsupported_observation_errors"] == {"KeyError": 1}
    assert policy.public_dict()["last_unsupported_observation"] == {
        "active_party_hp": None,
        "active_party_index": None,
        "active_party_level": None,
        "active_party_max_hp": None,
        "active_party_moves": [],
        "active_party_pp": [],
        "active_party_species_id": None,
        "battle_plan_id": "battle-test",
        "battle_state": 2,
        "disabled_move_slot": None,
        "enemy_hp": None,
        "enemy_species_id": None,
        "objective_id": "test_battle",
        "required_move_policy": "any_usable",
        "required_move_ref": None,
    }


def test_interrupted_decision_is_counted_before_propagation() -> None:
    policy = ModelAssistedBattlePolicy(
        model=_model(),
        encoder=_Encoder(),  # type: ignore[arg-type]
        projector=_Projector(),  # type: ignore[arg-type]
        confidence_threshold=0.0,
        require_teacher_agreement=True,
    )

    def interrupt_teacher() -> int:
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        policy.choose_move(_observation(), interrupt_teacher)

    report = policy.public_dict()
    assert report["interrupted_decisions"] == 1
    assert report["accounted_decisions"] == 1
    assert report["decision_accounting_complete"] is True


def test_teacher_control_request_during_fallback_is_not_counted_as_returned_move() -> None:
    policy = ModelAssistedBattlePolicy(
        model=_model(),
        encoder=_Encoder(),  # type: ignore[arg-type]
        projector=_RejectingProjector(),  # type: ignore[arg-type]
        confidence_threshold=0.0,
        require_teacher_agreement=True,
    )

    def request_recovery() -> int:
        raise BattleControlRequest(BattleAction.recovery())

    with pytest.raises(BattleControlRequest):
        policy.choose_move(_observation(), request_recovery)

    report = policy.public_dict()
    assert report["returned_move_decisions"] == 0
    assert report["non_move_control_decisions"] == 1
    assert report["teacher_queries"] == 1
    assert report["teacher_fallbacks"] == 0
    assert report["fallback_reasons"] == {}
    assert report["returned_move_accounting_gap"] == 0
    assert report["decision_accounting_complete"] is True
    assert live_evaluation_state(report, None).public_dict()["decision_accounting_complete"] is True


def test_failed_control_record_does_not_count_a_returned_teacher_move() -> None:
    projected: list[dict[str, object]] = []

    def validate_progress(report: Mapping[str, object]) -> None:
        projected.append(live_evaluation_state(report, None).public_dict())

    policy = ModelAssistedBattlePolicy(
        model=_model(),
        encoder=_RejectingEncoder(),  # type: ignore[arg-type]
        projector=_Projector(),  # type: ignore[arg-type]
        confidence_threshold=0.0,
        require_teacher_agreement=True,
        control_sink=lambda record: None,
        progress_sink=validate_progress,
    )

    with pytest.raises(ValueError, match="unsupported live observation"):
        policy.choose_move(_observation(), lambda: 1)

    report = policy.public_dict()
    assert report["returned_move_decisions"] == 0
    assert report["failed_decisions"] == 1
    assert report["teacher_fallbacks"] == 0
    assert report["returned_move_accounting_gap"] == 0
    assert report["decision_accounting_complete"] is True
    assert policy.progress_sink_errors == 0
    assert projected[0]["decision_accounting_complete"] is True


def test_failed_control_sink_does_not_commit_label_counters_or_history() -> None:
    def reject_label(record: Mapping[str, object]) -> None:
        del record
        raise RuntimeError("control label unavailable")

    encoder = _ShadowEncoder()
    policy = ModelAssistedBattlePolicy(
        model=_model(),
        control_model=_control_model(0),
        encoder=encoder,  # type: ignore[arg-type]
        projector=_Projector(),  # type: ignore[arg-type]
        confidence_threshold=0.0,
        require_teacher_agreement=False,
        control_sink=reject_label,
    )
    observation = _observation()

    with pytest.raises(RuntimeError, match="control label unavailable"):
        policy.choose_move(observation, lambda: 1)

    report = policy.public_dict()
    assert report["control_records"] == 0
    assert report["typed_non_move_control_records"] == 0
    assert report["control_signals"] == {}
    assert report["model_decisions"] == 0
    assert report["failed_decisions"] == 1
    assert report["returned_move_accounting_gap"] == 0
    snapshot = encoder.snapshot_from_raw(observation.state).to_dict()
    history = policy.control_history.before("battle-test", snapshot)
    assert history.action_counts == (0,) * len(CONTROL_CLASS_REFS)


def test_policy_complete_flag_requires_returned_move_source_accounting() -> None:
    policy = ModelAssistedBattlePolicy(
        model=_model(),
        encoder=_Encoder(),  # type: ignore[arg-type]
        projector=_Projector(),  # type: ignore[arg-type]
        confidence_threshold=0.0,
    )
    policy.decisions = 1
    policy.returned_move_decisions = 1

    report = policy.public_dict()

    assert report["accounted_decisions"] == 1
    assert report["returned_move_accounting_gap"] == 1
    assert report["decision_accounting_complete"] is False


def test_shadow_teacher_preserves_non_move_control_signal() -> None:
    policy = ModelAssistedBattlePolicy(
        model=_model(),
        encoder=_Encoder(),  # type: ignore[arg-type]
        projector=_Projector(),  # type: ignore[arg-type]
        confidence_threshold=0.0,
        require_teacher_agreement=False,
        observe_teacher_when_not_required=True,
    )

    def request_recovery() -> int:
        raise RuntimeError("use recovery command")

    with pytest.raises(RuntimeError, match="recovery"):
        policy.choose_move(_observation(), request_recovery)
    assert policy.shadow_teacher_unavailable == 1
    assert policy.model_decisions == 0


def test_shadow_teacher_records_typed_control_signal() -> None:
    records: list[dict[str, object]] = []
    policy = ModelAssistedBattlePolicy(
        model=_model(),
        encoder=_ControlEncoder(),  # type: ignore[arg-type]
        projector=_Projector(),  # type: ignore[arg-type]
        confidence_threshold=0.0,
        require_teacher_agreement=False,
        observe_teacher_when_not_required=True,
        control_sink=lambda record: records.append(dict(record)),
    )

    def request_recovery() -> int:
        raise BattleControlRequest(BattleAction.recovery())

    with pytest.raises(BattleControlRequest):
        policy.choose_move(_observation(), request_recovery)

    assert policy.control_records == 1
    assert policy.typed_non_move_control_records == 1
    assert policy.non_move_control_decisions == 1
    assert policy.returned_move_decisions == 0
    assert policy.public_dict()["accounted_decisions"] == 1
    assert policy.public_dict()["returned_move_accounting_gap"] == 0
    assert policy.control_signals == {"pokemon.core:battle:recovery": 1}
    assert records[0]["teacher_action"] == BattleAction.recovery().public_dict()


def test_control_sink_binds_targetless_teacher_switch_to_observed_reserve() -> None:
    records: list[dict[str, object]] = []
    policy = ModelAssistedBattlePolicy(
        model=_model(),
        encoder=_ShadowEncoder(),  # type: ignore[arg-type]
        projector=_Projector(),  # type: ignore[arg-type]
        confidence_threshold=0.0,
        require_teacher_agreement=False,
        observe_teacher_when_not_required=True,
        control_sink=lambda record: records.append(dict(record)),
    )

    def request_switch() -> int:
        raise BattleControlRequest(BattleAction.switch())

    with pytest.raises(BattleControlRequest):
        policy.choose_move(_observation(), request_switch)

    assert policy.control_signals == {"pokemon.core:battle:switch:2": 1}
    assert records[0]["teacher_action"] == BattleAction.switch(2).public_dict()


def test_switch_target_model_shadows_teacher_without_changing_its_request() -> None:
    policy = ModelAssistedBattlePolicy(
        model=_model(),
        encoder=_TargetEncoder(),  # type: ignore[arg-type]
        projector=_TargetProjector(),  # type: ignore[arg-type]
        confidence_threshold=0.0,
        switch_target_model=_switch_target_model(),
    )

    teacher_request = BattleControlRequest(BattleAction.switch(2))
    with pytest.raises(BattleControlRequest) as raised:
        policy.choose_move(
            _observation(),
            lambda: (_ for _ in ()).throw(teacher_request),
        )

    assert raised.value is teacher_request
    target = policy.public_dict()["switch_target_model"]
    assert isinstance(target, dict)
    assert target["shadow"] == {
        "decisions": 1,
        "agreements": 0,
        "accuracy": 0.0,
        "mean_confidence": pytest.approx(0.5592599275355958),
        "unavailable": {},
    }
    assert target["execution"] == {
        "enabled": False,
        "decisions": 0,
        "rebindings": 0,
        "fallbacks": {},
    }


def test_switch_target_execution_rebinds_only_teacher_switch_target() -> None:
    policy = ModelAssistedBattlePolicy(
        model=_model(),
        encoder=_TargetEncoder(),  # type: ignore[arg-type]
        projector=_TargetProjector(),  # type: ignore[arg-type]
        confidence_threshold=0.0,
        switch_target_model=_switch_target_model(),
        execute_switch_target_model=True,
    )

    with pytest.raises(LearnedBattleControlRequest) as raised:
        policy.choose_move(
            _observation(),
            lambda: (_ for _ in ()).throw(BattleControlRequest(BattleAction.switch(2))),
        )

    assert raised.value.action == BattleAction.switch()
    assert raised.value.party_slot == 3
    target = policy.public_dict()["switch_target_model"]
    assert isinstance(target, dict)
    assert target["execution"] == {
        "enabled": True,
        "decisions": 1,
        "rebindings": 1,
        "fallbacks": {},
    }


def test_control_sink_records_normal_model_move() -> None:
    records: list[dict[str, object]] = []
    policy = ModelAssistedBattlePolicy(
        model=_model(),
        encoder=_ControlEncoder(),  # type: ignore[arg-type]
        projector=_Projector(),  # type: ignore[arg-type]
        confidence_threshold=0.0,
        require_teacher_agreement=False,
        observe_teacher_when_not_required=True,
        control_sink=lambda record: records.append(dict(record)),
    )

    chosen = policy.choose_move(_observation(), lambda: 1)

    assert 1 <= chosen <= 4
    assert policy.control_records == 1
    assert policy.typed_non_move_control_records == 0
    assert policy.returned_move_decisions == 1
    assert policy.non_move_control_decisions == 0
    assert policy.failed_decisions == 0
    assert policy.interrupted_decisions == 0
    assert policy.public_dict()["decision_accounting_complete"] is True
    assert policy.control_signals == {f"pokemon.core:battle:move:{chosen}": 1}
    assert records[0]["teacher_action"] == BattleAction.move(chosen).public_dict()


def test_control_model_scores_live_actions_without_executing_them() -> None:
    policy = ModelAssistedBattlePolicy(
        model=_model(),
        control_model=_control_model(),
        encoder=_ShadowEncoder(),  # type: ignore[arg-type]
        projector=_Projector(),  # type: ignore[arg-type]
        confidence_threshold=0.0,
        require_teacher_agreement=False,
        observe_teacher_when_not_required=True,
    )

    assert policy.choose_move(_observation(), lambda: 1) == 3
    with pytest.raises(BattleControlRequest):
        policy.choose_move(
            _observation(),
            lambda: (_ for _ in ()).throw(BattleControlRequest(BattleAction.recovery())),
        )

    shadow = policy.public_dict()["control_model_shadow"]
    assert isinstance(shadow, dict)
    assert shadow["decisions"] == 2
    assert shadow["agreements"] == 1
    assert shadow["accuracy"] == 0.5
    assert shadow["unavailable"] == {}
    assert shadow["confusion"] == {
        "pokemon.core:battle:recovery -> pokemon.core:battle:recovery": 1,
        "pokemon.core:battle:select_move -> pokemon.core:battle:recovery": 1,
    }


def test_control_shadow_records_typed_request_while_move_model_is_teacher_gated() -> None:
    policy = ModelAssistedBattlePolicy(
        model=_model(),
        control_model=_control_model(),
        encoder=_ShadowEncoder(),  # type: ignore[arg-type]
        projector=_Projector(),  # type: ignore[arg-type]
        confidence_threshold=0.0,
        require_teacher_agreement=True,
    )

    with pytest.raises(BattleControlRequest):
        policy.choose_move(
            _observation(),
            lambda: (_ for _ in ()).throw(BattleControlRequest(BattleAction.recovery())),
        )

    shadow = policy.public_dict()["control_model_shadow"]
    assert isinstance(shadow, dict)
    assert shadow["decisions"] == 1
    assert shadow["agreements"] == 1
    assert shadow["confusion"] == {
        "pokemon.core:battle:recovery -> pokemon.core:battle:recovery": 1,
    }
    assert policy.teacher_queries == 1


def test_control_execution_emits_recovery_without_calling_teacher() -> None:
    policy = ModelAssistedBattlePolicy(
        model=_model(),
        control_model=_control_model(),
        execute_control_model=True,
        encoder=_ShadowEncoder(),  # type: ignore[arg-type]
        projector=_Projector(),  # type: ignore[arg-type]
        confidence_threshold=0.0,
        require_teacher_agreement=False,
    )

    def teacher_must_not_run() -> int:
        raise AssertionError("authorized recovery queried the teacher")

    with pytest.raises(LearnedBattleControlRequest) as raised:
        policy.choose_move(
            _observation(recovery_capabilities=frozenset({BattleRecoveryCapability.RESTORE_HP})),
            teacher_must_not_run,
        )

    assert raised.value.party_slot == 1
    assert raised.value.recovery_need == "hp"

    execution = policy.public_dict()["control_model_execution"]
    assert isinstance(execution, dict)
    assert execution["decisions"] == 1
    assert execution["typed_requests_executed"] == 1
    assert execution["safety_fallbacks"] == 0


def test_control_execution_can_suppress_a_teacher_recovery() -> None:
    policy = ModelAssistedBattlePolicy(
        model=_model(),
        control_model=_control_model(0),
        execute_control_model=True,
        encoder=_ShadowEncoder(),  # type: ignore[arg-type]
        projector=_Projector(),  # type: ignore[arg-type]
        confidence_threshold=0.0,
        require_teacher_agreement=False,
    )

    chosen = policy.choose_move(
        _observation(),
        lambda: (_ for _ in ()).throw(BattleControlRequest(BattleAction.recovery())),
    )

    assert chosen == 3
    execution = policy.public_dict()["control_model_execution"]
    assert isinstance(execution, dict)
    assert execution["teacher_requests_suppressed"] == 1


def test_control_low_confidence_teacher_move_has_one_return_source() -> None:
    policy = ModelAssistedBattlePolicy(
        model=_model(),
        control_model=_control_model(0),
        execute_control_model=True,
        control_confidence_threshold=1.0,
        encoder=_ShadowEncoder(),  # type: ignore[arg-type]
        projector=_Projector(),  # type: ignore[arg-type]
        confidence_threshold=0.0,
        require_teacher_agreement=False,
    )

    assert policy.choose_move(_observation(), lambda: 1) == 1
    report = policy.public_dict()
    assert report["returned_move_decisions"] == 1
    assert report["teacher_fallbacks"] == 1
    assert report["model_decisions"] == 0
    assert report["fallback_reasons"] == {"control_low_confidence": 1}
    assert report["returned_move_accounting_gap"] == 0
    assert report["decision_accounting_complete"] is True
    assert live_evaluation_state(report, None).public_dict()["decision_accounting_complete"] is True


def test_control_execution_preserves_move_teacher_gate() -> None:
    policy = ModelAssistedBattlePolicy(
        model=_model(),
        control_model=_control_model(0),
        execute_control_model=True,
        encoder=_ShadowEncoder(),  # type: ignore[arg-type]
        projector=_Projector(),  # type: ignore[arg-type]
        confidence_threshold=0.0,
        require_teacher_agreement=True,
    )

    assert policy.choose_move(_observation(), lambda: 1) == 1
    assert policy.teacher_queries == 1
    assert policy.teacher_fallbacks == 1
    assert policy.fallback_reasons == {"teacher_disagreement": 1}
    assert policy.model_decisions == 0
    execution = policy.public_dict()["control_model_execution"]
    assert isinstance(execution, dict)
    assert execution["decisions"] == 1


def test_teacher_free_control_move_does_not_query_teacher() -> None:
    policy = ModelAssistedBattlePolicy(
        model=_model(),
        control_model=_control_model(0),
        execute_control_model=True,
        encoder=_ShadowEncoder(),  # type: ignore[arg-type]
        projector=_Projector(),  # type: ignore[arg-type]
        confidence_threshold=0.0,
        require_teacher_agreement=False,
        allow_teacher_queries=False,
    )

    def teacher_must_not_run() -> int:
        raise AssertionError("teacher was queried")

    assert policy.choose_move(_observation(), teacher_must_not_run) == 3
    assert policy.teacher_queries == 0
    assert policy.public_dict()["actor"] == "learned_policy_teacher_free"


def test_control_execution_masks_an_unparameterized_special_action() -> None:
    policy = ModelAssistedBattlePolicy(
        model=_model(),
        control_model=_control_model(),
        execute_control_model=True,
        encoder=_ShadowEncoder(),  # type: ignore[arg-type]
        projector=_Projector(),  # type: ignore[arg-type]
        confidence_threshold=0.0,
        require_teacher_agreement=False,
    )

    assert policy.choose_move(_observation(), lambda: 1) == 3
    execution = policy.public_dict()["control_model_execution"]
    assert isinstance(execution, dict)
    assert execution["safety_fallbacks"] == 0
    assert execution["affordance_masked_decisions"] == 1
    assert execution["affordance_masks"] == {"capability_or_target_mask": 1}
    assert execution["target_resolution_failures"] == {}


def test_control_affordance_mask_preserves_move_teacher_gate() -> None:
    policy = ModelAssistedBattlePolicy(
        model=_model(),
        control_model=_control_model(),
        execute_control_model=True,
        encoder=_ShadowEncoder(),  # type: ignore[arg-type]
        projector=_Projector(),  # type: ignore[arg-type]
        confidence_threshold=0.0,
        require_teacher_agreement=True,
    )

    assert policy.choose_move(_observation(), lambda: 1) == 1
    assert policy.teacher_queries == 1
    assert policy.teacher_fallbacks == 1
    assert policy.fallback_reasons == {"teacher_disagreement": 1}
    assert policy.model_decisions == 0
    execution = policy.public_dict()["control_model_execution"]
    assert isinstance(execution, dict)
    assert execution["safety_fallbacks"] == 0
    assert execution["affordance_masked_decisions"] == 1
    assert execution["affordance_masks"] == {"capability_or_target_mask": 1}
    assert execution["target_resolution_failures"] == {}


def test_control_execution_emits_boost_without_calling_teacher() -> None:
    policy = ModelAssistedBattlePolicy(
        model=_model(),
        control_model=_full_control_model(4),
        execute_control_model=True,
        encoder=_ShadowEncoder(),  # type: ignore[arg-type]
        projector=_Projector(),  # type: ignore[arg-type]
        confidence_threshold=0.0,
        require_teacher_agreement=False,
    )

    def teacher_must_not_run() -> int:
        raise AssertionError("high-confidence boost queried the teacher")

    with pytest.raises(LearnedBattleControlRequest) as raised:
        policy.choose_move(
            _observation(boost_capabilities=frozenset({BattleBoostStat.SPECIAL})),
            teacher_must_not_run,
        )

    assert raised.value.action == BattleAction.boost(BattleBoostStat.SPECIAL)
    execution = policy.public_dict()["control_model_execution"]
    assert isinstance(execution, dict)
    assert execution["teacher_free_requests"] == 1
    assert execution["typed_requests_executed"] == 1


def test_control_execution_masks_boost_without_bound_executor_capability() -> None:
    policy = ModelAssistedBattlePolicy(
        model=_model(),
        control_model=_full_control_model(2),
        execute_control_model=True,
        encoder=_ShadowEncoder(),  # type: ignore[arg-type]
        projector=_Projector(),  # type: ignore[arg-type]
        confidence_threshold=0.0,
        require_teacher_agreement=False,
    )

    assert policy.choose_move(_observation(), lambda: 1) == 3
    execution = policy.public_dict()["control_model_execution"]
    assert isinstance(execution, dict)
    assert execution["safety_fallbacks"] == 0
    assert execution["affordance_masked_decisions"] == 1
    assert execution["affordance_masks"] == {"capability_or_target_mask": 1}
    assert execution["target_resolution_failures"] == {}
    assert execution["typed_requests_executed"] == 0


def test_control_execution_masks_boost_after_intent_budget_is_consumed() -> None:
    policy = ModelAssistedBattlePolicy(
        model=_model(),
        control_model=_full_control_model(2),
        execute_control_model=True,
        encoder=_ShadowEncoder(),  # type: ignore[arg-type]
        projector=_Projector(),  # type: ignore[arg-type]
        confidence_threshold=0.0,
        require_teacher_agreement=False,
    )
    observation = _observation(
        boost_capabilities=frozenset({BattleBoostStat.ACCURACY}),
        boost_use_limits=((BattleBoostStat.ACCURACY, 1),),
    )

    with pytest.raises(LearnedBattleControlRequest):
        policy.choose_move(observation, lambda: 1)
    assert policy.choose_move(observation, lambda: 1) == 3

    execution = policy.public_dict()["control_model_execution"]
    assert isinstance(execution, dict)
    assert execution["typed_requests_executed"] == 1
    assert execution["safety_fallbacks"] == 0
    assert execution["affordance_masked_decisions"] == 1
    assert execution["affordance_masks"] == {"budget_mask": 1}
    assert execution["target_resolution_failures"] == {}
    assert execution["last_intent_mask"] == {
        "reason": "budget_mask",
        "predicted_action": "pokemon.core:battle:boost:accuracy",
        "battle_plan_id": "battle-test",
        "objective_id": "test_battle",
        "history": {
            "battle_turn": 1,
            "opponent_index": 0,
            "opponent_turn": 1,
            "previous_action": "pokemon.core:battle:boost:accuracy",
            "action_counts": {
                class_ref: int(class_ref == "pokemon.core:battle:boost:accuracy")
                for class_ref in CONTROL_CLASS_REFS
            },
            "move_count_at_last_switch": 0,
        },
        "active": {
            "party_index": None,
            "species_id": None,
            "level": None,
            "hp": None,
            "max_hp": None,
            "status": None,
        },
        "opponent": {
            "species_id": None,
            "level": None,
            "hp": None,
            "max_hp": None,
        },
    }


def test_control_execution_emits_switch_without_calling_teacher() -> None:
    policy = ModelAssistedBattlePolicy(
        model=_model(),
        control_model=_full_control_model(5),
        execute_control_model=True,
        encoder=_ShadowEncoder(),  # type: ignore[arg-type]
        projector=_Projector(),  # type: ignore[arg-type]
        confidence_threshold=0.0,
        require_teacher_agreement=False,
    )

    def teacher_must_not_run() -> int:
        raise AssertionError("authorized switch queried the teacher")

    with pytest.raises(LearnedBattleControlRequest) as raised:
        policy.choose_move(
            _observation(switch_capabilities=frozenset({BattleSwitchCapability.DIRECT})),
            teacher_must_not_run,
        )

    assert raised.value.action.kind.value == "switch"
    assert raised.value.party_slot == 2
    execution = policy.public_dict()["control_model_execution"]
    assert isinstance(execution, dict)
    assert execution["teacher_free_requests"] == 1
    assert execution["typed_requests_executed"] == 1


def test_control_execution_masks_switch_after_intent_budget_is_consumed() -> None:
    policy = ModelAssistedBattlePolicy(
        model=_model(),
        control_model=_full_control_model(5),
        execute_control_model=True,
        encoder=_ShadowEncoder(),  # type: ignore[arg-type]
        projector=_Projector(),  # type: ignore[arg-type]
        confidence_threshold=0.0,
        require_teacher_agreement=False,
    )
    observation = _observation(
        switch_capabilities=frozenset({BattleSwitchCapability.DIRECT}),
        switch_limit=1,
    )

    with pytest.raises(LearnedBattleControlRequest):
        policy.choose_move(observation, lambda: 1)
    assert policy.choose_move(observation, lambda: 1) == 3

    execution = policy.public_dict()["control_model_execution"]
    assert isinstance(execution, dict)
    assert execution["typed_requests_executed"] == 1
    assert execution["safety_fallbacks"] == 0
    assert execution["affordance_masked_decisions"] == 1
    assert execution["affordance_masks"] == {"budget_mask": 1}
    assert execution["target_resolution_failures"] == {}


def test_control_execution_requires_move_residency_between_switches() -> None:
    policy = ModelAssistedBattlePolicy(
        model=_model(),
        control_model=_full_control_model(5),
        execute_control_model=True,
        encoder=_ShadowEncoder(),  # type: ignore[arg-type]
        projector=_Projector(),  # type: ignore[arg-type]
        confidence_threshold=0.0,
        require_teacher_agreement=False,
    )
    observation = _observation(
        switch_capabilities=frozenset({BattleSwitchCapability.DIRECT}),
        switch_limit=2,
        require_move_between_switches=True,
    )

    with pytest.raises(LearnedBattleControlRequest):
        policy.choose_move(observation, lambda: 1)
    assert policy.choose_move(observation, lambda: 1) == 3
    with pytest.raises(LearnedBattleControlRequest):
        policy.choose_move(observation, lambda: 1)

    execution = policy.public_dict()["control_model_execution"]
    assert isinstance(execution, dict)
    assert execution["typed_requests_executed"] == 2
    assert execution["safety_fallbacks"] == 0
    assert execution["affordance_masked_decisions"] == 1
    assert execution["affordance_masks"] == {"switch_residency_mask": 1}
    assert execution["target_resolution_failures"] == {}
    last_mask = execution["last_intent_mask"]
    assert isinstance(last_mask, dict)
    assert last_mask["reason"] == "switch_residency_mask"
    assert last_mask["predicted_action"] == "pokemon.core:battle:switch"


def test_switch_residency_is_not_satisfied_by_a_recovery_action() -> None:
    policy = ModelAssistedBattlePolicy(
        model=_model(),
        control_model=_full_control_model(5),
        execute_control_model=True,
        encoder=_ShadowEncoder(),  # type: ignore[arg-type]
        projector=_Projector(),  # type: ignore[arg-type]
        confidence_threshold=0.0,
        require_teacher_agreement=False,
    )
    observation = _observation(
        switch_capabilities=frozenset({BattleSwitchCapability.DIRECT}),
        require_move_between_switches=True,
    )

    with pytest.raises(LearnedBattleControlRequest):
        policy.choose_move(observation, lambda: 1)
    policy._record_control_action(observation, BattleAction.recovery())
    assert policy.choose_move(observation, lambda: 1) == 3

    execution = policy.public_dict()["control_model_execution"]
    assert isinstance(execution, dict)
    assert execution["affordance_masked_decisions"] == 1
    assert execution["affordance_masks"] == {"switch_residency_mask": 1}
    assert execution["target_resolution_failures"] == {}


def test_control_execution_forces_setup_then_real_residency_move() -> None:
    policy = ModelAssistedBattlePolicy(
        model=_model(),
        control_model=_full_control_model(5),
        execute_control_model=True,
        encoder=_ShadowEncoder(),  # type: ignore[arg-type]
        projector=_Projector(),  # type: ignore[arg-type]
        confidence_threshold=0.0,
        require_teacher_agreement=False,
    )
    observation = _observation(
        boost_capabilities=frozenset({BattleBoostStat.SPECIAL}),
        boost_use_limits=((BattleBoostStat.SPECIAL, 1),),
        required_boost_before_first_move=BattleBoostStat.SPECIAL,
        switch_capabilities=frozenset({BattleSwitchCapability.DIRECT}),
        require_move_between_switches=True,
    )

    with pytest.raises(LearnedBattleControlRequest) as switched:
        policy.choose_move(observation, lambda: 1)
    assert switched.value.action.kind is BattleActionKind.SWITCH
    with pytest.raises(LearnedBattleControlRequest) as boosted:
        policy.choose_move(observation, lambda: 1)
    assert boosted.value.action == BattleAction.boost(BattleBoostStat.SPECIAL)
    assert policy.choose_move(observation, lambda: 1) == 3
    with pytest.raises(LearnedBattleControlRequest) as switched_again:
        policy.choose_move(observation, lambda: 1)
    assert switched_again.value.action.kind is BattleActionKind.SWITCH

    execution = policy.public_dict()["control_model_execution"]
    assert isinstance(execution, dict)
    assert execution["intent_forced_requests"] == 1
    assert execution["target_resolution_failures"] == {
        "required_boost_before_first_move_mask": 1,
    }
    assert execution["affordance_masked_decisions"] == 2
    assert execution["affordance_masks"] == {"switch_residency_mask": 2}


def test_control_execution_requires_move_before_first_switch() -> None:
    policy = ModelAssistedBattlePolicy(
        model=_model(),
        control_model=_full_control_model(5),
        execute_control_model=True,
        encoder=_ShadowEncoder(),  # type: ignore[arg-type]
        projector=_Projector(),  # type: ignore[arg-type]
        confidence_threshold=0.0,
        require_teacher_agreement=False,
    )
    observation = _observation(
        switch_capabilities=frozenset({BattleSwitchCapability.DIRECT}),
        require_move_before_first_switch=True,
    )

    assert policy.choose_move(observation, lambda: 1) == 3
    with pytest.raises(LearnedBattleControlRequest):
        policy.choose_move(observation, lambda: 1)

    execution = policy.public_dict()["control_model_execution"]
    assert isinstance(execution, dict)
    assert execution["typed_requests_executed"] == 1
    assert execution["safety_fallbacks"] == 0
    assert execution["affordance_masked_decisions"] == 1
    assert execution["affordance_masks"] == {"initial_switch_residency_mask": 1}
    assert execution["target_resolution_failures"] == {}
    last_mask = execution["last_intent_mask"]
    assert isinstance(last_mask, dict)
    assert last_mask["reason"] == "initial_switch_residency_mask"
    assert last_mask["predicted_action"] == "pokemon.core:battle:switch"


@pytest.mark.parametrize("predicted_class_index", (0, 2, 5))
def test_control_execution_forces_declared_status_clearance_before_dispatch(
    predicted_class_index: int,
) -> None:
    policy = ModelAssistedBattlePolicy(
        model=_model(),
        control_model=_full_control_model(predicted_class_index),
        execute_control_model=True,
        encoder=_ShadowEncoder(),  # type: ignore[arg-type]
        projector=_Projector(),  # type: ignore[arg-type]
        confidence_threshold=0.0,
        require_teacher_agreement=False,
    )

    def teacher_must_not_run() -> int:
        raise AssertionError("intent-forced recovery queried the teacher")

    with pytest.raises(LearnedBattleControlRequest) as raised:
        policy.choose_move(
            _observation(
                recovery_capabilities=frozenset({BattleRecoveryCapability.CURE_PARALYSIS}),
                require_status_clear_before_move=True,
                battler_status=0x40,
            ),
            teacher_must_not_run,
        )

    assert raised.value.party_slot == 1
    assert raised.value.recovery_need == "status"
    assert raised.value.status == "paralysis"
    execution = policy.public_dict()["control_model_execution"]
    assert isinstance(execution, dict)
    assert execution["intent_forced_requests"] == 1
    assert execution["teacher_free_requests"] == 0
    assert execution["typed_requests_executed"] == 1
    assert execution["safety_fallbacks"] == 0
    assert execution["target_resolution_failures"] == {"status_clear_before_move_mask": 1}
    last_mask = execution["last_intent_mask"]
    assert isinstance(last_mask, dict)
    assert last_mask["reason"] == "status_clear_before_move_mask"
    assert last_mask["predicted_action"] == CONTROL_CLASS_REFS[0]


def test_control_execution_forces_declared_hp_floor_before_move() -> None:
    policy = ModelAssistedBattlePolicy(
        model=_model(),
        control_model=_full_control_model(0),
        execute_control_model=True,
        encoder=_ShadowEncoder(),  # type: ignore[arg-type]
        projector=_Projector(),  # type: ignore[arg-type]
        confidence_threshold=0.0,
        require_teacher_agreement=False,
    )

    def teacher_must_not_run() -> int:
        raise AssertionError("intent-forced recovery queried the teacher")

    with pytest.raises(LearnedBattleControlRequest) as raised:
        policy.choose_move(
            _observation(
                recovery_capabilities=frozenset({BattleRecoveryCapability.RESTORE_HP}),
                minimum_hp_before_move=70,
                battler_hp=59,
                battler_max_hp=151,
            ),
            teacher_must_not_run,
        )

    assert raised.value.party_slot == 1
    assert raised.value.recovery_need == "hp"
    execution = policy.public_dict()["control_model_execution"]
    assert isinstance(execution, dict)
    assert execution["intent_forced_requests"] == 1
    assert execution["target_resolution_failures"] == {"minimum_hp_before_move_mask": 1}


@pytest.mark.parametrize(
    "model",
    (
        _model(),
        MaskedMLPMoveRanker(
            feature_names=FEATURE_NAMES,
            input_weights=[[0.0] * len(FEATURE_NAMES)] * 2,
            hidden_bias=[0.0, 0.0],
            output_weights=[0.0, 0.0],
            output_bias=0.0,
        ),
    ),
)
def test_model_loader_authenticates_typed_artifact_stream(
    tmp_path: Path,
    model: MaskedLinearMoveRanker | MaskedMLPMoveRanker,
) -> None:
    artifact = tmp_path / "candidate"
    artifact.mkdir()
    record = {
        "record_type": "battle_model_candidate",
        "model": model.to_dict(),
        "model_sha256": hashlib.sha256(model.to_json().encode("utf-8")).hexdigest(),
    }
    payload = (
        json.dumps(record, allow_nan=False, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode("utf-8")
    model_path = artifact / "model.jsonl"
    model_path.write_bytes(payload)
    (artifact / "manifest.json").write_text(
        json.dumps(
            {
                "status": "complete",
                "files": [
                    {
                        "filename": "model.jsonl",
                        "bytes": len(payload),
                        "records": 1,
                        "sha256": hashlib.sha256(payload).hexdigest(),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    loaded = load_battle_model_artifact(model_path)
    assert loaded.to_json() == model.to_json()

    model_path.write_bytes(payload + b" ")
    with pytest.raises(LearnedBattlePolicyError, match="authentication"):
        load_battle_model_artifact(model_path)
