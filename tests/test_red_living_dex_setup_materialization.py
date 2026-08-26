from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.living_dex_capture_curriculum import (
    LivingDexProspectiveCaptureSlot,
)
from pokemon_red_completion.living_dex_option_value import LivingDexOptionKind
from pokemon_red_completion.private_artifacts import (
    PrivateArtifactRoot,
    initialize_private_root,
)
from pokemon_red_completion.red_living_dex_capture_plan import (
    RED_LIVING_DEX_EXECUTOR_CAPABILITIES,
    build_red_living_dex_prospective_capture_plan,
)
from pokemon_red_completion.red_living_dex_setup_campaign import (
    RedLivingDexSetupCampaignError,
    RedLivingDexSetupOptionBinding,
    RedLivingDexSetupSlotBinding,
    RedLivingDexSetupTransportKind,
)
from pokemon_red_completion.red_living_dex_setup_materialization import (
    RED_LIVING_DEX_SETUP_MATERIALIZATION_RECORD_ID,
    RedLivingDexSetupMaterializationCheckpoint,
    RedLivingDexSetupMaterializationError,
    RedLivingDexSetupPrivateSourceAttestation,
    materialize_red_living_dex_setup_bindings,
)


def _digest(value: object) -> str:
    return hashlib.sha256(str(value).encode("ascii")).hexdigest()


_CAPABILITY = {item.option_kind: item for item in RED_LIVING_DEX_EXECUTOR_CAPABILITIES}
_GOAL_KIND = {
    LivingDexOptionKind.ACQUIRE: GoalKind.ACQUIRE_SPECIES,
    LivingDexOptionKind.EVOLVE: GoalKind.EVOLVE_SPECIES,
    LivingDexOptionKind.DEVELOP: GoalKind.DEVELOP_TEAM,
    LivingDexOptionKind.MANAGE_STORAGE: GoalKind.MANAGE_STORAGE,
    LivingDexOptionKind.RESUPPLY: GoalKind.RESUPPLY,
    LivingDexOptionKind.UNLOCK_ACCESS: GoalKind.ADVANCE_STORY,
    LivingDexOptionKind.EXPLORE: GoalKind.EXPLORE,
}


def _provider_contract(kind: LivingDexOptionKind) -> str:
    provider = _CAPABILITY[kind].executor_types[0]
    return f"{provider.__module__}.{provider.__qualname__}"


def _binding(index: int) -> RedLivingDexSetupSlotBinding:
    slot = build_red_living_dex_prospective_capture_plan().slots[index]
    origin_state = _digest(("origin-state", index))
    origin_boundary = _digest(("origin-boundary", index))
    local = index == 0
    options = []
    for option_index, kind in enumerate(slot.available_option_kinds):
        suffix = (index, option_index, kind.value)
        options.append(
            RedLivingDexSetupOptionBinding(
                option_kind=kind,
                goal_kind=_GOAL_KIND[kind],
                transport_kind=(
                    RedLivingDexSetupTransportKind.LOCAL
                    if local
                    else RedLivingDexSetupTransportKind.ROUTED
                ),
                provider_contract_id=_provider_contract(kind),
                provider_capability_sha256=_CAPABILITY[kind].capability_sha256,
                origin_state_sha256=origin_state,
                origin_boundary_sha256=origin_boundary,
                destination_terminal_boundary_sha256=(
                    origin_boundary if local else _digest(("destination-boundary", *suffix))
                ),
                expected_fresh_observation_sha256=_digest(("fresh-observation", *suffix)),
                expected_provider_offer_sha256=_digest(("provider-offer", *suffix)),
                expected_executable_binding_sha256=_digest(("executable-binding", *suffix)),
                route_plan_sha256=(None if local else _digest(("route-plan", *suffix))),
                route_terminal_predicate_sha256=(
                    None if local else _digest(("route-terminal", *suffix))
                ),
                route_planner_binding_sha256=(
                    None if local else _digest(("route-planner", *suffix))
                ),
            )
        )
    return RedLivingDexSetupSlotBinding(
        slot_sha256=slot.slot_sha256,
        setup_plan_sha256=slot.setup.setup_plan_sha256,
        terminal_predicate_sha256=slot.setup.terminal_predicate_sha256,
        observer_contract_sha256=slot.setup.observer_contract_sha256,
        partition=slot.partition,
        available_option_kinds=slot.available_option_kinds,
        root_consumption_sha256=_digest(("root", index)),
        state_sha256=origin_state,
        origin_boundary_sha256=origin_boundary,
        envelope_sha256=_digest(("envelope", index)),
        menu_sha256=_digest(("menu", index)),
        observer_binding_sha256=_digest(("observer", index)),
        available_family_sha256s=tuple(
            _digest(("family", slot.family_scope_id, option_index, index))
            for option_index, _kind in enumerate(slot.available_option_kinds)
        ),
        location_sha256=_digest(("location", slot.location_scope_id)),
        option_bindings=tuple(options),
    )


