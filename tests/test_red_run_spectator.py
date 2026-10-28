"""Spectator data, lifecycle, privacy and streaming checks; no ROM or save."""

import json
import urllib.error
import urllib.request

import pytest

from pokemon_red_completion.progress_dashboard import (
    DashboardState,
    ProgressDashboardError,
    ProgressDashboardServer,
    encode_rgb_png,
)
from pokemon_red_completion.red_run_spectator import (
    _NAMES,
    RedRunReader,
    RunViewerState,
    worker_is_running,
)
from pokemon_red_completion.red_spectator_feed import RunFrameFeed, declared_spectator


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2))


@pytest.fixture
def run(tmp_path):
    root = tmp_path / "ui-verification-run"
    root.mkdir()
    write(root / "PLAN.json", dict(required_species=["x"] * 124, fit_allowed=False))
    write(
        root / "LAUNCH.json",
        dict(
            worker_pid=123,
            command=["python", "driver.py", "--plan", str(root / "PLAN.json")],
            started_at_utc="2026-10-14T19:47:51+00:00",
        ),
    )
    segment = root / "runs/segment-001"
    write(
        segment / "CONTEXT.json",
        dict(
            spent=dict(decisions=3, actions=80, frames=600),
            lesson=dict(completed_objectives=["defeat_brock"]),
        ),
    )
    write(
        segment / "native/episode/result.json",
        dict(
            executed_decisions=3,
            model_decisions=2,
            support_decisions=1,
            ordinary_setbacks=1,
            outcomes=[],
        ),
    )
    step = segment / "native/episode/step-002"
    facts = dict(
        cash=131,
        input_ready=True,
        completed_objectives=["defeat_brock"],
        diagnostics=dict(
            map_id=33,
            badge_bits=1,
            party_species_ids=[179],
            party_levels=[16],
            party_hp=[47],
            party_max_hp=[47],
            party_status=[0],
            bag_items=[[4, 7]],
            collection_ledger=dict(local_registered_species=["x"] * 10),
        ),
    )
    write(step / "before.json", dict(facts=facts))
    write(step / "decision.json", dict(mode="model_exploration", selected_option_kind="acquire"))
    write(
        step / "outcome.json",
        dict(
            after=facts,
            selected_kind="acquire_species",
            ordinary_setback=True,
            verification="failed",
            elapsed_seconds=2.5,
            observed_cost=dict(actions=5),
        ),
    )
    write(
        step / "admission-failure.json",
        dict(error="second rival unavailable, consumed or ambiguous"),
    )
    write(
        root / "RESULT.json",
        dict(
            worker_stopped=True,
            passed=False,
            terminal_reason="menu_unavailable",
            native_facts=dict(
                badges=1,
                badge_bits=1,
                cash=131,
                registrations=10,
                party_levels=[16],
                bag_stock=[[4, 7]],
            ),
            spent=dict(decisions=3, actions=80, frames=600),
        ),
    )
    write(
        root / "PROCESS-EXIT.json",
        dict(worker_exit_confirmed=True, exited_at_utc="2026-10-14T20:07:52+00:00"),
    )
    return root


def test_retained_run_is_stopped_and_exactly_projected_without_writes(run):
    before = {p: p.read_bytes() for p in run.rglob("*") if p.is_file()}
    snapshot, meta = RedRunReader(run).read()
    assert snapshot.run_status == "failed"
    assert snapshot.location == "Route 22" and snapshot.registered_species == 10
    assert snapshot.party[0].label == "Wartortle" and snapshot.party[0].hp == 47
    assert (meta["model_decisions"], meta["support_decisions"], meta["ordinary_setbacks"]) == (
        2,
        1,
        1,
    )
    assert meta["badges"] == 1 and meta["money"] == 131 and meta["balls"] == 7
    assert meta["elapsed_seconds"] == 1201 and meta["lifecycle"] == "stopped"
    assert meta["recent"][-1]["result"] == "Safe setback"
    assert "second rival" in meta["failure"] and meta["weights_updated"] == 0
    assert before == {p: p.read_bytes() for p in run.rglob("*") if p.is_file()}


def test_missing_party_fields_stay_unknown_not_invented(run):
    path = run / "runs/segment-001/native/episode/step-002"
    write(path / "before.json", dict(facts=dict(diagnostics={})))
    (path / "outcome.json").unlink()
    snapshot, _ = RedRunReader(run).read()
    assert snapshot.party == ()


