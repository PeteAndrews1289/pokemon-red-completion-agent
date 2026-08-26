from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from fractions import Fraction

import pytest

from pokemon_red_completion.living_dex_capture_curriculum import (
    LIVING_DEX_CAPTURE_BEHAVIOR_POLICY,
    LIVING_DEX_CAPTURE_PLAN_SCHEMA,
    LIVING_DEX_CAPTURE_QUALIFICATION_SCHEMA,
    LivingDexCaptureAttestation,
    LivingDexCaptureCoverageGate,
    LivingDexCaptureCurriculumError,
    LivingDexCapturePartition,
    LivingDexCaptureSetupBoundary,
    LivingDexCaptureSetupStatus,
    LivingDexCaptureSetupTerminal,
    LivingDexProspectiveCapturePlan,
    LivingDexProspectiveCaptureSlot,
    qualify_living_dex_capture_inventory,
)
from pokemon_red_completion.living_dex_option_value import LivingDexOptionKind


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode("ascii")).hexdigest()


KINDS = tuple(LivingDexOptionKind)
TRAIN_MENUS = (
    (KINDS[0], KINDS[1], KINDS[2]),
    (KINDS[1], KINDS[2], KINDS[3]),
    (KINDS[2], KINDS[3], KINDS[4]),
    (KINDS[3], KINDS[4], KINDS[5]),
    (KINDS[4], KINDS[5], KINDS[6]),
    (KINDS[5], KINDS[6], KINDS[7]),
    (KINDS[0], KINDS[6], KINDS[7]),
    (KINDS[0], KINDS[1], KINDS[7]),
    (KINDS[0], KINDS[2], KINDS[4], KINDS[6]),
    (KINDS[1], KINDS[3], KINDS[5], KINDS[7]),
)
DEVELOPMENT_MENUS = (
    (KINDS[0], KINDS[3], KINDS[4]),
    (KINDS[1], KINDS[3], KINDS[5]),
    (KINDS[0], KINDS[5], KINDS[6]),
    (KINDS[1], KINDS[4], KINDS[7]),
    (KINDS[2], KINDS[3], KINDS[6]),
)


def _slot(
    index: int,
    partition: LivingDexCapturePartition,
    kinds: tuple[LivingDexOptionKind, ...],
    *,
    family_scope_id: str,
    location_scope_id: str,
) -> LivingDexProspectiveCaptureSlot:
    label = f"{partition.value}-{index:02d}"
    return LivingDexProspectiveCaptureSlot(
        slot_id=label,
        partition=partition,
        available_option_kinds=kinds,
        family_scope_id=family_scope_id,
        location_scope_id=location_scope_id,
        root_slot_id=f"root-{label}",
        setup=LivingDexCaptureSetupBoundary(
            setup_plan_sha256=_sha(f"setup-{label}"),
            terminal_predicate_sha256=_sha(f"terminal-{label}"),
            observer_contract_sha256=_sha(f"observer-contract-{label}"),
            maximum_controller_actions=1000,
            maximum_emulator_frames=60_000,
        ),
    )


def _slots() -> tuple[LivingDexProspectiveCaptureSlot, ...]:
    train = tuple(
        _slot(
            index,
            LivingDexCapturePartition.TRAIN,
            kinds,
            family_scope_id=(
                "train-family-0"
                if index < 4
                else "train-family-1"
                if index < 7
                else "train-family-2"
            ),
            location_scope_id=f"train-location-{index // 2}",
        )
        for index, kinds in enumerate(TRAIN_MENUS)
    )
    development = tuple(
        _slot(
            index,
            LivingDexCapturePartition.DEVELOPMENT,
            kinds,
            family_scope_id=f"development-family-{index}",
            location_scope_id=f"development-location-{index}",
        )
        for index, kinds in enumerate(DEVELOPMENT_MENUS)
    )
    return (*train, *development)


def _plan(
    slots: tuple[LivingDexProspectiveCaptureSlot, ...] | None = None,
) -> LivingDexProspectiveCapturePlan:
    return LivingDexProspectiveCapturePlan(_slots() if slots is None else slots)


