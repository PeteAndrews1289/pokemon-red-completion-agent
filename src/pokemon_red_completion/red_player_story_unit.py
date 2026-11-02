"""Private native endpoint proof for one incremental story lesson.

The trusted teacher declares the selected binding's endpoint before input.
Map/event identities are verification evidence, never policy features. Success
credits that unit only; the enclosing quest still requires its ordinary proof.
No execution, memory writes, invented dependency gains or alternative labels.
"""

from collections.abc import Mapping

from .goal_manager import GoalKind
from .observation import EVENT_FLAG_BYTES, event_flag_is_set
from .red_player_economy import semantic_facts
from .red_player_lesson import validate_player_lesson, verify_player_lesson


def validate_story_unit_target(target):
    if not isinstance(target, Mapping) or target.get("kind") not in {"events", "arrival"}:
        raise ValueError("story unit target kind differs")
    events = target["kind"] == "events"
    if (
        set(target) != {"kind", "map_id", "events" if events else "at"}
        or type(target["map_id"]) is not int
        or not 0 <= target["map_id"] < 248
    ):
        raise ValueError("story unit native target differs")
    if events:
        flags = target["events"]
        if (
            not isinstance(flags, list)
            or not 1 <= len(flags) <= 8
            or any(type(e) is not int or not 0 <= e < EVENT_FLAG_BYTES * 8 for e in flags)
            or flags != sorted(set(flags))
        ):
            raise ValueError("story unit event target differs")
    elif target["at"] is not None:
        at = target["at"]
        if (
            not isinstance(at, list)
            or len(at) != 2
            or any(type(n) is not int or not 0 <= n <= 255 for n in at)
        ):
            raise ValueError("story unit arrival target differs")


def _validate_snapshot(target, snapshot):
    validate_story_unit_target(target)
    if (
        not isinstance(snapshot, Mapping)
        or set(snapshot) != {"map_id", "at", "events"}
        or type(snapshot["map_id"]) is not int
        or not 0 <= snapshot["map_id"] < 248
        or not isinstance(snapshot["at"], list)
        or len(snapshot["at"]) != 2
        or any(type(n) is not int or not 0 <= n <= 255 for n in snapshot["at"])
        or not isinstance(snapshot["events"], list)
        or len(snapshot["events"]) != len(target.get("events", []))
        or any(type(value) is not bool for value in snapshot["events"])
    ):
        raise ValueError("story unit native snapshot differs")


def capture_story_unit(runtime, target):
    """Observe the declared native fields through the existing read-only adapter."""
    validate_story_unit_target(target)
    frame = runtime.emulator.frame_count
    state = runtime.emulator.save_state_bytes()
    raw = runtime.reader.read()
    if target["kind"] == "events" and (
        not isinstance(raw.event_flags, bytes) or len(raw.event_flags) != EVENT_FLAG_BYTES
    ):
        raise ValueError("story unit event flags are unavailable")
    snapshot = dict(
        map_id=raw.map_id,
        at=[raw.player_y, raw.player_x],
        events=[event_flag_is_set(raw.event_flags, e) for e in target.get("events", [])],
    )
    _validate_snapshot(target, snapshot)
    if runtime.emulator.frame_count != frame or runtime.emulator.save_state_bytes() != state:
        raise ValueError("story unit observation changed native state")
    return snapshot


def _reached(target, snapshot):
    return snapshot["map_id"] == target["map_id"] and (
        all(snapshot["events"])
        if target["kind"] == "events"
        else target["at"] is None or snapshot["at"] == target["at"]
    )


def validate_story_unit_lesson(plan, kind):
    if kind is not GoalKind.ADVANCE_STORY:
        raise ValueError("story unit requires a story action")
    validate_player_lesson(plan["player_lesson"], plan["before"], kind)
    unit = plan["story_unit"]
    if not isinstance(unit, Mapping) or set(unit) != {"target", "before"}:
        raise ValueError("story unit declaration differs")
    target, before = unit["target"], unit["before"]
    _validate_snapshot(target, before)
    if all(before["events"]) if target["kind"] == "events" else _reached(target, before):
        raise ValueError("story unit target is already complete")


def verify_story_unit_lesson(plan, result, kind):
    validate_story_unit_lesson(plan, kind)
    # Preserve every old party/objective invariant, without claiming whole-quest success.
    verify_player_lesson(
        plan["player_lesson"], result["player_lesson"], plan["before"], result["after"], kind, False
    )
    target, before = plan["story_unit"]["target"], plan["story_unit"]["before"]
    after = result["story_unit"]
    _validate_snapshot(target, after)
    if any(old and not new for old, new in zip(before["events"], after["events"], strict=True)):
        raise ValueError("story unit lost a previously observed prerequisite")
    if type(result["succeeded"]) is not bool:
        raise ValueError("story unit success must be boolean")
    if result["succeeded"] and (
        result["player_lesson"]["in_battle"]
        or not semantic_facts(result["after"])["input_ready"]
        or not _reached(target, after)
    ):
        raise ValueError("story unit success lacks its settled native endpoint")
