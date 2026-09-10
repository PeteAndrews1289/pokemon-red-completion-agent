import pytest
from summarize_red_search_trace import summarize_trace


def fixture():
    def state(identity, x, battle=None):
        return {
            "snapshot_sha256": identity,
            "snapshot": {
                "features": {
                    "battle": battle,
                    "world": {"area_ref": "grass", "position": {"x": x, "y": 2}},
                }
            },
        }

    return [state("a", 1), state("b", 2), state("c", 2, {"kind": "wild"})]


def step(before, after, kind="move", frames=12):
    return {
        "before_sha256": before,
        "after_sha256": after,
        "action": {"kind": kind},
        "frames": frames,
    }


def test_repeated_identical_encounters_are_counted_from_transitions():
    result = summarize_trace(
        fixture(),
        [
            step("a", "b"),
            step("b", "c"),
            step("c", "b", "cancel"),
            step("b", "c"),
            step("c", "b", "cancel"),
        ],
    )
    assert result["recorded_actions"] == 5 and result["recorded_frames"] == 60
    assert result["wild_encounter_starts"] == result["wild_battle_ends"] == 2
    assert result["overworld_movement_inputs"] == 3
    assert result["overworld_movements_with_displacement"] == 1
    assert result["controller_actions"] == result["model_queries"] == result["model_fits"] == 0


@pytest.mark.parametrize(
    "rows,message",
    [
        ([step("a", "missing")], "missing snapshot"),
        ([step("a", "b"), step("a", "c")], "continuity"),
        ([step("a", "b", frames=True)], "frame cost"),
    ],
)
def test_unjoinable_or_invalid_cost_cannot_become_a_diagnostic(rows, message):
    with pytest.raises(ValueError, match=message):
        summarize_trace(fixture(), rows)


def test_unknown_position_is_not_a_collision_or_success():
    states = fixture()
    states[1]["snapshot"]["features"]["world"]["position"] = None
    result = summarize_trace(states, [step("a", "b")])
    assert result["movement_inputs_missing_position"] == 1
    assert result["overworld_movements_with_displacement"] == 0


def test_duplicate_snapshot_is_rejected():
    states = fixture()
    with pytest.raises(ValueError, match="duplicated"):
        summarize_trace([*states, states[0]], [])
