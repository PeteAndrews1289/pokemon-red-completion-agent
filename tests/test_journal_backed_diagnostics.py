"""Flat and packed journals retain sealed event bytes without full in-memory copies.

Same records, same diagnostic-events.json bytes, same coverage summary; only the in-memory copy goes.
"""

import json
from enum import Enum, IntEnum

import pytest

from pokemon_red_completion import private_artifacts as private
from pokemon_red_completion.executor import NativeLessonController
from pokemon_red_completion.red_autonomous_player import _record
from pokemon_red_completion.red_player_lesson_runtime import (
    JournalBackedDiagnosticEvents,
    _diagnostic_coverage_row,
    _RecordedActions,
    summarize_player_diagnostic_events,
    write_streamed_player_diagnostic_journal,
)

PACKED = "packed_sealed_v1"
FLAT = "flat_sealed_v1"


def store_at(tmp_path, name, storage=PACKED):
    root = tmp_path / name
    root.mkdir(mode=0o700)
    options = dict(
        repository_root=tmp_path / "repository",
        device_id=lambda p: 2,
        git_worktree_probe=lambda p: False,
        allow_same_device=True,
    )
    options["repository_root"].mkdir(exist_ok=True)
    extra = {} if storage is None else {"native_input_storage": storage}
    return root, private.initialize_private_root(root, **options, **extra), options


class Emulator:
    pressed_buttons = frozenset()
    frame_count = 0

    def read_u8(self, address):
        return 0

    def save_state_bytes(self):
        return b"state"


class Ball(IntEnum):
    POKE = 4


class Outcome(str, Enum):
    CAUGHT = "caught"


def ledger(n):
    return dict(
        potential_consuming_dependencies=[
            dict(
                physical_reacquisition_n=i,
                physical_stock=i % 3,
                protected_stock=0,
                source_species="pokemon:national:%03d" % (i + 1),
                target_species="pokemon:national:%03d" % (i + 2),
                unprotected_stock=1,
            )
            for i in range(n)
        ]
    )


EVENTS = [
    ("player_boundary", dict(state=dict(collection_ledger=ledger(54), party_moves=[(33, 45), (10,)]))),
    ("capture_throw_started", dict(source="wild", conditions=dict(ball_id=Ball.POKE))),
    ("capture_throw_completed", dict(source="wild", conditions=dict(ball_id=Ball.POKE, hp=0.25),
                                     outcome=Outcome.CAUGHT, measured_cost=dict(frames=120, actions=3),
                                     state=dict(collection_ledger=ledger(5)))),
    ("capture_throw_completed", dict(source="gift", outcome="escaped")),
    ("survey_action_returned", dict(operation="seek_encounter",
                                    diagnostic_review=dict(measured=dict(eligible_search_steps=17, other=[1, 2]),
                                                           notes="x"),
                                    state=dict(collection_ledger=ledger(54)))),
    ("survey_action_failed", dict(operation="seek_encounter", diagnostic_review=dict(measured=dict(other=1)))),
    ("survey_action_returned", dict(operation="seek_encounter")),
    ("survey_action_returned", dict(operation="walk_to", diagnostic_review=dict(measured=dict(eligible_search_steps=9)))),
    ("fishing_cast_observed", dict(selected_target_seen=True, outcome="no_bite", rod="old")),
    ("fishing_cast_observed", dict(outcome="bite")),
    ("flee_verified", dict(state=dict(value=1.5, nested={"b": [None, True, False], "a": "z"}))),
]


def recorder_for(store):
    controller = NativeLessonController(Emulator(), maximum_frames=1000)
    recorder = _RecordedActions(controller, store, "d" * 64, 10)
    for kind, payload in EVENTS:
        recorder.record_diagnostic_event(kind, payload)
    return recorder


