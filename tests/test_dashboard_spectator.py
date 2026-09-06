from __future__ import annotations

import copy
import json
import runpy
from dataclasses import replace
from html.parser import HTMLParser
from pathlib import Path

import pytest

from pokemon_red_completion.dashboard_relay import (
    DashboardRelayState,
    snapshot_from_public_status,
)
from pokemon_red_completion.progress_dashboard import (
    _DASHBOARD_HTML,
    DashboardSnapshot,
    DashboardState,
    DashboardWorkState,
    ProgressDashboardError,
    ProgressDashboardServer,
    encode_rgb_png,
)

ROOT = Path(__file__).resolve().parents[1]
OVERVIEW = runpy.run_path(str(ROOT / "scripts/run_product_focus_dashboard.py"))


def _snapshot() -> DashboardSnapshot:
    return DashboardSnapshot(
        game="Pokémon Red",
        run_status="running",
        stage="Acquisition",
        message="A supported collection objective is executing.",
        registered_species=4,
        living_species=3,
        collection_target=151,
    )


def _status() -> dict:
    state = DashboardState(_snapshot())
    state.publish_png(encode_rgb_png(1, 1, bytes((5, 7, 9))), logical_frame=21)
    return json.loads(state.status_bytes()[0])


def test_frame_freshness_tracks_frames_not_work_updates() -> None:
    now = [100.0]
    state = DashboardState(_snapshot(), clock=lambda: now[0])
    assert json.loads(state.status_bytes()[0])["dashboard"]["frame_age_seconds"] is None
    state.publish_png(encode_rgb_png(1, 1, bytes((0, 0, 0))), logical_frame=12)
    now[0] += 8
    state.publish(replace(_snapshot(), stage="Work update"))
    metadata = json.loads(state.status_bytes()[0])["dashboard"]
    assert metadata["snapshot_age_seconds"] == 0
    assert metadata["frame_age_seconds"] == 8
    state.publish_png(encode_rgb_png(1, 1, bytes((1, 1, 1))), logical_frame=13)
    assert json.loads(state.status_bytes()[0])["dashboard"]["frame_age_seconds"] == 0


def test_completed_training_evidence_is_derived_and_explicitly_not_held_out() -> None:
    receipt = OVERVIEW["_load_learning_evidence"]()
    training, component = OVERVIEW["_training_projection"](receipt)
    assert training.samples_after == 29
    assert training.samples_before + training.previously_unfitted + training.newly_collected == 29
    assert training.weighted_mse_after == pytest.approx(0.005004556974872811)
    assert training.public_dict()["held_out_claim"] is False
    assert component.train_examples == 29
    assert component.validation_examples == 0
    assert component.authority == "shadow_only"

    changed = copy.deepcopy(receipt)
    changed["fit_result"]["model"]["total_examples"] = 31
    changed["fit_result"]["model"]["settled_examples"] = 31
    projection, candidate = OVERVIEW["_training_projection"](changed)
    assert candidate.train_examples == 31
    assert projection.samples_before == 20


def test_saved_run_recap_uses_actual_choices_resources_and_denominator() -> None:
    recap = OVERVIEW["_load_run_recap"]()
    assert [step.goal for step in recap.steps] == [
        "resupply", "acquire_species", "acquire_species", "resupply",
    ]
    assert [step.authority for step in recap.steps] == [
        "safety", "unsupported", "model", "model",
    ]
    assert (recap.living_before, recap.living_after) == (13, 14)
    assert (recap.money_before, recap.money_after) == (12649, 649)
    assert (recap.capture_items_before, recap.capture_items_after) == (1, 19)
    assert (recap.controller_actions, recap.emulator_frames) == (656, 40368)
    assert sum(step.needed_specimens_gained for step in recap.steps) == 2
    assert (recap.control_successes, recap.control_decisions, recap.control_failed) == (3, 4, True)
    assert recap.public_dict()["live"] is False
    assert recap.public_dict()["training_data"] is False
    assert recap.public_dict()["independent_generalization_claim"] is False