def _attestation(
    slot: LivingDexProspectiveCaptureSlot,
    *,
    changes: dict[str, object] | None = None,
) -> LivingDexCaptureAttestation:
    values: dict[str, object] = {
        "slot_sha256": slot.slot_sha256,
        "setup_plan_sha256": slot.setup.setup_plan_sha256,
        "terminal_predicate_sha256": slot.setup.terminal_predicate_sha256,
        "observer_contract_sha256": slot.setup.observer_contract_sha256,
        "root_consumption_sha256": _sha(f"physical-root-{slot.slot_id}"),
        "state_sha256": _sha(f"state-{slot.slot_id}"),
        "envelope_sha256": _sha(f"envelope-{slot.slot_id}"),
        "menu_sha256": _sha(f"menu-{slot.slot_id}"),
        "observer_binding_sha256": _sha(f"observer-binding-{slot.slot_id}"),
        "available_option_kinds": slot.available_option_kinds,
        "available_family_sha256s": tuple(
            _sha(f"family-{slot.family_scope_id}-{kind.value}")
            for kind in slot.available_option_kinds
        ),
        "location_sha256": _sha(f"location-{slot.location_scope_id}"),
        "setup_controller_actions": 100,
        "setup_emulator_frames": 1000,
    }
    if changes:
        values.update(changes)
    return LivingDexCaptureAttestation(**values)  # type: ignore[arg-type]


def _terminals(
    plan: LivingDexProspectiveCapturePlan,
    *,
    censored: frozenset[str] = frozenset(),
) -> tuple[LivingDexCaptureSetupTerminal, ...]:
    result = []
    for slot in plan.slots:
        if slot.slot_id in censored:
            result.append(
                LivingDexCaptureSetupTerminal(
                    slot_sha256=slot.slot_sha256,
                    claim_sha256=_sha(f"claim-{slot.slot_id}"),
                    status=LivingDexCaptureSetupStatus.INTERRUPTED,
                    setup_controller_actions=50,
                    setup_emulator_frames=500,
                )
            )
            continue
        attestation = _attestation(slot)
        result.append(
            LivingDexCaptureSetupTerminal(
                slot_sha256=slot.slot_sha256,
                claim_sha256=_sha(f"claim-{slot.slot_id}"),
                status=LivingDexCaptureSetupStatus.COMPLETE,
                setup_controller_actions=attestation.setup_controller_actions,
                setup_emulator_frames=attestation.setup_emulator_frames,
                attestation=attestation,
            )
        )
    return tuple(result)


def test_plan_preregisters_reserve_and_selected_arm_kind_power() -> None:
    plan = _plan()

    assert plan.behavior_policy == LIVING_DEX_CAPTURE_BEHAVIOR_POLICY
    assert plan.execute_every_slot is True
    assert plan.adaptive_replacement_allowed is False
    assert len(plan.partition_slots(LivingDexCapturePartition.TRAIN)) == 10
    assert len(plan.partition_slots(LivingDexCapturePartition.DEVELOPMENT)) == 5
    assert plan.minimum_train_selected_kind_probability > Fraction(98, 100)

    public = plan.public_dict()
    assert public["schema"] == LIVING_DEX_CAPTURE_PLAN_SCHEMA
    assert public["partition_counts"] == {"development": 5, "train": 10}
    assert public["menu_width_counts"] == {"3": 13, "4": 2}
    assert public["family_scope_overlap"] == 0
    assert public["location_scope_overlap"] == 0
    assert public["setup_learner_labels"] == 0
    assert public["identity_fields_public"] == 0
    assert public["private_path_fields"] == 0


def test_plan_requires_reserve_before_any_setup_runs() -> None:
    slots = tuple(item for item in _slots() if item.slot_id != "train-09")

    with pytest.raises(
        LivingDexCaptureCurriculumError,
        match="pre-registered train reserve",
    ):
        _plan(slots)

    slots = tuple(
        item for item in _slots() if item.slot_id != "development-04"
    )
    with pytest.raises(
        LivingDexCaptureCurriculumError,
        match="pre-registered development reserve",
    ):
        _plan(slots)


