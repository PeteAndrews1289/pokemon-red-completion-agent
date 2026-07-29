from __future__ import annotations

import json
from pathlib import Path

import pytest

from pokemon_red_completion import cli
from pokemon_red_completion.opening import OpeningChapterError, OpeningProgress
from pokemon_red_completion.play import QualifiedPlayProgress


def test_route_command_prints_validated_hall_of_fame_route(capsys) -> None:
    assert cli.main(["route"]) == 0

    payload = json.loads(capsys.readouterr().out)

    assert payload[0]["id"] == "power_on"
    assert payload[-1]["id"] == "enter_hall_of_fame"
    assert payload[-1]["prerequisites"] == ["defeat_champion"]
    assert len(payload) >= 30


def test_bootstrap_command_prints_only_public_report(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class FakeReport:
        def public_dict(self) -> dict[str, object]:
            return {"status": "ok", "clean_power_on": True}

    private_path = Path("/private/Pokemon Red.gb")
    monkeypatch.setattr(cli, "resolve_rom_path", lambda argument: private_path)
    monkeypatch.setattr(cli, "run_bootstrap_smoke", lambda path: FakeReport())

    assert cli.main(["bootstrap", "--rom", str(private_path)]) == 0

    output = capsys.readouterr().out
    assert json.loads(output) == {"clean_power_on": True, "status": "ok"}
    assert str(private_path) not in output


def test_opening_command_wires_watch_progress_and_public_report(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class FakeReport:
        verified_objectives = ("power_on", "begin_adventure", "choose_starter")
        next_objective = "receive_pokedex"

        def public_dict(self) -> dict[str, object]:
            return {
                "status": "ok",
                "objective_progress": {
                    "verified": 3,
                    "total": 36,
                    "next": "receive_pokedex",
                },
            }

    private_path = Path("/private/Pokemon Red.gb")
    monkeypatch.setattr(cli, "resolve_rom_path", lambda argument: private_path)

    def fake_run_opening_chapter(
        path: Path,
        *,
        watch: bool,
        speed: int | None,
        progress,
    ) -> FakeReport:
        assert path == private_path
        assert watch is True
        assert speed == 4
        progress(
            OpeningProgress(
                checkpoint_id="bedroom_ready",
                label="Bedroom input ready",
                completed=1,
                total=6,
                frames_executed=9_804,
            )
        )
        progress(
            OpeningProgress(
                checkpoint_id="starter_obtained",
                label="Selected and verified Squirtle",
                completed=6,
                total=6,
                frames_executed=20_000,
            )
        )
        return FakeReport()

    monkeypatch.setattr(cli, "run_opening_chapter", fake_run_opening_chapter)

    assert (
        cli.main(
            [
                "opening",
                "--rom",
                str(private_path),
                "--watch",
                "--speed",
                "4",
            ]
        )
        == 0
    )

    captured = capsys.readouterr()
    assert json.loads(captured.out) == {
        "objective_progress": {
            "next": "receive_pokedex",
            "total": 36,
            "verified": 3,
        },
        "status": "ok",
    }
    assert captured.err.splitlines() == [
        "[1/6] Bedroom input ready",
        "[6/6] Selected and verified Squirtle",
        "Objectives: 3/36 verified | Next: Deliver Oak's Parcel and receive the Pokédex",
    ]
    assert str(private_path) not in captured.out
    assert str(private_path) not in captured.err


def test_opening_command_defaults_to_headless_unlimited_mode(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class FakeReport:
        verified_objectives = ("power_on",)
        next_objective = "begin_adventure"

        def public_dict(self) -> dict[str, object]:
            return {"status": "ok"}

    private_path = Path("/private/Pokemon Red.gb")
    observed: dict[str, object] = {}
    monkeypatch.setattr(cli, "resolve_rom_path", lambda argument: private_path)

    def fake_run_opening_chapter(
        path: Path,
        *,
        watch: bool,
        speed: int | None,
        progress,
    ) -> FakeReport:
        observed.update(path=path, watch=watch, speed=speed, progress=progress)
        return FakeReport()

    monkeypatch.setattr(cli, "run_opening_chapter", fake_run_opening_chapter)

    assert cli.main(["opening", "--rom", str(private_path)]) == 0

    captured = capsys.readouterr()
    assert observed == {
        "path": private_path,
        "watch": False,
        "speed": None,
        "progress": cli._print_opening_progress,
    }
    assert json.loads(captured.out) == {"status": "ok"}
    assert captured.err == "Objectives: 1/36 verified | Next: Complete the opening sequence\n"


def test_opening_command_rejects_speed_without_watch(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as error:
        cli.main(["opening", "--speed", "2"])

    captured = capsys.readouterr()
    assert error.value.code == 2
    assert captured.out == ""
    assert "--speed requires --watch" in captured.err


def test_opening_command_reports_opening_errors(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    private_path = Path("/private/Pokemon Red.gb")
    monkeypatch.setattr(cli, "resolve_rom_path", lambda argument: private_path)

    def fail_opening(*args, **kwargs):
        raise OpeningChapterError("The opening teacher missed a verified gate.")

    monkeypatch.setattr(cli, "run_opening_chapter", fail_opening)

    with pytest.raises(SystemExit) as error:
        cli.main(["opening", "--rom", str(private_path)])

    captured = capsys.readouterr()
    assert error.value.code == 2
    assert captured.out == ""
    assert "The opening teacher missed a verified gate." in captured.err
    assert str(private_path) not in captured.err


def test_play_command_runs_the_continuous_watched_boundary(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class FakeReport:
        verified_objectives = (
            "power_on",
            "begin_adventure",
            "choose_starter",
            "receive_pokedex",
            "reach_pewter",
            "defeat_brock",
            "reach_cerulean",
            "help_bill",
            "reach_vermilion",
            "defeat_misty",
        )
        next_objective = "obtain_cut"

        def public_dict(self) -> dict[str, object]:
            return {
                "schema": "qualified-play-v5",
                "status": "ok",
                "game_complete": False,
            }

    private_path = Path("/private/Pokemon Red.gb")
    monkeypatch.setattr(cli, "resolve_rom_path", lambda argument: private_path)

    def fake_run_qualified_play(
        path: Path,
        *,
        watch: bool,
        speed: int | None,
        progress,
    ) -> FakeReport:
        assert path == private_path
        assert watch is True
        assert speed == 4
        progress(
            QualifiedPlayProgress(
                checkpoint_id="bedroom_ready",
                label="Bedroom input ready",
                completed=1,
                total=73,
                frames_executed=9_804,
            )
        )
        progress(
            QualifiedPlayProgress(
                checkpoint_id="vermilion_reached",
                label="Reached stable Vermilion City",
                completed=73,
                total=73,
                frames_executed=501_922,
            )
        )
        return FakeReport()

    monkeypatch.setattr(cli, "run_qualified_play", fake_run_qualified_play)

    assert (
        cli.main(
            [
                "play",
                "--rom",
                str(private_path),
                "--watch",
                "--speed",
                "4",
            ]
        )
        == 0
    )

    captured = capsys.readouterr()
    assert json.loads(captured.out) == {
        "game_complete": False,
        "schema": "qualified-play-v5",
        "status": "ok",
    }
    assert captured.err.splitlines() == [
        "[1/73] Bedroom input ready",
        "[73/73] Reached stable Vermilion City",
        "Objectives: 10/36 verified | Next: Obtain HM01 Cut aboard the S.S. Anne",
        "Safe stop: latest independently qualified boundary reached; the game is not complete.",
    ]
    assert str(private_path) not in captured.out
    assert str(private_path) not in captured.err


def test_play_command_stops_cleanly_on_keyboard_interrupt(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    private_path = Path("/private/Pokemon Red.gb")
    monkeypatch.setattr(cli, "resolve_rom_path", lambda argument: private_path)

    def interrupt(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "run_qualified_play", interrupt)

    assert cli.main(["play", "--rom", str(private_path)]) == 130

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        "Stopped safely without saving. No success report was emitted.\n"
    )
    assert str(private_path) not in captured.err