def test_recap_never_makes_a_live_frame_or_overwrites_current_collection() -> None:
    recap = OVERVIEW["_load_run_recap"]()
    state = DashboardState(replace(_snapshot(), last_run=recap, collection_observed=False))
    status = json.loads(state.status_bytes()[0])
    assert status["dashboard"]["frame_ready"] is False
    assert status["dashboard"]["frame_age_seconds"] is None
    assert status["collection"]["observed"] is False
    assert status["last_run"]["living_after"] == 14
    assert snapshot_from_public_status(status).last_run == recap
    status["last_run"]["live"] = True
    with pytest.raises(ProgressDashboardError, match="claim boundary"):
        snapshot_from_public_status(status)


@pytest.mark.parametrize("change", ["source", "arm", "action", "decision", "fit", "scope"])
def test_saved_recap_rejects_broken_receipt_joins(change: str) -> None:
    result_path = ROOT / "docs/evidence/red-fit29-resource-chain-result-2026-09-06.json"
    audit_path = ROOT / "docs/evidence/red-fit29-resource-chain-readonly-audit-2026-09-06.json"
    result, audit = json.loads(result_path.read_text()), json.loads(audit_path.read_text())
    if change == "source":
        audit["source_commit"] = "0" * 40
    elif change == "arm":
        audit["arms"][0]["manifest_sha256"] = "0" * 64
    elif change == "action":
        result["learned"]["episode"]["steps"][0]["actions_executed"] += 1
    elif change == "decision":
        result["living_dex_causal_shadow"]["decisions"][0]["selected_kind"] = "explore"
    elif change == "fit":
        audit["new_train_examples"] = 1
    else:
        result["context_origin"] = "development"
    with pytest.raises(ProgressDashboardError):
        OVERVIEW["_run_recap_projection"](result, audit)


def test_saved_recap_loader_refuses_an_unjoined_audit(tmp_path: Path) -> None:
    reference = json.loads((ROOT / "configs/dashboard-gameplay-evidence.json").read_text())
    reference["audit"]["sha256"] = "0" * 64
    path = tmp_path / "reference.json"
    path.write_text(json.dumps(reference))
    with pytest.raises(ProgressDashboardError, match="changed"):
        OVERVIEW["_load_run_recap"](path)


@pytest.mark.parametrize(
    "changes",
    [
        {"samples_after": 500},
        {"setup_censors": 1},
        {"terminal_lessons": 7},
        {"fit_count": 0},
        {"successful_examples": 30},
        {"weighted_mse_after": float("nan")},
        {"weighted_mse_before": True},
        {"training_choice_changes": 30},
    ],
)
def test_training_summary_rejects_false_accounting(changes: dict) -> None:
    training, _ = OVERVIEW["_training_projection"](OVERVIEW["_load_learning_evidence"]())
    with pytest.raises(ProgressDashboardError):
        replace(training, **changes)


def test_evidence_reference_rejects_changed_bytes_and_escaping_path(tmp_path: Path) -> None:
    reference = json.loads((ROOT / "configs/dashboard-learning-evidence.json").read_text())
    path = tmp_path / "reference.json"
    reference["sha256"] = "0" * 64
    path.write_text(json.dumps(reference))
    with pytest.raises(ProgressDashboardError, match="changed"):
        OVERVIEW["_load_learning_evidence"](path)
    reference["path"] = "../private-record.json"
    path.write_text(json.dumps(reference))
    with pytest.raises(ProgressDashboardError):
        OVERVIEW["_load_learning_evidence"](path)


def test_relay_preserves_typed_semantics_but_drops_unknown_fields() -> None:
    status = _status()
    status["dashboard"]["untrusted_extra"] = "must not be forwarded"
    status["untrusted_extra"] = {"pretend_control": True}
    projected = snapshot_from_public_status(status).public_dict()
    assert projected["collection"]["living"] == 3
    assert projected["controller_endpoints"] == 0
    assert "untrusted_extra" not in projected


@pytest.mark.parametrize(
    "key,value",
    [
        ("controller_endpoints", 1),
        ("raw_address_fields", 1),
        ("schema", "some-other-local-service"),
        ("message", "Open file:///private/example"),
        ("message", "Read /home/example/data"),
        ("actions", -1),
    ],
)
def test_relay_rejects_wrong_or_private_feed(key: str, value: object) -> None:
    status = _status()
    status[key] = value
    with pytest.raises(ProgressDashboardError):
        snapshot_from_public_status(status)


