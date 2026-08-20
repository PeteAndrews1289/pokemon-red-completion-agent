import pytest

from pokemon_red_completion.training import (
    TrainingDirective,
    TrainingObservation,
    TrainingPolicy,
    TrainingReport,
    choose_training_directive,
    choose_training_move_slot,
)

POLICY = TrainingPolicy(55, (4, 2, 3, 1))


def observation(**changes: object) -> TrainingObservation:
    values: dict[str, object] = {
        "level": 51,
        "hp": 150,
        "max_hp": 160,
        "pp": (10, 15, 10, 15),
        "in_battle": False,
    }
    values.update(changes)
    return TrainingObservation(**values)  # type: ignore[arg-type]


def test_training_policy_seeks_fights_heals_and_stops_semantically() -> None:
    assert choose_training_directive(observation(), POLICY) is TrainingDirective.SEEK_ENCOUNTER
    assert (
        choose_training_directive(
            observation(in_battle=True, enemy_level=42), POLICY
        )
        is TrainingDirective.FIGHT
    )
    assert (
        choose_training_directive(observation(hp=60), POLICY)
        is TrainingDirective.RETURN_TO_HEAL
    )
    assert (
        choose_training_directive(observation(status=1), POLICY)
        is TrainingDirective.RETURN_TO_HEAL
    )
    assert (
        choose_training_directive(
            observation(hp=60, in_battle=True, enemy_level=42), POLICY
        )
        is TrainingDirective.FLEE
    )
    assert (
        choose_training_directive(observation(level=55), POLICY)
        is TrainingDirective.STOP
    )


def test_training_policy_rejects_overmatched_encounters_and_honors_bounds() -> None:
    assert (
        choose_training_directive(
            observation(in_battle=True, enemy_level=56), POLICY
        )
        is TrainingDirective.FLEE
    )
    assert (
        choose_training_directive(observation(battles_completed=80), POLICY)
        is TrainingDirective.STOP
    )
    assert (
        choose_training_directive(observation(steps_taken=6_000), POLICY)
        is TrainingDirective.STOP
    )


def test_training_move_selection_uses_ranked_available_pp() -> None:
    assert choose_training_move_slot((10, 15, 10, 0), POLICY.preferred_move_slots) == 2
    with pytest.raises(ValueError, match="no usable"):
        choose_training_move_slot((0, 0, 0, 0), POLICY.preferred_move_slots)


def test_training_receipt_requires_target_battle_and_no_faint() -> None:
    report = TrainingReport("pokemon_mansion_1f", 46, 55, 55, 58, 2, 1_500, 5, False)
    assert report.passed
    assert not TrainingReport(
        "pokemon_mansion_1f", 46, 55, 54, 58, 2, 1_500, 5, False
    ).passed


@pytest.mark.parametrize(
    "policy",
    (
        TrainingPolicy(55, (4,)),
        TrainingPolicy(100, (1, 2, 3, 4), retreat_hp_ratio=0.1),
    ),
)
def test_training_policy_accepts_portable_valid_configurations(policy: TrainingPolicy) -> None:
    assert policy.target_level >= 55