def _store(tmp_path: Path) -> PrivateArtifactRoot:
    repository = tmp_path / "repository"
    root = tmp_path / "private"
    repository.mkdir()
    root.mkdir()

    def device_id(path: Path) -> int:
        return 2 if path == root.resolve() else 1

    return initialize_private_root(
        root,
        repository_root=repository,
        device_id=device_id,
        git_worktree_probe=lambda _path: False,
    )


class _Meter:
    def __init__(self) -> None:
        self.authority = 0
        self.actions = 0
        self.frames = 0
        self.behavior = 0
        self.labels = 0
        self.outcomes = 0
        self.predictions = 0
        self.fits = 0
        self.claims = 0
        self.teachers = 0

    def checkpoint(self) -> RedLivingDexSetupMaterializationCheckpoint:
        return RedLivingDexSetupMaterializationCheckpoint(
            controller_authority_attempts=self.authority,
            controller_actions=self.actions,
            emulator_frames=self.frames,
            behavior_draws=self.behavior,
            learner_labels=self.labels,
            learner_outcomes=self.outcomes,
            model_predictions=self.predictions,
            model_fits=self.fits,
            root_claims=self.claims,
            teacher_queries=self.teachers,
        )


class _Source:
    def __init__(
        self,
        meter: _Meter,
        *,
        cross_join_at: int | None = None,
        changed_offer: bool = False,
        effect_at: int | None = None,
        fail_at: int | None = None,
        change_attestation: bool = False,
    ) -> None:
        self.effects_meter = meter
        self.cross_join_at = cross_join_at
        self.changed_offer = changed_offer
        self.effect_at = effect_at
        self.fail_at = fail_at
        self.change_attestation = change_attestation
        self.calls: list[str] = []
        self.attestation_calls = 0

    def attest_source(self) -> RedLivingDexSetupPrivateSourceAttestation:
        self.attestation_calls += 1
        return RedLivingDexSetupPrivateSourceAttestation(
            source_manifest_sha256=_digest("private-source-manifest"),
            source_adapter_contract_id="tests.private.RedSetupBindingSourceV1",
            authenticated_input_count=15,
            protected_input_set_sha256=_digest(
                "changed-protected-input-set"
                if self.change_attestation and self.attestation_calls > 1
                else "protected-input-set"
            ),
        )

    def materialize_slot(
        self,
        slot: LivingDexProspectiveCaptureSlot,
    ) -> RedLivingDexSetupSlotBinding:
        slots = build_red_living_dex_prospective_capture_plan().slots
        index = next(
            i for i, expected in enumerate(slots) if expected.slot_sha256 == slot.slot_sha256
        )
        self.calls.append(slot.slot_sha256)
        if index == self.fail_at:
            raise RuntimeError("fixture source failure")
        if index == self.effect_at:
            self.effects_meter.authority += 1
        binding = _binding(index + 1 if index == self.cross_join_at else index)
        if index == 0 and self.changed_offer:
            option = replace(
                binding.option_bindings[0],
                expected_provider_offer_sha256=_digest("changed-provider-offer"),
            )
            binding = replace(
                binding,
                option_bindings=(option, *binding.option_bindings[1:]),
            )
        return binding


class _EffectfulMeterPropertySource(_Source):
    def __init__(self, meter: _Meter) -> None:
        self._effects_meter = meter
        super().__init__(meter)

    @property
    def effects_meter(self) -> _Meter:
        self._effects_meter.authority += 1
        return self._effects_meter

    @effects_meter.setter
    def effects_meter(self, value: _Meter) -> None:
        self._effects_meter = value


class _FailingMeterPropertySource(_Source):
    def __init__(self, meter: _Meter, private_detail: str) -> None:
        self._effects_meter = meter
        self._private_detail = private_detail
        super().__init__(meter)

    @property
    def effects_meter(self) -> _Meter:
        raise RuntimeError(self._private_detail)

    @effects_meter.setter
    def effects_meter(self, value: _Meter) -> None:
        self._effects_meter = value