def test_partial_json_preserves_last_parsed_observation(run):
    reader = RedRunReader(run)
    snapshot, meta = reader.read()
    (run / "RESULT.json").write_text("{")
    again, new_meta = reader.read()
    assert again.registered_species == snapshot.registered_species
    assert new_meta["lifecycle"] == "stopped" and new_meta["money"] == meta["money"]


def test_no_authenticated_worker_is_not_live(run):
    (run / "RESULT.json").unlink()
    (run / "PROCESS-EXIT.json").unlink()
    reader = RedRunReader(run, process_probe=lambda *args: False)
    snapshot, meta = reader.read()
    assert snapshot.run_status == "waiting" and meta["lifecycle"] == "not_connected"
    reader.process_probe = lambda *args: True
    snapshot, meta = reader.read()
    assert snapshot.run_status == "running" and meta["lifecycle"] == "running"


def test_worker_claim_requires_command_not_pid_only(run, monkeypatch):
    from types import SimpleNamespace

    import pokemon_red_completion.red_run_spectator as module

    launch = json.loads((run / "LAUNCH.json").read_text())
    monkeypatch.setattr(
        module.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout="python unrelated.py")
    )
    assert not worker_is_running(launch, run)
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(stdout=f"python driver.py --plan {run / 'PLAN.json'}"),
    )
    assert worker_is_running(launch, run)


def test_count_reader_skips_huge_payload_and_nested_decoys(run):
    path = run / "runs/segment-001/native/episode/result.json"
    path.write_text(
        '{\n  "executed_decisions": 3,\n  "model_decisions": 2,\n'
        '  "ordinary_setbacks": 1,\n  "outcomes": [{"model_decisions": 999, "padding": "'
        + "x" * 20_000_000
        + '"}],\n  "support_decisions": 1\n}'
    )
    reader = RedRunReader(run)
    assert reader.segment_counts(path)["model_decisions"] == 2
    assert reader.read()[1]["model_decisions"] == 2


def test_counter_accounting_mismatch_is_not_admitted(run):
    path = run / "runs/segment-001/native/episode/result.json"
    write(
        path,
        dict(executed_decisions=3, model_decisions=99, support_decisions=1, ordinary_setbacks=1),
    )
    reader = RedRunReader(run)
    assert reader.segment_counts(path) == {}
    assert reader.read()[1]["counts_observed"] is False


def test_unfinished_counter_receipt_retains_only_labeled_partial_totals(run):
    reader = RedRunReader(run)
    assert reader.read()[1]["counts_observed"] is True
    (run / "runs/segment-001/native/episode/result.json").write_text("{")
    _, meta = reader.read()
    assert meta["model_decisions"] == 2
    assert meta["counts_observed"] is False


def test_missing_resources_are_unknown_not_zero(run):
    (run / "RESULT.json").unlink()
    (run / "PROCESS-EXIT.json").unlink()
    path = run / "runs/segment-001/native/episode/step-002"
    write(path / "before.json", dict(facts=dict(diagnostics={})))
    (path / "outcome.json").unlink()
    _, meta = RedRunReader(run, process_probe=lambda *args: False).read()
    assert meta["money"] is None and meta["balls"] is None


def test_latest_context_avoids_historical_cache_churn_and_filters_private_text(run):
    reader = RedRunReader(run)
    for n in range(2, 180):
        segment = run / f"runs/segment-{n:03}"
        write(
            segment / "CONTEXT.json",
            dict(lesson=dict(completed_objectives=["defeat_brock", "/Volumes/Private/secret"])),
        )
        write(
            segment / "native/episode/result.json",
            dict(executed_decisions=1, model_decisions=1, support_decisions=0, ordinary_setbacks=0),
        )
    _, meta = reader.read()
    assert meta["completed_objectives"] == ["defeat_brock"]
    contexts = [path for path in reader._cache if path.name == "CONTEXT.json"]
    assert len(contexts) <= 2


def test_private_text_and_external_symlink_are_not_exposed(run, tmp_path):
    error = run / "runs/segment-001/native/episode/step-002/admission-failure.json"
    write(error, dict(error="failed at /Volumes/Private/data/secret or 0xcafe"))
    snapshot, meta = RedRunReader(run).read()
    assert "/Volumes" not in json.dumps(meta) + json.dumps(snapshot.public_dict())
    external = tmp_path / "private.json"
    write(external, dict(secret="do not read"))
    link = run / "linked.json"
    link.symlink_to(external)
    assert RedRunReader(run).document(link) == {}


def test_species_display_catalog_has_all_151_entries():
    assert len(_NAMES) == 151 and _NAMES[7] == "Wartortle" and _NAMES[-1] == "Mew"