def test_relay_disconnect_returns_to_overview_without_live_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    overview = replace(
        _snapshot(),
        run_status="waiting",
        collection_observed=False,
        work=DashboardWorkState(headline="Engineering work"),
    )
    state = DashboardRelayState(overview, live_port=8769)
    status = _status()
    status["dashboard"]["untrusted_extra"] = "must not be forwarded"
    png = encode_rgb_png(1, 1, bytes((5, 7, 9)))
    endpoints = []

    def get(endpoint: str) -> bytes:
        endpoints.append(endpoint)
        return json.dumps(status).encode() if endpoint == "/api/status" else png

    monkeypatch.setattr(state, "_get", get)
    assert state.poll()
    assert endpoints == ["/api/status", "/frame.png"]
    public = json.loads(state.status_bytes()[0])
    assert public["dashboard"]["frame_ready"] is True
    assert "untrusted_extra" not in public["dashboard"]
    assert public["work"]["headline"] == "Engineering work"
    assert state.frame_bytes()[0] == png

    def disconnected(endpoint: str) -> bytes:
        raise OSError("producer stopped")

    monkeypatch.setattr(state, "_get", disconnected)
    assert state.poll() is False
    public = json.loads(state.status_bytes()[0])
    assert public["run_status"] == "waiting"
    assert public["dashboard"]["frame_ready"] is False
    assert public["collection"]["observed"] is False


@pytest.mark.parametrize("port", [True, 0, 80, -1, 65536])
def test_relay_cannot_target_other_network_destinations(port: int) -> None:
    with pytest.raises(ProgressDashboardError):
        DashboardRelayState(_snapshot(), live_port=port)


@pytest.mark.parametrize("same_model,same_count", [(True, True), (False, True), (True, False)])
def test_saved_training_chart_follows_only_the_exact_live_model(
    monkeypatch,
    same_model: bool,
    same_count: bool,
) -> None:
    training, component = OVERVIEW["_training_projection"](OVERVIEW["_load_learning_evidence"]())
    state = DashboardRelayState(
        replace(_snapshot(), training=training, learning_components=(component,)),
        live_port=8769,
    )
    live_component = replace(
        component,
        model_sha256=component.model_sha256 if same_model else "0" * 64,
        train_examples=component.train_examples if same_count else component.train_examples + 1,
    )
    upstream = DashboardState(replace(_snapshot(), learning_components=(live_component,)))
    monkeypatch.setattr(state, "_get", lambda endpoint: upstream.status_bytes()[0])
    assert state.poll()
    result = json.loads(state.status_bytes()[0])
    assert (result["training"] is not None) is (same_model and same_count)


def test_actual_loopback_feed_switches_and_disconnects_without_controller_access() -> None:
    upstream = DashboardState(_snapshot())
    png = encode_rgb_png(1, 1, bytes((17, 19, 23)))
    upstream.publish_png(png, logical_frame=40)
    with ProgressDashboardServer(upstream, port=0) as server:
        port = int(server.url.split(":")[-1].rstrip("/"))
        relay = DashboardRelayState(replace(_snapshot(), run_status="waiting"), live_port=port)
        assert relay.poll()
        assert relay.frame_bytes()[0] == png
        assert json.loads(relay.status_bytes()[0])["collection"]["living"] == 3
        upstream.publish(replace(_snapshot(), stage="Second goal", actions=10))
        assert relay.poll()
        assert json.loads(relay.status_bytes()[0])["stage"] == "Second goal"
    assert relay.poll() is False
    assert json.loads(relay.status_bytes()[0])["run_status"] == "waiting"


def test_view_has_unique_semantic_targets_and_no_external_assets() -> None:
    class Inventory(HTMLParser):
        ids: list[str] = []
        external: list[str] = []

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            for key, value in attrs:
                if key == "id" and value:
                    self.ids.append(value)
                if key in {"src", "href"} and value and value.startswith("http"):
                    self.external.append(value)

    parser = Inventory()
    html = _DASHBOARD_HTML.decode()
    parser.feed(html)
    assert len(parser.ids) == len(set(parser.ids))
    assert set(
        ("frame-empty", "viewer-toggle", "work-panel", "decision-panel", "fit-chart")
    ) <= set(parser.ids)
    assert not parser.external
    assert "prefers-reduced-motion" in html
    assert 'aria-pressed="false"' in html
    assert "setInterval(refresh" not in html
    assert "CONNECTION LOST / LAST FRAME" in html