def test_offered_kind_union_cannot_replace_selected_arm_power() -> None:
    weak = tuple(
        replace(
            item,
            available_option_kinds=(
                KINDS[0],
                KINDS[1],
                KINDS[2],
            )
            if item.partition is LivingDexCapturePartition.DEVELOPMENT
            or item.slot_id != "train-09"
            else (KINDS[0], KINDS[1], KINDS[3]),
        )
        for item in _slots()
    )

    with pytest.raises(
        LivingDexCaptureCurriculumError,
        match="selected-kind coverage probability",
    ):
        _plan(weak)


def test_plan_rejects_reused_physical_root_scopes() -> None:
    slots = list(_slots())
    slots[1] = replace(slots[1], root_slot_id=slots[0].root_slot_id)

    with pytest.raises(LivingDexCaptureCurriculumError, match="root slots repeat"):
        _plan(tuple(slots))


def test_plan_rejects_family_scopes_that_lose_selected_arm_diversity() -> None:
    slots = list(_slots())
    for index in range(4, 10):
        slots[index] = replace(slots[index], family_scope_id="train-family-1")

    with pytest.raises(
        LivingDexCaptureCurriculumError,
        match="loses selected train family coverage",
    ):
        _plan(tuple(slots))

    slots = list(_slots())
    slots[10] = replace(
        slots[10],
        family_scope_id=slots[0].family_scope_id,
    )
    with pytest.raises(
        LivingDexCaptureCurriculumError,
        match="train and development family scopes overlap",
    ):
        _plan(tuple(slots))

    slots = list(_slots())
    slots[14] = replace(
        slots[14],
        family_scope_id=slots[13].family_scope_id,
    )
    with pytest.raises(
        LivingDexCaptureCurriculumError,
        match="loses selected development family coverage",
    ):
        _plan(tuple(slots))


def test_plan_rejects_development_location_reuse_or_partition_overlap() -> None:
    slots = list(_slots())
    slots[11] = replace(
        slots[11],
        location_scope_id=slots[10].location_scope_id,
    )
    with pytest.raises(
        LivingDexCaptureCurriculumError,
        match="development location scopes repeat",
    ):
        _plan(tuple(slots))

    slots = list(_slots())
    slots[10] = replace(
        slots[10],
        location_scope_id=slots[0].location_scope_id,
    )
    with pytest.raises(
        LivingDexCaptureCurriculumError,
        match="train and development locations overlap",
    ):
        _plan(tuple(slots))


def test_setup_boundary_cannot_become_a_teacher_label() -> None:
    slots = list(_slots())
    setup = slots[0].setup
    object.__setattr__(setup, "learner_labels_emitted", 1)

    with pytest.raises(
        LivingDexCaptureCurriculumError,
        match="acquired learner authority",
    ):
        _plan(tuple(slots))


@pytest.mark.parametrize(
    ("field_name", "value"),
    (
        ("deterministic_setup", False),
        ("claim_before_controller_input", False),
        ("capture_before_behavior_draw", False),
        ("retry_after_controller_input", True),
    ),
)
def test_setup_authority_boundary_is_rechecked(
    field_name: str,
    value: bool,
) -> None:
    slots = list(_slots())
    object.__setattr__(slots[0].setup, field_name, value)

    with pytest.raises(
        LivingDexCaptureCurriculumError,
        match="setup authority boundary differs",
    ):
        _plan(tuple(slots))


@pytest.mark.parametrize(
    ("field_name", "value"),
    (
        ("behavior_policy", "caller-selected-arm"),
        ("execute_every_slot", False),
        ("adaptive_replacement_allowed", True),
    ),
)
def test_plan_policy_and_nonadaptive_denominator_are_rechecked(
    field_name: str,
    value: object,
) -> None:
    plan = _plan()
    object.__setattr__(plan, field_name, value)

    with pytest.raises(
        LivingDexCaptureCurriculumError,
        match="cannot select slots from outcomes",
    ):
        plan.__post_init__()