def materialized_bytes(tmp_path, events):
    path = tmp_path / "materialized.json"
    _record(path, dict(
        schema="pokemon.red.player-diagnostic-journal.v1",
        diagnostic_only=True,
        automatic_fit=False,
        events=events,
        coverage=summarize_player_diagnostic_events(events),
    ))
    return path.read_bytes()


@pytest.mark.parametrize("storage", [PACKED, FLAT])
def test_recorder_keeps_events_in_the_journal_only(tmp_path, storage):
    _, store, _ = store_at(tmp_path, "journal", storage=storage)
    _, legacy, _ = store_at(tmp_path, "legacy", storage=None)
    recorder, legacy_recorder = recorder_for(store), recorder_for(legacy)
    assert isinstance(recorder.diagnostic_events, JournalBackedDiagnosticEvents)
    assert isinstance(legacy_recorder.diagnostic_events, list)
    assert len(recorder.diagnostic_events) == len(legacy_recorder.diagnostic_events) == len(EVENTS)
    assert [json.dumps(r, sort_keys=True) for r in recorder.diagnostic_events] == [
        json.dumps(r, sort_keys=True) for r in legacy_recorder.diagnostic_events
    ]
    assert recorder.diagnostic_events.kinds() == tuple(k for k, _ in EVENTS)
    assert recorder.diagnostic_events[2]["payload"]["outcome"] == "caught"
    assert [r["ordinal"] for r in recorder.diagnostic_events[1:3]] == [1, 2]
    assert all("state" not in r["payload"] for r in recorder.diagnostic_events.coverage_rows())

@pytest.mark.parametrize("storage", [PACKED, FLAT])
def test_coverage_summary_is_identical(tmp_path, storage):
    _, packed, _ = store_at(tmp_path, "journal", storage=storage)
    recorder = recorder_for(packed)
    full = list(recorder.diagnostic_events)
    assert summarize_player_diagnostic_events(recorder.diagnostic_events.coverage_rows()) == (
        summarize_player_diagnostic_events(full)
    )
    summary = summarize_player_diagnostic_events(full)
    assert summary["capture"]["completed"] == 2 and summary["search"]["known_tile_exposure"] == 17
    assert summary["fishing"] == dict(observed_casts=2, selected_target_sightings=1, no_bites=1)


@pytest.mark.parametrize("storage", [PACKED, FLAT])
def test_streamed_journal_bytes_equal_the_ordinary_writer(tmp_path, storage):
    _, packed, _ = store_at(tmp_path, "journal", storage=storage)
    recorder = recorder_for(packed)
    expected = materialized_bytes(tmp_path, list(recorder.diagnostic_events))
    path = tmp_path / "streamed.json"
    write_streamed_player_diagnostic_journal(path, recorder.diagnostic_events)
    assert path.read_bytes() == expected
    with pytest.raises(FileExistsError):
        write_streamed_player_diagnostic_journal(path, recorder.diagnostic_events)


@pytest.mark.parametrize("storage", [PACKED, FLAT])
def test_streamed_journal_with_no_events(tmp_path, storage):
    _, packed, _ = store_at(tmp_path, "journal", storage=storage)
    events = JournalBackedDiagnosticEvents(packed)
    path = tmp_path / "empty.json"
    write_streamed_player_diagnostic_journal(path, events)
    assert path.read_bytes() == materialized_bytes(tmp_path, [])


@pytest.mark.parametrize("storage", [PACKED, FLAT])
def test_recorder_memory_holds_only_summary_fields(tmp_path, storage):
    _, packed, _ = store_at(tmp_path, "journal", storage=storage)
    recorder = recorder_for(packed)
    full = sum(len(json.dumps(r)) for r in recorder.diagnostic_events)
    kept = sum(len(json.dumps(r)) for r in recorder.diagnostic_events.coverage_rows())
    # The 54-entry ledgers stay in the journal; memory keeps a few small fields per event.
    assert full > 20000 and kept < 2000


