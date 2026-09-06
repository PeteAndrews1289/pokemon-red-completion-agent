from __future__ import annotations

from datetime import UTC, datetime

import pytest
from test_red_living_dex_targeted_bank_retirement import _capabilities
from test_red_living_dex_targeted_update_capacity import _repeatable_capabilities

from pokemon_red_completion.red_living_dex_causal_inventory import (
    freeze_red_living_dex_targeted_schedule,
)
from pokemon_red_completion.red_living_dex_setup_trust import (
    RedLivingDexSetupProtectedEffectCheckpoint,
)
from pokemon_red_completion.red_living_dex_targeted_bank_retirement import (
    plan_red_living_dex_targeted_bank_retirement,
)
from pokemon_red_completion.red_living_dex_targeted_train_dashboard import (
    RedLivingDexTargetedTrainDashboardError,
    RedLivingDexTargetedTrainDashboardProgress,
    red_living_dex_targeted_train_dashboard_snapshot,
)
from pokemon_red_completion.red_living_dex_targeted_train_runner import (
    RedLivingDexTargetedSetupStatus,
    RedLivingDexTargetedTrainAssignment,
    RedLivingDexTargetedTrainReceipt,
)


def _binding():  # type: ignore[no-untyped-def]
    return freeze_red_living_dex_targeted_schedule(
        _repeatable_capabilities(),
        maximum_train_replays_per_context=5,
    )


def test_targeted_dashboard_describes_collection_without_training_overclaim() -> None:
    binding = _binding()
    assignment = RedLivingDexTargetedTrainAssignment(binding, 0, "a" * 40)
    snapshot = red_living_dex_targeted_train_dashboard_snapshot(
        binding,
        RedLivingDexTargetedTrainDashboardProgress(
            status="running",
            active_assignment=assignment,
            effects=RedLivingDexSetupProtectedEffectCheckpoint(
                controller_actions=12,
                emulator_frames=345,
            ),
        ),
        updated_at=datetime(2026, 9, 5, 22, 0, tzinfo=UTC),
    )
    public = snapshot.public_dict()

    assert public["game"] == "Pokémon Red"
    assert public["run_status"] == "running"
    assert public["actions"] == 12
    assert public["frame_count"] == 345
    assert public["collection"]["target"] == 151
    assert public["experiment"]["zero_shot"] == {"completed": 0, "total": 10}
    assert public["experiment"]["adaptation"] == {"completed": 0, "total": 8}
    assert public["experiment"]["sealed_test"] == {"completed": 0, "total": 1}
    assert public["model"]["mode"] == "waiting"
    assert public["model"]["decisions"] == 0
    encoded = str(public)
    assert "not fitted yet" in encoded
    assert "not model play" in encoded
    assert "98:1" in encoded
    assert "settled 0 of 8; acquire 0 of 3, develop 0 of 3" in encoded
    assert assignment.slot.lineage_sha256 not in encoded
    assert assignment.slot.physical_root_sha256 not in encoded
    assert "/" not in encoded


def test_targeted_dashboard_rejects_false_completion() -> None:
    with pytest.raises(
        RedLivingDexTargetedTrainDashboardError,
        match="cannot pass an incomplete campaign",
    ):
        red_living_dex_targeted_train_dashboard_snapshot(
            _binding(),
            RedLivingDexTargetedTrainDashboardProgress(status="passed"),
        )


def test_targeted_dashboard_describes_the_smaller_root_diverse_successor() -> None:
    binding = plan_red_living_dex_targeted_bank_retirement(
        _capabilities()
    ).binding

    snapshot = red_living_dex_targeted_train_dashboard_snapshot(
        binding,
        RedLivingDexTargetedTrainDashboardProgress(),
    )

    encoded = str(snapshot.public_dict())
    assert snapshot.experiment.zero_shot_total == 8
    assert snapshot.experiment.adaptation_total == 4
    assert "8 train resets across 4 shared base-state clusters" in encoded
    assert "settled 0 of 6; acquire 0 of 1, develop 0 of 3" in encoded
    assert "Fit gate: blocked" in encoded


def test_targeted_dashboard_projects_bounded_setup_diagnostics() -> None:
    binding = _binding()
    failed = RedLivingDexTargetedTrainAssignment(binding, 0, "a" * 40)
    active = RedLivingDexTargetedTrainAssignment(binding, 1, "a" * 40)
    snapshot = red_living_dex_targeted_train_dashboard_snapshot(
        binding,
        RedLivingDexTargetedTrainDashboardProgress(
            status="running",
            active_assignment=active,
            receipts=(
                RedLivingDexTargetedTrainReceipt(
                    failed,
                    RedLivingDexTargetedSetupStatus.FAILED,
                    None,
                    "candidate_route",
                    "production_runtime_error",
                ),
            ),
        ),
    )

    encoded = str(snapshot.public_dict())
    assert "candidate_route 1" in encoded
    assert "production_runtime_error 1" in encoded
    assert failed.slot.physical_root_sha256 not in encoded


def test_targeted_dashboard_rejects_an_active_assignment_from_another_binding() -> None:
    binding = _binding()
    other = _binding()
    object.__setattr__(other.schedule, "maximum_train_replays_per_context", 6)
    assignment = RedLivingDexTargetedTrainAssignment(other, 0, "a" * 40)
    with pytest.raises(RedLivingDexTargetedTrainDashboardError):
        red_living_dex_targeted_train_dashboard_snapshot(
            binding,
            RedLivingDexTargetedTrainDashboardProgress(
                status="running",
                active_assignment=assignment,
            ),
        )