def test_complete_capture_inventory_reconciles_without_learner_effects() -> None:
    plan = _plan()
    inventory = qualify_living_dex_capture_inventory(plan, _terminals(plan))

    public = inventory.public_dict()
    assert public["schema"] == LIVING_DEX_CAPTURE_QUALIFICATION_SCHEMA
    assert public["all_slots_reconciled"] is True
    assert public["status_counts"] == {
        "complete": 15,
        "failed": 0,
        "interrupted": 0,
    }
    assert public["train_complete_count"] == 10
    assert public["development_complete_count"] == 5
    assert public["setup_controller_actions"] == 1500
    assert public["setup_emulator_frames"] == 15_000
    assert public["behavior_draws"] == 0
    assert public["learner_controller_actions"] == 0
    assert public["learner_labels_emitted"] == 0
    assert public["learner_outcomes_observed"] == 0
    assert public["model_fits"] == 0
    assert public["retry_allowed"] is False


def test_frozen_reserve_tolerates_two_train_and_one_development_censors() -> None:
    plan = _plan()
    censored = frozenset({"train-00", "train-09", "development-04"})
    inventory = qualify_living_dex_capture_inventory(
        plan,
        _terminals(plan, censored=censored),
    )

    public = inventory.public_dict()
    assert public["status_counts"] == {
        "complete": 12,
        "failed": 0,
        "interrupted": 3,
    }
    assert public["train_complete_count"] == 8
    assert public["development_complete_count"] == 4


def test_campaign_cannot_adaptively_drop_more_slots_than_preregistered() -> None:
    plan = _plan()
    censored = frozenset({"train-00", "train-01", "train-02"})

    with pytest.raises(
        LivingDexCaptureCurriculumError,
        match="exceeds train censor reserve",
    ):
        qualify_living_dex_capture_inventory(
            plan,
            _terminals(plan, censored=censored),
        )

    censored = frozenset({"development-00", "development-01"})
    with pytest.raises(
        LivingDexCaptureCurriculumError,
        match="exceeds development censor reserve",
    ):
        qualify_living_dex_capture_inventory(
            plan,
            _terminals(plan, censored=censored),
        )


def test_campaign_requires_one_terminal_for_every_frozen_slot() -> None:
    plan = _plan()

    with pytest.raises(
        LivingDexCaptureCurriculumError,
        match="does not reconcile every slot",
    ):
        qualify_living_dex_capture_inventory(plan, _terminals(plan)[:-1])


def test_capture_attestation_must_match_menu_and_setup_contract() -> None:
    plan = _plan()
    terminals = list(_terminals(plan))
    slot = plan.slots[0]
    changed = _attestation(
        slot,
        changes={
            "available_option_kinds": (
                KINDS[0],
                KINDS[1],
                KINDS[3],
            ),
            "available_family_sha256s": (
                _sha("changed-family-0"),
                _sha("changed-family-1"),
                _sha("changed-family-2"),
            ),
        },
    )
    terminals[0] = replace(terminals[0], attestation=changed)

    with pytest.raises(
        LivingDexCaptureCurriculumError,
        match="differs from its prospective slot",
    ):
        qualify_living_dex_capture_inventory(plan, tuple(terminals))


def test_capture_inventory_rejects_actual_family_overlap() -> None:
    plan = _plan()
    terminals = list(_terminals(plan))
    first = terminals[0].attestation
    second = terminals[4].attestation
    assert first is not None and second is not None
    changed = replace(
        second,
        available_family_sha256s=(
            first.available_family_sha256s[0],
            *second.available_family_sha256s[1:],
        ),
    )
    terminals[4] = replace(terminals[4], attestation=changed)

    with pytest.raises(
        LivingDexCaptureCurriculumError,
        match="family scopes overlap",
    ):
        qualify_living_dex_capture_inventory(plan, tuple(terminals))