def test_coverage_row_matches_summary_lookups_on_odd_shapes():
    odd = [
        dict(kind="capture_throw_completed", ordinal=0, payload=dict(conditions={})),
        dict(kind="capture_throw_completed", ordinal=1, payload={}),
        dict(kind="survey_action_returned", ordinal=2, payload=dict(operation="seek_encounter", diagnostic_review={})),
        dict(kind="survey_action_failed", ordinal=3, payload=dict(diagnostic_review=dict(measured={}))),
        dict(kind="other", ordinal=4, payload=dict(state=[1])),
    ]
    assert summarize_player_diagnostic_events([_diagnostic_coverage_row(r) for r in odd]) == (
        summarize_player_diagnostic_events(odd)
    )


@pytest.mark.parametrize("storage", [PACKED, FLAT])
def test_missing_journal_record_fails_closed(tmp_path, storage):
    _, packed, _ = store_at(tmp_path, "journal", storage=storage)
    events = JournalBackedDiagnosticEvents(packed)
    events.append_sealed("rnp-diagnostic-" + "0" * 64, dict(kind="x", ordinal=0, payload={}))
    with pytest.raises(RuntimeError, match="missing"):
        list(events)


@pytest.mark.parametrize("storage", [PACKED, FLAT, None])
def test_storage_capability_keeps_original_press_and_action_counters(tmp_path, storage):
    _, store, _ = store_at(tmp_path, "journal", storage=storage)
    recorder = recorder_for(store)
    assert store.supports_journal_backed_diagnostics is (storage is not None)
    assert recorder.observe_presses is (storage == PACKED)
    assert recorder.press_observations == 0
    assert recorder.trace == []
    assert recorder.controller.frames_executed == 0
    assert recorder.enabled is False
    assert recorder.diagnostic_journal_seconds >= 0
    assert [r["ordinal"] for r in recorder.diagnostic_events] == list(range(len(EVENTS)))
    assert all(r["action_ordinal"] == 0 and r["frame"] == 0 for r in recorder.diagnostic_events)


def test_flat_events_reopen_through_verified_sealed_storage(tmp_path):
    root, store, options = store_at(tmp_path, "flat", storage=FLAT)
    recorder = recorder_for(store)
    expected = list(recorder.diagnostic_events)
    reopened = private.open_private_root(root, **options, native_input_storage=FLAT)
    events = JournalBackedDiagnosticEvents(reopened)
    for record_id, row in zip(recorder.diagnostic_events._ids, expected):
        events.append_sealed(record_id, row)
    assert list(events) == expected
    assert events[-1] == expected[-1]
    assert summarize_player_diagnostic_events(events.coverage_rows()) == summarize_player_diagnostic_events(expected)
    path = tmp_path / "reopened-streamed.json"
    write_streamed_player_diagnostic_journal(path, events)
    assert path.read_bytes() == materialized_bytes(tmp_path, expected)


def test_flat_lazy_read_rejects_changed_sealed_bytes(tmp_path):
    root, store, _ = store_at(tmp_path, "flat", storage=FLAT)
    recorder = recorder_for(store)
    record_id = recorder.diagnostic_events._ids[0]
    record_path = root / (record_id + ".sealed.jsonl")
    data = record_path.read_bytes()
    assert b"player_boundary" in data
    record_path.write_bytes(data.replace(b"player_boundary", b"player_boundarx", 1))
    with pytest.raises(private.PrivateArtifactError):
        recorder.diagnostic_events[0]


def test_legacy_store_without_capability_retains_list_compatibility(tmp_path):
    _, legacy, _ = store_at(tmp_path, "legacy", storage=None)
    class LegacyStore:
        records_press_observations = False
        def publish_sealed_record(self, *args, **kwargs):
            return legacy.publish_sealed_record(*args, **kwargs)
    recorder = recorder_for(LegacyStore())
    assert isinstance(recorder.diagnostic_events, list)
    assert len(recorder.diagnostic_events) == len(EVENTS)