@pytest.mark.parametrize(
    "spec",
    [
        True,
        {},
        {"port": 80, "maximum_fps": 4},
        {"port": 8769, "maximum_fps": 0},
        {"port": 8769, "maximum_fps": True},
        {"port": True, "maximum_fps": 4},
        {"port": 8769, "maximum_fps": 4, "host": "0.0.0.0"},
    ],
)
def test_spectator_rejects_invalid_or_remote_settings(spec):
    with pytest.raises(ValueError):
        declared_spectator(dict(spectator=spec))


def test_disabled_feed_is_exact_noop_without_run_directory(tmp_path):
    with RunFrameFeed({}, tmp_path / "absent") as feed:
        assert feed.adapter_options == {} and feed._server is None


def test_inspection_disables_even_a_valid_declared_feed(tmp_path):
    spec = dict(spectator=dict(port=8769, maximum_fps=4))
    with RunFrameFeed(spec, tmp_path / "absent", enabled=False) as feed:
        assert feed.adapter_options == {} and feed._server is None


def test_enabled_feed_streams_pixels_and_readonly_status(run):
    # Synthetic UI test only: no emulator/controller/save loader involved.
    with ProgressDashboardServer(DashboardState(), port=0) as spare:
        port = spare._server.server_address[1]
    with RunFrameFeed(dict(spectator=dict(port=port, maximum_fps=4)), run) as feed:
        observer = feed.adapter_options["frame_observer"]
        observer.publish_frame(1, 1, bytes((10, 20, 30)), 12)
        origin = f"http://127.0.0.1:{port}"
        with urllib.request.urlopen(origin + "/api/status") as response:
            data = json.load(response)
        assert data["run"]["id"] == run.name and data["controller_endpoints"] == 0
        with urllib.request.urlopen(origin + "/frame.png") as response:
            assert response.read().startswith(b"\x89PNG")
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(urllib.request.Request(origin + "/launch", data=b"{}"))
        assert error.value.code == 405


def test_port_collision_does_not_interrupt_player_or_attach_observer(run):
    with ProgressDashboardServer(DashboardState(), port=0) as occupied:
        spec = dict(spectator=dict(port=occupied._server.server_address[1], maximum_fps=4))
        with RunFrameFeed(spec, run) as feed:
            assert feed.adapter_options == {} and feed._server is None


def test_other_run_rejected_and_matching_last_frame_retained(run, monkeypatch):
    state = RunViewerState(RedRunReader(run), live_port=8769)
    snapshot, meta = state.reader.read()
    producer = DashboardState(snapshot)
    png = encode_rgb_png(1, 1, bytes((3, 5, 7)))
    producer.publish_png(png, logical_frame=123)
    data = json.loads(producer.status_bytes()[0])
    data["run"] = meta | {"id": "another-run"}

    def get(endpoint):
        return json.dumps(data).encode() if endpoint == "/api/status" else png

    monkeypatch.setattr(
        "pokemon_red_completion.dashboard_relay.DashboardRelayState._get",
        lambda _, x: get(x),
    )
    assert not state.poll()
    assert not json.loads(state.status_bytes()[0])["dashboard"]["frame_ready"]
    data["run"]["id"] = run.name
    assert state.poll() and state.frame_bytes()[0] == png

    def fail(endpoint):
        raise OSError("producer stopped")

    monkeypatch.setattr(
        "pokemon_red_completion.dashboard_relay.DashboardRelayState._get",
        lambda _, x: fail(x),
    )
    assert not state.poll() and state.frame_bytes()[0] == png
    status = json.loads(state.status_bytes()[0])
    assert status["run"]["frame_source_connected"] is False
    assert status["run"]["lifecycle"] == "stopped"


def test_watch_page_has_display_controls_only_and_rejects_writes(run):
    with ProgressDashboardServer(
        RunViewerState(RedRunReader(run), live_port=8769), port=0
    ) as server:
        with urllib.request.urlopen(server.url + "watch") as response:
            html = response.read().decode()
        assert "Recent decisions" in html and "LAST RECORDED BOUNDARY" in html
        assert "requestFullscreen" in html and "No game controls" in html
        assert "method:'POST'" not in html
        for endpoint in ("launch", "resume", "reset", "input", "../PLAN.json"):
            with pytest.raises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(urllib.request.Request(server.url + endpoint, data=b"{}"))
            assert error.value.code == 405
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(server.url + "PLAN.json")
        assert error.value.code == 404


def test_server_cannot_bind_network_interface():
    with pytest.raises(ProgressDashboardError):
        ProgressDashboardServer(DashboardState(), host="0.0.0.0", port=0)