def test_capture_inventory_rejects_actual_root_or_observer_reuse() -> None:
    plan = _plan()
    for field_name, expected in (
        ("root_consumption_sha256", "capture roots repeat"),
        ("observer_binding_sha256", "capture observer bindings repeat"),
    ):
        terminals = list(_terminals(plan))
        first = terminals[0].attestation
        second = terminals[1].attestation
        assert first is not None and second is not None
        changed = replace(
            second,
            **{field_name: getattr(first, field_name)},
        )
        terminals[1] = replace(terminals[1], attestation=changed)
        with pytest.raises(LivingDexCaptureCurriculumError, match=expected):
            qualify_living_dex_capture_inventory(plan, tuple(terminals))


def test_capture_inventory_binds_actual_locations_to_logical_scopes() -> None:
    plan = _plan()
    terminals = list(_terminals(plan))
    first = terminals[0].attestation
    second = terminals[1].attestation
    assert first is not None and second is not None
    assert plan.slots[0].location_scope_id == plan.slots[1].location_scope_id
    changed = replace(second, location_sha256=_sha("different-physical-location"))
    terminals[1] = replace(terminals[1], attestation=changed)

    with pytest.raises(
        LivingDexCaptureCurriculumError,
        match="scope maps to multiple locations",
    ):
        qualify_living_dex_capture_inventory(plan, tuple(terminals))


def test_setup_terminal_budget_and_zero_effects_are_rechecked() -> None:
    plan = _plan()
    terminals = list(_terminals(plan))
    first_attestation = terminals[0].attestation
    assert first_attestation is not None
    terminals[0] = replace(
        terminals[0],
        setup_controller_actions=plan.slots[0].setup.maximum_controller_actions + 1,
        attestation=replace(
            first_attestation,
            setup_controller_actions=(
                plan.slots[0].setup.maximum_controller_actions + 1
            ),
        ),
    )
    with pytest.raises(
        LivingDexCaptureCurriculumError,
        match="exceeds its frozen budget",
    ):
        qualify_living_dex_capture_inventory(plan, tuple(terminals))

    terminals = list(_terminals(plan))
    attestation = terminals[0].attestation
    assert attestation is not None
    object.__setattr__(attestation, "learner_behavior_draws", 1)
    with pytest.raises(
        LivingDexCaptureCurriculumError,
        match="acquired learner authority",
    ):
        qualify_living_dex_capture_inventory(plan, tuple(terminals))


def test_public_receipt_contains_no_private_capture_values() -> None:
    plan = _plan()
    terminals = _terminals(plan)
    inventory = qualify_living_dex_capture_inventory(plan, terminals)
    encoded = json.dumps(inventory.public_dict(), sort_keys=True)

    for terminal in terminals:
        assert terminal.claim_sha256 not in encoded
        if terminal.attestation is None:
            continue
        private = terminal.attestation
        for value in (
            private.root_consumption_sha256,
            private.state_sha256,
            private.envelope_sha256,
            private.menu_sha256,
            private.observer_binding_sha256,
            private.location_sha256,
            *private.available_family_sha256s,
        ):
            assert value not in encoded
    assert "identity_fields_public\": 0" in encoded
    assert "private_path_fields\": 0" in encoded


def test_gate_rejects_impossible_probability_or_kind_threshold() -> None:
    with pytest.raises(
        LivingDexCaptureCurriculumError,
        match="probability threshold",
    ):
        LivingDexCaptureCoverageGate(
            minimum_train_kind_probability_numerator=101,
            minimum_train_kind_probability_denominator=100,
        )
    with pytest.raises(
        LivingDexCaptureCurriculumError,
        match="unavailable option kinds",
    ):
        LivingDexCaptureCoverageGate(
            minimum_train_option_kinds=len(LivingDexOptionKind) + 1,
        )
    with pytest.raises(
        LivingDexCaptureCurriculumError,
        match="development location threshold is impossible",
    ):
        LivingDexCaptureCoverageGate(
            minimum_development_examples=4,
            minimum_development_locations=5,
        )
