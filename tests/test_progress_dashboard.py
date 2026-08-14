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
    DashboardLearningComponent,
    DashboardLiveEvaluationState,
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
    with pytest.raises(ProgressDashboardError, match="three entries"):
        DashboardExperimentState(counter_labels=("one", "two"))  # type: ignore[arg-type]


def test_dashboard_supports_red_training_counter_labels() -> None:
    experiment = DashboardExperimentState(
        phase="live_evaluation",
        zero_shot_completed=4,
        zero_shot_total=4,
        adaptation_completed=4,
        adaptation_total=4,
        sealed_completed=0,
        sealed_total=1,
        heading="Red training milestone",
        eyebrow="Red hierarchical learner",
        counter_labels=(
            "Portable heads fitted",
            "Held-out gates passed",
            "Full Red shadow runs",
        ),
    ).public_dict()

    assert experiment["heading"] == "Red training milestone"
    assert experiment["counter_labels"] == {
        "zero_shot": "Portable heads fitted",
        "adaptation": "Held-out gates passed",
        "sealed_test": "Full Red shadow runs",
    }


def test_dashboard_exposes_path_free_learning_evidence_and_live_scorecard() -> None:
    component = DashboardLearningComponent(
        name="Battle ranker",
        scope="Ranks legal moves",
        status="shadow",
        authority="teacher_supervised",
        train_examples=100,
        validation_examples=40,
        validation_correct=36,
        baseline_correct=20,
        model_sha256="a" * 64,
        independent_validation_units=4,
        baseline_id="test_baseline",
        paired_wins=4,
        paired_losses=1,
        paired_two_sided_exact_p=0.375,
        candidate_count_results=((2, 7, 10),),
    )
    evaluation = DashboardLiveEvaluationState(
        battle_decisions=10,
        teacher_agreements=8,
        teacher_disagreements=1,
        teacher_queries=10,
        teacher_fallbacks=2,
        corrections_saved=2,
        low_confidence_fallbacks=1,
        team_decisions=4,
        team_agreements=3,
    )
    snapshot = DashboardSnapshot(
        game="Pokémon Red",
        run_status="running",
        stage="Pewter City",
        message="Teacher-supervised live evaluation.",
        model=DashboardModelState(
            mode="shadow",
            decisions=10,
            teacher_queries=10,
            fallbacks=2,
        ),
        learning_components=(component,),
        live_evaluation=evaluation,
    ).public_dict()

    assert snapshot["learning_components"] == [component.public_dict()]
    assert snapshot["live_evaluation"]["teacher_agreement_rate"] == pytest.approx(8 / 9)  # type: ignore[index]
    assert snapshot["live_evaluation"]["model_execution_rate"] == pytest.approx(8 / 10)  # type: ignore[index]
    assert snapshot["live_evaluation"]["teacher_agreement_denominator"] == 9  # type: ignore[index]
    assert snapshot["live_evaluation"]["model_execution_denominator"] == 10  # type: ignore[index]
    assert snapshot["live_evaluation"]["team_accuracy"] == 0.75  # type: ignore[index]


def test_dashboard_rejects_inconsistent_live_scorecard() -> None:
    with pytest.raises(ProgressDashboardError, match="comparisons"):
        DashboardLiveEvaluationState(
            battle_decisions=1,
            teacher_agreements=1,
            teacher_disagreements=1,
            teacher_queries=1,
        )
    with pytest.raises(ProgressDashboardError, match="match model decisions"):
        DashboardSnapshot(
            game="Pokémon Red",
            run_status="running",
            stage="test",
            message="test",
            live_evaluation=DashboardLiveEvaluationState(
                battle_decisions=1,
                unclassified_decisions=1,
            ),
        )


def test_live_scorecard_rejects_an_unacknowledged_decision_gap() -> None:
    with pytest.raises(ProgressDashboardError, match="battle decisions must equal"):
        DashboardLiveEvaluationState(
            battle_decisions=10,
            teacher_agreements=8,
            teacher_fallbacks=1,
            teacher_queries=9,
        )


def test_live_scorecard_allows_unsupported_observation_to_end_as_non_move_control() -> None:
    state = DashboardLiveEvaluationState(
        battle_decisions=1,
        teacher_queries=1,
        unsupported_observations=1,
        non_move_control_decisions=1,
    ).public_dict()

    assert state["decision_accounting_complete"] is True
    assert state["teacher_fallbacks"] == 0

    with pytest.raises(ProgressDashboardError, match="unsupported observations"):
        DashboardLiveEvaluationState(
            battle_decisions=1,
            unsupported_observations=1,
            unclassified_decisions=1,
        )


def test_live_scorecard_rejects_overlapping_typed_fallback_triggers() -> None:
    with pytest.raises(ProgressDashboardError, match="typed fallback triggers"):
        DashboardLiveEvaluationState(
            battle_decisions=10,
            teacher_agreements=4,
            teacher_queries=10,
            teacher_fallbacks=6,
            low_confidence_fallbacks=6,
            unsupported_observations=6,
        )


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
    assert "Learned stack" in html
    assert "held-out evidence" in html
    assert "Live shadow scorecard" in html
    assert "independent val units" in html
    assert "historical unclassified" in html
    assert "candidate audit" in html
    assert 'grid-template-areas: "name name" "status samples" "score digest"' in html
    assert "candidate ${exactScore" in html
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