class _InterruptingSource(_Source):
    def materialize_slot(
        self,
        slot: LivingDexProspectiveCaptureSlot,
    ) -> RedLivingDexSetupSlotBinding:
        raise KeyboardInterrupt


def test_materializer_freezes_all_fifteen_slots_and_seals_one_private_plan(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    meter = _Meter()
    source = _Source(meter)

    result = materialize_red_living_dex_setup_bindings(
        store,
        source=source,
        effects_meter=meter,
    )

    canonical = build_red_living_dex_prospective_capture_plan()
    assert source.calls == [slot.slot_sha256 for slot in canonical.slots]
    assert len(result.plan.bindings) == 15
    assert sum(len(item.option_bindings) for item in result.plan.bindings) == 45
    assert result.plan.local_slot_count == 1
    assert result.plan.routed_slot_count == 14
    assert result.effects_before == result.effects_after
    sealed = store.find_sealed_record(
        RED_LIVING_DEX_SETUP_MATERIALIZATION_RECORD_ID,
        expected_kind="red_living_dex_setup_binding_materialization",
    )
    assert sealed is not None
    assert sealed.read() == result.private_dict()


def test_public_materialization_is_aggregate_path_free_and_not_execution_authority(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    meter = _Meter()
    result = materialize_red_living_dex_setup_bindings(
        store,
        source=_Source(meter),
        effects_meter=meter,
    )
    public = result.public_dict()
    encoded = json.dumps(public, sort_keys=True)

    assert public["slot_count"] == 15
    assert public["provider_contracts_bound"] == 45
    assert public["train_slots"] == 10
    assert public["development_slots"] == 5
    assert public["runtime_private_bindings_authenticated"] is True
    assert public["runtime_private_routes_executed"] is False
    assert public["actionful_setup_execution_authorized"] is False
    for value in (
        result.materialization_sha256,
        result.plan.plan_sha256,
        result.source_attestation.source_manifest_sha256,
        result.plan.bindings[0].state_sha256,
        result.plan.bindings[1].option_bindings[0].route_plan_sha256,
    ):
        assert value not in encoded
    assert '"private_identity_fields": 0' in encoded
    assert '"private_path_fields": 0' in encoded


def test_source_must_share_the_exact_independent_effect_meter(tmp_path: Path) -> None:
    store = _store(tmp_path)
    source_meter = _Meter()

    with pytest.raises(
        RedLivingDexSetupMaterializationError,
        match="share the protected-effect meter",
    ):
        materialize_red_living_dex_setup_bindings(
            store,
            source=_Source(source_meter),
            effects_meter=_Meter(),
        )
    assert store.find_sealed_record(RED_LIVING_DEX_SETUP_MATERIALIZATION_RECORD_ID) is None


def test_source_introspection_cannot_hide_a_protected_effect_before_the_baseline(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    meter = _Meter()

    with pytest.raises(
        RedLivingDexSetupMaterializationError,
        match="changed a protected effect",
    ):
        materialize_red_living_dex_setup_bindings(
            store,
            source=_EffectfulMeterPropertySource(meter),
            effects_meter=meter,
        )
    assert store.find_sealed_record(RED_LIVING_DEX_SETUP_MATERIALIZATION_RECORD_ID) is None


def test_private_source_inspection_failure_is_sanitized(tmp_path: Path) -> None:
    store = _store(tmp_path)
    meter = _Meter()
    private_detail = "/private/source/secret-adapter.json"

    with pytest.raises(RedLivingDexSetupMaterializationError) as failure:
        materialize_red_living_dex_setup_bindings(
            store,
            source=_FailingMeterPropertySource(meter, private_detail),
            effects_meter=meter,
        )
    assert private_detail not in str(failure.value)
    assert store.find_sealed_record(RED_LIVING_DEX_SETUP_MATERIALIZATION_RECORD_ID) is None


def test_any_protected_effect_fails_before_private_plan_publication(tmp_path: Path) -> None:
    store = _store(tmp_path)
    meter = _Meter()

    with pytest.raises(
        RedLivingDexSetupMaterializationError,
        match="changed a protected effect",
    ):
        materialize_red_living_dex_setup_bindings(
            store,
            source=_Source(meter, effect_at=3),
            effects_meter=meter,
        )
    assert store.find_sealed_record(RED_LIVING_DEX_SETUP_MATERIALIZATION_RECORD_ID) is None


def test_cross_joined_slot_fails_before_private_plan_publication(tmp_path: Path) -> None:
    store = _store(tmp_path)
    meter = _Meter()

    with pytest.raises(RedLivingDexSetupCampaignError, match="prospective slot"):
        materialize_red_living_dex_setup_bindings(
            store,
            source=_Source(meter, cross_join_at=1),
            effects_meter=meter,
        )
    assert store.find_sealed_record(RED_LIVING_DEX_SETUP_MATERIALIZATION_RECORD_ID) is None


def test_action_free_source_failure_leaves_no_record_and_can_be_retried(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    meter = _Meter()

    with pytest.raises(
        RedLivingDexSetupMaterializationError,
        match="private slot source failed",
    ):
        materialize_red_living_dex_setup_bindings(
            store,
            source=_Source(meter, fail_at=4),
            effects_meter=meter,
        )
    assert store.find_sealed_record(RED_LIVING_DEX_SETUP_MATERIALIZATION_RECORD_ID) is None

    result = materialize_red_living_dex_setup_bindings(
        store,
        source=_Source(meter),
        effects_meter=meter,
    )
    assert len(result.plan.bindings) == 15


def test_private_source_failures_are_sanitized_but_process_interruptions_propagate(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    meter = _Meter()
    private_detail = "/private/source/secret-capture.json"

    class _PrivateFailureSource(_Source):
        def materialize_slot(
            self,
            slot: LivingDexProspectiveCaptureSlot,
        ) -> RedLivingDexSetupSlotBinding:
            raise RuntimeError(private_detail)

    with pytest.raises(RedLivingDexSetupMaterializationError) as failure:
        materialize_red_living_dex_setup_bindings(
            store,
            source=_PrivateFailureSource(meter),
            effects_meter=meter,
        )
    assert private_detail not in str(failure.value)
    assert store.find_sealed_record(RED_LIVING_DEX_SETUP_MATERIALIZATION_RECORD_ID) is None

    with pytest.raises(KeyboardInterrupt):
        materialize_red_living_dex_setup_bindings(
            store,
            source=_InterruptingSource(meter),
            effects_meter=meter,
        )
    assert store.find_sealed_record(RED_LIVING_DEX_SETUP_MATERIALIZATION_RECORD_ID) is None


def test_private_input_set_must_be_identical_before_and_after_binding(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    meter = _Meter()

    with pytest.raises(
        RedLivingDexSetupMaterializationError,
        match="input set changed during binding",
    ):
        materialize_red_living_dex_setup_bindings(
            store,
            source=_Source(meter, change_attestation=True),
            effects_meter=meter,
        )
    assert store.find_sealed_record(RED_LIVING_DEX_SETUP_MATERIALIZATION_RECORD_ID) is None


def test_a_different_private_plan_cannot_replace_the_sealed_plan(tmp_path: Path) -> None:
    store = _store(tmp_path)
    meter = _Meter()
    original = materialize_red_living_dex_setup_bindings(
        store,
        source=_Source(meter),
        effects_meter=meter,
    )

    with pytest.raises(
        RedLivingDexSetupMaterializationError,
        match="different content",
    ):
        materialize_red_living_dex_setup_bindings(
            store,
            source=_Source(meter, changed_offer=True),
            effects_meter=meter,
        )
    sealed = store.find_sealed_record(RED_LIVING_DEX_SETUP_MATERIALIZATION_RECORD_ID)
    assert sealed is not None
    assert sealed.read() == original.private_dict()


def test_source_attestation_cannot_be_synthetic_or_empty() -> None:
    with pytest.raises(
        RedLivingDexSetupMaterializationError,
        match="authenticated input count",
    ):
        RedLivingDexSetupPrivateSourceAttestation(
            source_manifest_sha256=_digest("manifest"),
            source_adapter_contract_id="tests.private.RedSetupBindingSourceV1",
            authenticated_input_count=0,
            protected_input_set_sha256=_digest("inputs"),
        )

    attestation = RedLivingDexSetupPrivateSourceAttestation(
        source_manifest_sha256=_digest("manifest"),
        source_adapter_contract_id="tests.private.RedSetupBindingSourceV1",
        authenticated_input_count=15,
        protected_input_set_sha256=_digest("inputs"),
    )
    object.__setattr__(attestation, "synthetic_inputs", True)
    with pytest.raises(
        RedLivingDexSetupMaterializationError,
        match="authentic unchanged private inputs",
    ):
        attestation.__post_init__()
