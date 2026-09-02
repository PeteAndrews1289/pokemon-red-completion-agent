from __future__ import annotations

import argparse
import runpy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = runpy.run_path(
    "scripts/build_battle_scenario_retained_train_capture_catalog.py"
)
CATALOG_HELPERS = runpy.run_path("tests/test_battle_scenario_capture_catalog.py")
RUN_GLOBALS = SCRIPT["_run"].__globals__
MAIN_GLOBALS = SCRIPT["main"].__globals__


def _args(tmp_path: Path) -> argparse.Namespace:
    capture_directory = tmp_path / "captures"
    capture_directory.mkdir()
    return argparse.Namespace(
        catalog_id="battle-v2-five-retained-train-inputs",
        expected_source_commit="d" * 40,
        expected_source_bundle_sha256=f"{500:064x}",
        predecessor_plan=capture_directory / "plan.json",
        expected_predecessor_plan_sha256="1" * 64,
        predecessor_journal=capture_directory / "journal.json",
        expected_predecessor_journal_sha256="2" * 64,
        predecessor_capture_directory=capture_directory,
        out_catalog=tmp_path / "retained-train-catalog.json",
        rom=tmp_path / "Pokemon Red.gb",
    )


def test_builder_authenticates_exact_five_success_two_failure_terminal(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    args = _args(tmp_path)
    source = SimpleNamespace(git_commit="d" * 40)
    plan = object()
    journal = object()
    payload: bytes | None = None
    terminal_calls: list[tuple[int, int]] = []

    monkeypatch.setitem(
        RUN_GLOBALS, "detect_source_identity", lambda *_args, **_kwargs: source
    )
    monkeypatch.setitem(RUN_GLOBALS, "require_clean_source", lambda _source: None)
    monkeypatch.setitem(RUN_GLOBALS, "require_published_source", lambda *_args: None)
    monkeypatch.setitem(
        RUN_GLOBALS,
        "working_source_bundle_sha256",
        lambda _root: f"{500:064x}",
    )
    monkeypatch.setitem(RUN_GLOBALS, "resolve_rom_path", lambda path: path)
    monkeypatch.setitem(
        RUN_GLOBALS,
        "verify_rom",
        lambda _path: SimpleNamespace(sha256=f"{11:064x}"),
    )
    builder = RUN_GLOBALS["catalog_builder"]
    monkeypatch.setattr(builder, "_commit", lambda value, _subject: value)
    monkeypatch.setattr(builder, "_sha256", lambda value, _subject: value)
    monkeypatch.setattr(
        builder,
        "_private_capture_directory",
        lambda path, **_kwargs: path,
    )
    monkeypatch.setattr(builder, "_read_predecessor_plan", lambda *_args, **_kwargs: plan)
    monkeypatch.setattr(builder, "_read_journal", lambda *_args, **_kwargs: journal)

    def require_terminal(
        _plan: object,
        _journal: object,
        *,
        expected_successes: int,
        expected_failures: int,
        capture_directory: Path,
    ) -> None:
        assert capture_directory == args.predecessor_capture_directory
        terminal_calls.append((expected_successes, expected_failures))

    monkeypatch.setattr(builder, "_require_terminal_producer", require_terminal)
    entries = tuple(CATALOG_HELPERS["_entry"](index) for index in range(5))
    entries = (
        *entries[:3],
        replace(entries[3], venue_id="route_11"),
        entries[4],
    )
    monkeypatch.setattr(
        builder,
        "_catalog_entries",
        lambda **_kwargs: (entries, ()),
    )
    monkeypatch.setattr(
        builder,
        "_producer",
        lambda *_args, **_kwargs: CATALOG_HELPERS["_producer"]("predecessor"),
    )
    monkeypatch.setattr(
        builder,
        "_private_new_catalog",
        lambda path, **_kwargs: path,
    )

    def write(_path: Path, observed: bytes) -> None:
        nonlocal payload
        payload = observed

    monkeypatch.setattr(builder, "_write_exclusive", write)
    monkeypatch.setattr(
        builder,
        "_read_owned_regular",
        lambda *_args, **_kwargs: payload,
    )

    receipt = SCRIPT["_run"](args)

    assert terminal_calls == [(5, 2)]
    assert receipt["status"] == "authenticated_action_free"
    assert receipt["capture_count"] == 5
    assert receipt["historical_failed_assignments"] == 2
    assert receipt["venue_counts"] == {"digletts_cave": 3, "route_11": 2}
    assert receipt["controller_actions"] == 0
    assert receipt["emulator_frames"] == 0
    assert receipt["outcomes_opened"] == 0
    assert receipt["model_fits"] == 0


def test_builder_cli_failure_is_sanitized(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    monkeypatch.setitem(
        MAIN_GLOBALS,
        "_parser",
        lambda: SimpleNamespace(parse_args=lambda _argv: _args(tmp_path)),
    )
    monkeypatch.setitem(
        MAIN_GLOBALS,
        "_run",
        lambda _args: (_ for _ in ()).throw(RuntimeError("private path")),
    )

    assert SCRIPT["main"]([]) == 1
    output = capsys.readouterr().out
    assert "private path" not in output
    assert '"status": "failed_closed"' in output
    assert '"controller_actions": 0' in output
