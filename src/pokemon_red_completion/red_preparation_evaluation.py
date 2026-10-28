"""Evaluation-only outcome verification; deliberately no TRAIN example constructor."""

from .goal_manager import GoalKind
from .provenance import canonical_sha256
from .red_player_evolution_lesson import verify_evolution_lesson_boundary
from .red_player_story_unit import _reached, _validate_snapshot


def evaluate_preparation_phases(source, before, phases, *, target, evolution_contract):
    """Verify an independently recorded bounded preparation/challenge sequence."""
    if (source.get("partition") != "development" or not 1 <= len(phases) <= 4
        or before["state_sha256"] != source["state_sha256"]
        or any(before[k] != 0 for k in ("actions", "completed_actions", "frames", "heals"))):
        raise ValueError("evaluation needs a prospective DEVELOPMENT source")
    _validate_snapshot(target, before["endpoint"])
    if all(before["endpoint"]["events"]):
        raise ValueError("evaluation challenge was already complete")
    previous = before
    debits = credits = 0
    attempted = completed = False
    for i, phase in enumerate(phases):
        kind = GoalKind(phase["kind"])
        if (phase["ordinal"] != i or canonical_sha256(phase["before"]) != canonical_sha256(previous)
            or attempted or phase["interventions"] or not phase["cost_verified"]
            or phase["error"] is not None
            or kind not in {GoalKind.DEVELOP_TEAM, GoalKind.RESTORE_TEAM, GoalKind.ADVANCE_STORY}
            or i > 0 and kind is GoalKind.DEVELOP_TEAM):
            raise ValueError("evaluation phase order, cost or execution differs")
        after = phase["after"]
        if (any(after[k] < previous[k] for k in ("actions", "completed_actions", "frames", "heals"))
            or after["actions"] != after["completed_actions"] or not after["settled"]):
            raise ValueError("evaluation requires complete settled measured actions")
        verify_evolution_lesson_boundary(previous["lesson"], after["lesson"],
            previous["observation"], after["observation"], kind, evolution_contract)
        _validate_snapshot(target, after["endpoint"])
        reached = _reached(target, after["endpoint"])
        if kind is GoalKind.ADVANCE_STORY:
            attempted = True
            completed = phase["verified"] is True and phase["battle"] == "won" and reached
            if not completed and not (
                phase["verified"] is False and phase["battle"] == "lost" and not reached
            ):
                raise ValueError("evaluation challenge result lacks native endpoint")
        elif reached or phase["verified"] is not True and i != len(phases) - 1:
            raise ValueError("evaluation cannot continue after failed preparation")
        debits += max(0, previous["cash"] - after["cash"])
        credits += max(0, after["cash"] - previous["cash"])
        previous = after
    return dict(schema="pokemon.red.preparation-evaluation.v1", partition="development",
        fit_allowed=False, attempted=attempted, completed=completed,
        actions=previous["actions"], frames=previous["frames"], heals=previous["heals"],
        cash_debits=debits, cash_credits=credits, terminal_sha256=previous["state_sha256"])
