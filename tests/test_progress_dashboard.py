from __future__ import annotations

import json
import struct
import urllib.error
import urllib.request
import zlib

import pytest

from pokemon_red_completion.progress_dashboard import (
    DashboardExperimentState,
    DashboardFrameObserver,
    DashboardGoalPressure,
    DashboardModelState,
    DashboardPartyMember,
    DashboardSnapshot,
    DashboardState,
    ProgressDashboardError,
    ProgressDashboardServer,
    encode_rgb_png,
)


def _snapshot() -> DashboardSnapshot:
    return DashboardSnapshot(
        game="Pokémon Crystal 1.1",
        run_status="running",
        stage="Zero-shot probe",
        message="Ranking an unseen Crystal goal menu.",
        frame_count=12_345,
        actions=91,
        emulation_speed=8.5,
        stage_progress=0.5,
        location="New Bark Town",
        registered_species=3,
        living_species=2,
        level_cap_species=1,
        collection_target=250,
        capture_items=7,
        free_storage_slots=276,
        party=(DashboardPartyMember(1, "Species #155", 12, 30, 40),),
        goals=(
            DashboardGoalPressure("advance_story", 0.8, True, True),
            DashboardGoalPressure("restore_team", 0.25, True),
        ),
        model=DashboardModelState(
            mode="zero_shot",
            choice="advance_story",
            confidence=0.87,
            decisions=4,
        ),
        experiment=DashboardExperimentState(
            phase="zero_shot",
            zero_shot_completed=9,
        ),
        events=("Prediction committed before teacher access",),
    )


def _decode_png_rgb(payload: bytes) -> tuple[int, int, bytes]:
    assert payload.startswith(b"\x89PNG\r\n\x1a\n")
    cursor = 8
    compressed = bytearray()
    width = height = 0
    while cursor < len(payload):
        length = struct.unpack(">I", payload[cursor : cursor + 4])[0]
        kind = payload[cursor + 4 : cursor + 8]
        chunk = payload[cursor + 8 : cursor + 8 + length]
        cursor += 12 + length
        if kind == b"IHDR":
            width, height = struct.unpack(">II", chunk[:8])
        elif kind == b"IDAT":
            compressed.extend(chunk)
        elif kind == b"IEND":
            break
    rows = zlib.decompress(bytes(compressed))
    stride = width * 3
    assert len(rows) == height * (stride + 1)
    rgb = b"".join(
        rows[row * (stride + 1) + 1 : (row + 1) * (stride + 1)]
        for row in range(height)
    )
    return width, height, rgb


def test_dashboard_snapshot_is_path_free_and_reports_observer_only_status() -> None:
    document = _snapshot().public_dict()
    encoded = json.dumps(document, sort_keys=True)

    assert document["controller_endpoints"] == 0
    assert document["model"]["teacher_queries"] == 0  # type: ignore[index]
    assert document["experiment"]["zero_shot"] == {  # type: ignore[index]
        "completed": 9,
        "total": 18,
    }
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded
    assert "0xd" not in encoded.lower()


def test_dashboard_snapshot_rejects_inconsistent_or_deceptive_status() -> None:
    with pytest.raises(ProgressDashboardError, match="collection counts"):
        DashboardSnapshot(
            game="Crystal",
            run_status="running",
            stage="test",
            message="test",
            registered_species=1,
            living_species=2,
        )
    with pytest.raises(ProgressDashboardError, match="unavailable goal"):
        DashboardGoalPressure("advance_story", 0.5, False, True)
    with pytest.raises(ProgressDashboardError, match="completed cannot exceed total"):
        DashboardExperimentState(zero_shot_completed=19)


def test_dependency_free_png_encoder_preserves_exact_rgb_pixels() -> None:
    rgb = bytes((1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12))
    payload = encode_rgb_png(2, 2, rgb)

    assert _decode_png_rgb(payload) == (2, 2, rgb)
    with pytest.raises(ProgressDashboardError, match="length"):
        encode_rgb_png(2, 2, b"short")


def test_frame_observer_rate_limits_and_rejects_backward_frames() -> None:
    moments = iter((0.0, 0.01, 0.2))
    state = DashboardState(_snapshot())
    observer = DashboardFrameObserver(state, maximum_fps=8, clock=lambda: next(moments))

    assert observer.wants_frame(1)
    observer.publish_frame(1, 1, bytes((1, 2, 3)), 1)
    assert not observer.wants_frame(2)
    assert observer.wants_frame(3)
    with pytest.raises(ProgressDashboardError, match="backward"):
        state.publish_png(encode_rgb_png(1, 1, bytes((1, 2, 3))), logical_frame=0)


def test_loopback_dashboard_serves_status_video_and_no_control_methods() -> None:
    state = DashboardState(_snapshot())
    state.publish_png(encode_rgb_png(1, 1, bytes((1, 2, 3))), logical_frame=12_345)

    with ProgressDashboardServer(state, port=0) as server:
        with urllib.request.urlopen(server.url, timeout=2) as response:
            html = response.read().decode("utf-8")
        with urllib.request.urlopen(server.url + "api/status", timeout=2) as response:
            status = json.loads(response.read())
        with urllib.request.urlopen(server.url + "frame.png", timeout=2) as response:
            frame = response.read()
            content_type = response.headers["Content-Type"]
        request = urllib.request.Request(server.url + "api/status", method="POST")
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(request, timeout=2)

    assert "Pokémon Learning Observatory" in html
    assert "VIEW ONLY" in html
    assert status["dashboard"]["view_only"] is True
    assert status["dashboard"]["frame_ready"] is True
    assert status["controller_endpoints"] == 0
    assert content_type == "image/png"
    assert frame.startswith(b"\x89PNG")
    assert error.value.code == 405
    assert error.value.headers["Allow"] == "GET"


def test_dashboard_refuses_non_loopback_binding() -> None:
    with pytest.raises(ProgressDashboardError, match="loopback"):
        ProgressDashboardServer(host="0.0.0.0", port=0)
