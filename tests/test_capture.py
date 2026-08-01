import pytest

from pokemon_red_completion.capture import (
    CaptureDirective,
    CaptureObservation,
    CapturePolicy,
    balls_required_estimate,
    plan_capture,
)
from pokemon_red_completion.party import (
    MoveObservation,
    PartyMemberObservation,
    StatusCondition,
)

POLICY = CapturePolicy()
SNORLAX_SPECIES_ID = 0x84


def catcher(**changes: object) -> PartyMemberObservation:
    values: dict[str, object] = {
        "slot": 1,
        "species_id": 0x1C,
        "level": 50,
        "hp": 150,
        "max_hp": 160,
        "moves": (MoveObservation(0x3D, 15, 20),),
    }
    values.update(changes)
    return PartyMemberObservation(**values)  # type: ignore[arg-type]


def encounter(**changes: object) -> CaptureObservation:
    values: dict[str, object] = {
        "target_species_id": SNORLAX_SPECIES_ID,
        "target_level": 30,
        "target_hp": 100,
        "target_max_hp": 110,
        "catcher": catcher(),
        "balls_available": 20,
        "party_has_room": True,
    }
    values.update(changes)
    return CaptureObservation(**values)  # type: ignore[arg-type]


def test_healthy_target_is_weakened_first() -> None:
    decision = plan_capture(encounter(), POLICY)
    assert decision.directive is CaptureDirective.WEAKEN_TARGET
    assert "above 20% health" in decision.reason
    assert not decision.is_terminal


def test_weakened_target_without_status_gets_a_status_first() -> None:
    decision = plan_capture(encounter(target_hp=20), POLICY)
    assert decision.directive is CaptureDirective.INFLICT_STATUS
    assert "carries no status" in decision.reason


def test_weakened_and_statused_target_is_thrown_at() -> None:
    decision = plan_capture(
        encounter(target_hp=20, target_status=StatusCondition.SLEEP), POLICY
    )
    assert decision.directive is CaptureDirective.THROW_BALL
    assert "18% health" in decision.reason


def test_status_step_can_be_disabled() -> None:
    policy = CapturePolicy(prefer_status_first=False)
    decision = plan_capture(encounter(target_hp=20), policy)
    assert decision.directive is CaptureDirective.THROW_BALL


def test_threshold_is_inclusive_at_the_boundary() -> None:
    at_threshold = encounter(target_hp=22, target_max_hp=110)
    assert at_threshold.target_hp_ratio == pytest.approx(0.2)
    decision = plan_capture(at_threshold, CapturePolicy(prefer_status_first=False))
    assert decision.directive is CaptureDirective.THROW_BALL


@pytest.mark.parametrize(
    ("unsafe", "expected"),
    (
        ({"hp": 0}, "cannot safely continue"),
        ({"hp": 40}, "cannot safely continue"),
        ({"status": StatusCondition.POISON}, "cannot safely continue"),
        ({"moves": (MoveObservation(0x3D, 0, 20),)}, "cannot safely continue"),
    ),
)
def test_unsafe_catcher_is_restored_before_more_damage(
    unsafe: dict[str, object], expected: str
) -> None:
    decision = plan_capture(encounter(catcher=catcher(**unsafe)), POLICY)
    assert decision.directive is CaptureDirective.RESTORE_CATCHER
    assert expected in decision.reason


@pytest.mark.parametrize(
    ("changes", "expected"),
    (
        ({"target_hp": 0}, "target fainted"),
        ({"party_has_room": False}, "no open slot"),
        ({"balls_available": 0}, "no balls remain"),
        ({"throws_used": 20}, "throw budget"),
    ),
)
def test_terminal_conditions_abandon_the_attempt(
    changes: dict[str, object], expected: str
) -> None:
    decision = plan_capture(encounter(**changes), POLICY)
    assert decision.directive is CaptureDirective.ABANDON
    assert decision.is_terminal
    assert expected in decision.reason


def test_a_fainted_target_outranks_every_other_terminal_reason() -> None:
    decision = plan_capture(
        encounter(target_hp=0, party_has_room=False, balls_available=0), POLICY
    )
    assert "target fainted" in decision.reason


def test_ball_reserve_estimate_scales_the_throw_budget() -> None:
    assert balls_required_estimate(POLICY) == 40
    assert balls_required_estimate(CapturePolicy(max_throws=10), safety_factor=3) == 30
    with pytest.raises(ValueError, match="safety_factor"):
        balls_required_estimate(POLICY, safety_factor=0)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("throw_at_or_below_hp_ratio", 0.0),
        ("throw_at_or_below_hp_ratio", 1.0),
        ("retreat_hp_ratio", 1.0),
        ("max_throws", 0),
    ),
)
def test_policy_rejects_invalid_configuration(field: str, value: object) -> None:
    with pytest.raises(ValueError, match=field):
        CapturePolicy(**{field: value})  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("field", "value", "match"),
    (
        ("target_species_id", 0, "target_species_id"),
        ("target_level", 0, "target_level"),
        ("target_max_hp", 0, "target_max_hp"),
        ("target_hp", 999, "target_hp"),
        ("balls_available", -1, "balls_available"),
    ),
)
def test_observation_validates_its_encounter(field: str, value: object, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        encounter(**{field: value})


def test_observation_rejects_wrongly_typed_participants() -> None:
    with pytest.raises(TypeError, match="PartyMemberObservation"):
        encounter(catcher="blastoise")
    with pytest.raises(TypeError, match="StatusCondition"):
        encounter(target_status="asleep")
