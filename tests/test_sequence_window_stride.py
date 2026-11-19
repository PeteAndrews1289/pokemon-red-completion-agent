"""Prospective overlapping windows preserve ownership/costs and old schedules."""
import json
from hashlib import sha256
import pytest
import test_player_sequence_collector as fixtures
from test_player_sequence_reconstruction import args
from test_task_terminal_sequence import collect_task
from pokemon_red_completion.player_sequence_collector import SequenceTraceCollector
from pokemon_red_completion.player_sequence_reconstruction import reconstruct_sequence_candidates
from pokemon_red_completion.player_sequence_targets import sequence_targets, SEQUENCE_TARGET_NAMES
from pokemon_red_completion.red_sequence_verified_targets import verify_sequence_target_channels


def collect_stride(tmp_path, monkeypatch, *, horizon=2, stride=1, **kw):
    constructor = fixtures.SequenceTraceCollector
    monkeypatch.setattr(fixtures, "SequenceTraceCollector", lambda **options: constructor(**options, window_stride=stride))
    return fixtures.collect(tmp_path, monkeypatch, horizon=horizon, **kw)


@pytest.mark.parametrize("bad", [0, -1, 3, True, False, 1.0, "1"])
def test_stride_requires_explicit_bounded_integer(bad):
    with pytest.raises(ValueError, match="stride"):
        SequenceTraceCollector(source_sha256="a"*64, partition="train", horizon=2, window_stride=bad)


def test_overlapping_windows_keep_support_cost_and_unknown_tail(tmp_path, monkeypatch):
    root, collector = collect_stride(tmp_path, monkeypatch, partition="train")
    read = lambda p: json.loads(p.read_bytes())
    declaration = read(root/"sequence/declaration.json")
    assert declaration["schema"] == "pokemon.player.sequence-collection.v4"
    assert declaration["window_stride"] == 1
    windows = [read(p) for p in sorted((root/"sequence").glob("window-*.json"))]
    assert [w["first_model_choice"] for w in windows] == [0, 1]
    assert [w["measurement"]["actions"] for w in windows] == [3, 1]
    assert [w["measurement"]["cash_debits"] for w in windows] == [60, 20]
    rows = reconstruct_sequence_candidates(root, **args(root, "train"))
    assert rows[0].measurement.complete_window
    assert not rows[1].measurement.complete_window
    assert all(not r.training_eligible for r in rows)
    targets = [sequence_targets(r.measurement, covered=frozenset(SEQUENCE_TARGET_NAMES)) for r in rows]
    assert all(v is not None for v in targets[0].values)
    assert all(v is None for v in targets[1].values)
    assert collector.finished
    # Shared costs are present in both examples; never sum these as run costs.
    assert sum(r.measurement.actions for r in rows) == 4
    assert read(root/"result.json")["executed_decisions"] == 3


def test_explicit_default_stride_keeps_legacy_declaration(tmp_path, monkeypatch):
    root, _ = collect_stride(tmp_path, monkeypatch, stride=2)
    d = json.loads((root/"sequence/declaration.json").read_bytes())
    assert d["schema"] == "pokemon.player.sequence-collection.v1"
    assert "window_stride" not in d
    assert d["windows"] == "nonoverlapping-model-choices-with-attached-support"
    rows = reconstruct_sequence_candidates(root, **args(root))
    assert len(rows) == 1 and rows[0].measurement.actions == 3


@pytest.mark.parametrize("bad", [0, 2, True, "1"])
def test_changed_stride_cannot_reinterpret_retained_windows(tmp_path, monkeypatch, bad):
    root, _ = collect_stride(tmp_path, monkeypatch)
    pinned = args(root)
    p = root/"sequence/declaration.json"
    d = json.loads(p.read_bytes()); d["window_stride"] = bad
    p.write_text(json.dumps(d))
    with pytest.raises(ValueError, match="declaration"):
        reconstruct_sequence_candidates(root, **pinned)
    with pytest.raises(ValueError, match="declaration"):
        reconstruct_sequence_candidates(root, **args(root))


def test_overlapping_task_terminal_short_window_uses_verified_native_predicate(tmp_path, monkeypatch):
    original = SequenceTraceCollector.__init__
    def init(self, **kw):
        kw["window_stride"] = 1
        original(self, **kw)
    monkeypatch.setattr(SequenceTraceCollector, "__init__", init)
    root, audit_args, executed = collect_task(tmp_path, monkeypatch)
    [row] = verify_sequence_target_channels(root, **audit_args)
    assert executed == [2]
    assert not row.measurement.complete_window and row.measurement.complete_observation
    assert row.targets.values[0] == .5
    assert row.targets.values[6] is None
    assert not row.training_eligible
    declaration = json.loads((root/"episode/sequence/declaration.json").read_bytes())
    assert declaration["window_stride"] == 1


@pytest.mark.parametrize("fault", ["partial", "verdict"])
def test_overlapping_failed_projection_keeps_failure_costs(tmp_path, monkeypatch, fault):
    root, _ = collect_stride(tmp_path, monkeypatch, fault=fault)
    report = json.loads((root/"sequence/result.json").read_bytes())
    assert report["projection_error"] is not None
    assert report["unprojected_observed_costs"][0]["actions"] == 1
    assert not report["training_eligible"]


def test_public_native_stride_argument_reaches_prospective_task_declaration(tmp_path, monkeypatch):
    from pokemon_red_completion import red_native_player as native
    original = native.run_native_continuous_player
    def run(**kw):
        return original(**kw, sequence_window_stride=1)
    monkeypatch.setattr(native, "run_native_continuous_player", run)
    root, audit_args, executed = collect_task(tmp_path, monkeypatch)
    [row] = verify_sequence_target_channels(root, **audit_args)
    assert executed == [2] and row.measurement.complete_observation
    declaration = json.loads((root/"episode/sequence/declaration.json").read_bytes())
    assert declaration["window_stride"] == 1


def test_public_native_stride_without_horizon_is_refused_before_input(tmp_path, monkeypatch):
    from test_red_native_player import setup
    from pokemon_red_completion import red_native_player as native
    kw, executed = setup(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="stride"):
        native.run_native_continuous_player(**kw, sequence_window_stride=1)
    assert executed == []
