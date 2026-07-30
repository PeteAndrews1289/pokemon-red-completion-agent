from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from pokemon_red_completion import cli
from pokemon_red_completion.opening import OpeningChapterError, OpeningProgress
from pokemon_red_completion.play import QualifiedPlayProgress
from pokemon_red_completion.private_artifacts import PrivateArtifactError
from pokemon_red_completion.provenance import (
    EvaluationIdentityError,
    SourceIdentity,
    canonical_sha256,
)
from pokemon_red_completion.rom import RomFingerprint


def test_route_command_prints_validated_hall_of_fame_route(capsys) -> None:
    assert cli.main(["route"]) == 0

    payload = json.loads(capsys.readouterr().out)

    assert payload[0]["id"] == "power_on"
    assert payload[-1]["id"] == "enter_hall_of_fame"
    assert payload[-1]["prerequisites"] == ["defeat_champion"]
    assert len(payload) >= 30


def test_private_data_init_does_not_resolve_a_rom_and_prints_no_path(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    private_root = Path("/private/external/trajectories")
    observed: dict[str, object] = {}

    def fail_if_rom_resolved(argument: object) -> None:
        pytest.fail(f"ROM resolution was unexpectedly attempted for {argument!r}")

    def fake_initialize(root: Path, *, repository_root: Path) -> object:
        observed.update(root=root, repository_root=repository_root)
        return object()

    monkeypatch.setattr(cli, "resolve_rom_path", fail_if_rom_resolved)
    monkeypatch.setattr(cli, "initialize_private_root", fake_initialize)

    assert (
        cli.main(
            [
                "private-data",
                "init",
                "--private-root",
                str(private_root),
            ]
        )
        == 0
    )

    captured = capsys.readouterr()
    assert json.loads(captured.out) == {
        "schema": "private-root-init-v1",
        "status": "ready",
    }
    assert captured.err == ""
    assert str(private_root) not in captured.out
    assert observed == {
        "root": private_root,
        "repository_root": cli.REPOSITORY_ROOT,
    }


def test_private_data_init_redacts_private_root_from_errors(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    private_root = Path("/private/external/trajectories")

    def fail_initialize(root: Path, *, repository_root: Path) -> None:
        del repository_root
        raise PrivateArtifactError(f"unsafe private root: {root}")

    monkeypatch.setattr(cli, "initialize_private_root", fail_initialize)

    with pytest.raises(SystemExit) as error:
        cli.main(
            [
                "private-data",
                "init",
                "--private-root",
                str(private_root),
            ]
        )

    captured = capsys.readouterr()
    assert error.value.code == 2
    assert captured.out == ""
    assert "unsafe private root: <private>" in captured.err
    assert str(private_root) not in captured.err


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
        "Completion verified: Champion defeated and Hall of Fame entered.",
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
    assert captured.err == ("Stopped safely without saving. No success report was emitted.\n")
    assert str(private_path) not in captured.err


def test_record_command_wires_private_episode_and_prints_path_free_summary(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class FakePlayReport:
        verified_objectives = tuple(objective.id for objective in cli.COMPLETION_QUEST)
        next_objective = None

        def public_dict(self) -> dict[str, object]:
            return {
                "schema": "qualified-play-v5",
                "status": "ok",
                "game_complete": True,
            }

    class FakeEpisodeSummary:
        def public_dict(self) -> dict[str, object]:
            return {
                "schema": "private-episode-summary-v1",
                "episode_id": expected_episode_id,
                "status": "complete",
                "stream_records": {"episode": 1, "executions": 42},
                "total_records": 43,
                "total_bytes": 4096,
                "manifest_sha256": "a" * 64,
            }

    class FakeWriter:
        summary = FakeEpisodeSummary()

        def __enter__(self) -> FakeWriter:
            return self

        def __exit__(self, *args: object) -> bool:
            return False

    class FakeSink:
        def __init__(
            self,
            writer: FakeWriter,
            *,
            episode_id: str,
            game_id: str,
        ) -> None:
            assert writer is fake_writer
            observed.update(
                sink_episode_id=episode_id,
                sink_game_id=game_id,
            )

        def write_episode_header(self, *, metadata: object) -> None:
            observed["header"] = metadata

    private_path = Path("/private/Pokemon Red.gb")
    private_root_path = Path("/private/external/trajectories")
    expected_episode_id = "red-teacher-1234567890abcdef1234567890abcdef"
    fake_writer = FakeWriter()
    observed: dict[str, object] = {}
    fake_metadata = {
        "adapter_id": cli.POKEMON_RED_ADAPTER_ID,
        "ontology_id": cli.POKEMON_CORE_ONTOLOGY_ID,
        "source": {"git_commit": "a" * 40, "worktree_dirty": False},
    }
    fake_root = SimpleNamespace(
        begin_episode=lambda episode_id: observed.update(begin_episode=episode_id) or fake_writer
    )

    monkeypatch.setattr(cli, "resolve_rom_path", lambda argument: private_path)

    def fake_open_private_root(root: Path, *, repository_root: Path) -> object:
        observed.update(private_root=root, repository_root=repository_root)
        return fake_root

    monkeypatch.setattr(cli, "open_private_root", fake_open_private_root)
    monkeypatch.setattr(cli, "EpisodeTrajectorySink", FakeSink)
    monkeypatch.setattr(
        cli,
        "_recording_metadata",
        lambda path, *, episode_id, watch, speed: (
            observed.update(
                metadata_rom=path,
                metadata_episode_id=episode_id,
                metadata_watch=watch,
                metadata_speed=speed,
            )
            or fake_metadata
        ),
    )
    monkeypatch.setattr(
        cli.uuid,
        "uuid4",
        lambda: SimpleNamespace(hex="1234567890abcdef1234567890abcdef"),
    )

    def fake_run_qualified_play(
        path: Path,
        *,
        watch: bool,
        speed: int | None,
        progress,
        trajectory_sink: FakeSink,
        trajectory_episode_id: str,
    ) -> FakePlayReport:
        observed.update(
            rom=path,
            watch=watch,
            speed=speed,
            progress=progress,
            trajectory_sink=trajectory_sink,
            trajectory_episode_id=trajectory_episode_id,
        )
        return FakePlayReport()

    monkeypatch.setattr(cli, "run_qualified_play", fake_run_qualified_play)

    assert (
        cli.main(
            [
                "record",
                "--private-root",
                str(private_root_path),
                "--rom",
                str(private_path),
                "--watch",
                "--speed",
                "2",
            ]
        )
        == 0
    )

    captured = capsys.readouterr()
    assert json.loads(captured.out) == {
        "episode": {
            "episode_id": expected_episode_id,
            "manifest_sha256": "a" * 64,
            "schema": "private-episode-summary-v1",
            "status": "complete",
            "stream_records": {"episode": 1, "executions": 42},
            "total_bytes": 4096,
            "total_records": 43,
        },
        "game_complete": True,
        "schema": "private-trajectory-recording-v1",
        "status": "ok",
    }
    assert str(private_path) not in captured.out
    assert str(private_path) not in captured.err
    assert str(private_root_path) not in captured.out
    assert str(private_root_path) not in captured.err
    assert observed["private_root"] == private_root_path
    assert observed["repository_root"] == cli.REPOSITORY_ROOT
    assert observed["begin_episode"] == expected_episode_id
    assert observed["sink_episode_id"] == expected_episode_id
    assert observed["sink_game_id"] == cli.POKEMON_RED_GAME_ID
    assert observed["rom"] == private_path
    assert observed["watch"] is True
    assert observed["speed"] == 2
    assert observed["progress"] is cli._print_qualified_progress
    assert observed["trajectory_episode_id"] == expected_episode_id
    assert observed["metadata_rom"] == private_path
    assert observed["metadata_episode_id"] == expected_episode_id
    assert observed["metadata_watch"] is True
    assert observed["metadata_speed"] == 2
    assert observed["header"] == fake_metadata


def test_record_command_rejects_speed_without_watch(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as error:
        cli.main(
            [
                "record",
                "--private-root",
                "/private/external/trajectories",
                "--speed",
                "2",
            ]
        )

    captured = capsys.readouterr()
    assert error.value.code == 2
    assert captured.out == ""
    assert "--speed requires --watch" in captured.err


def test_recording_metadata_requires_an_identified_clean_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cli,
        "detect_source_identity",
        lambda root, *, include_untracked: SourceIdentity("a" * 40, True),
    )

    with pytest.raises(EvaluationIdentityError, match="clean worktree"):
        cli._recording_metadata(
            Path("/private/Pokemon Red.gb"),
            episode_id="red-teacher-example",
            watch=False,
            speed=None,
        )


def test_recording_metadata_is_reproducible_and_omits_private_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private_rom = Path("/private/Pokemon Red.gb")
    source = SourceIdentity("a" * 40, False)
    monkeypatch.setattr(
        cli,
        "detect_source_identity",
        lambda root, *, include_untracked: source,
    )
    monkeypatch.setattr(
        cli,
        "verify_rom",
        lambda path: RomFingerprint(
            filename=path.name,
            title="POKEMON RED",
            size_bytes=1_048_576,
            sha1="b" * 40,
            sha256="c" * 64,
        ),
    )
    monkeypatch.setattr(cli, "version", lambda package: "2.7.0")

    metadata = cli._recording_metadata(
        private_rom,
        episode_id="red-teacher-example",
        watch=False,
        speed=None,
    )

    serialized = json.dumps(metadata, sort_keys=True)
    assert str(private_rom) not in serialized
    assert private_rom.name not in serialized
    assert metadata["source"] == source.public_dict()
    assert metadata["rom_identity"]["sha256"] == "c" * 64
    assert metadata["runtime"]["emulator_version"] == "2.7.0"
    assert metadata["configuration_sha256"] == canonical_sha256(metadata["configuration"])
    assert metadata["split"]["root_lineage_id"] == "red-teacher-example"
