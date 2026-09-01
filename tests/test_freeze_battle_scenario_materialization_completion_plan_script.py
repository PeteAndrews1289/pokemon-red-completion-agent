from __future__ import annotations

import runpy
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = runpy.run_path(
    str(
        PROJECT_ROOT
        / "scripts"
        / "freeze_battle_scenario_materialization_completion_plan.py"
    )
)
HELPERS = runpy.run_path(
    str(PROJECT_ROOT / "tests" / "test_battle_scenario_materialization_plan_v2.py")
)


def test_completion_freezer_accepts_only_complete_bank_and_history_inputs() -> None:
    options = SCRIPT["_parser"]()._option_string_actions

    assert "--state-bank" in options
    assert "--earliest-excluded-plan" in options
    assert "--earliest-excluded-run-journal" in options
    assert "--predecessor-plan" in options
    assert "--predecessor-run-journal" in options
    assert "--predecessor-capture-directory" in options
    assert "--source-state" not in options
    assert "--party-slot" not in options
    assert "--venue" not in options


def test_completion_freeze_selects_only_the_two_missing_roots(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    predecessor, retained = HELPERS["_retained_successes"]()
    candidates = tuple(HELPERS["_candidate"](index) for index in range(20, 23))
    roots = tuple(SimpleNamespace(binding=item.source) for item in candidates)
    scan = SimpleNamespace(roots=roots)
    globals_ = SCRIPT["_freeze_under_shared_lease"].__globals__
    observed_by_state = {
        item.source.source_state_sha256: SimpleNamespace(
            claim_available=True,
            reachable_venue_allocation_eligible=True,
            eligible_venue_ids=tuple(
                venue.venue_id for venue in item.reachable_venues
            ),
        )
        for item in candidates
    }
    candidates_by_state = {
        item.source.source_state_sha256: item for item in candidates
    }

    class Emulator:
        frame_count = 0
        pressed_buttons: tuple[object, ...] = ()

        def __init__(self, path: Path) -> None:
            del path

        def __enter__(self) -> Emulator:
            return self

        def __exit__(self, *args: object) -> None:
            del args

    monkeypatch.setitem(globals_, "PyBoyAdapter", Emulator)
    monkeypatch.setitem(
        globals_,
        "fixed_account_claim_registry_lease",
        lambda *args, **kwargs: nullcontext(),
    )
    monkeypatch.setitem(
        globals_,
        "_observe_root",
        lambda root, **kwargs: observed_by_state[
            root.binding.source_state_sha256
        ],
    )
    monkeypatch.setitem(
        globals_,
        "_candidate_from_loaded_root",
        lambda binding, **kwargs: candidates_by_state[
            binding.source_state_sha256
        ],
    )
    monkeypatch.setitem(
        globals_,
        "_require_new_assignment_outputs_v2",
        lambda *args, **kwargs: None,
    )
    written: list[bytes] = []
    monkeypatch.setitem(
        globals_,
        "_write_exclusive",
        lambda path, payload: written.append(payload),
    )

    plan, claim_available = SCRIPT["_freeze_under_shared_lease"](
        scan=scan,
        registry_path=tmp_path / "claims.json",
        rom_path=tmp_path / "red.gb",
        plan_id="red-battle-v2-additive-completion",
        source_commit="c" * 40,
        source_bundle_sha256=HELPERS["_sha"]("completion-bundle"),
        rom_sha256=predecessor.rom_sha256,
        capture_directory=tmp_path,
        predecessor_plan=predecessor,
        predecessor_journal_sha256=HELPERS["_sha"]("predecessor-journal"),
        predecessor_failure_count=2,
        retained_successes=retained,
        destination=tmp_path / "plan.json",
    )

    assert claim_available == 3
    assert len(plan.retained_successes) == 5
    assert len(plan.assignments) == 2
    assert written == [plan.canonical_bytes()]


def test_completion_freeze_fails_without_enough_untouched_supply(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    predecessor, retained = HELPERS["_retained_successes"]()
    candidate = HELPERS["_candidate"](20)
    root = SimpleNamespace(binding=candidate.source)
    globals_ = SCRIPT["_freeze_under_shared_lease"].__globals__

    class Emulator:
        frame_count = 0
        pressed_buttons: tuple[object, ...] = ()

        def __init__(self, path: Path) -> None:
            del path

        def __enter__(self) -> Emulator:
            return self

        def __exit__(self, *args: object) -> None:
            del args

    monkeypatch.setitem(globals_, "PyBoyAdapter", Emulator)
    monkeypatch.setitem(
        globals_,
        "fixed_account_claim_registry_lease",
        lambda *args, **kwargs: nullcontext(),
    )
    monkeypatch.setitem(
        globals_,
        "_observe_root",
        lambda *args, **kwargs: SimpleNamespace(
            claim_available=True,
            reachable_venue_allocation_eligible=True,
            eligible_venue_ids=tuple(
                venue.venue_id for venue in candidate.reachable_venues
            ),
        ),
    )
    monkeypatch.setitem(
        globals_,
        "_candidate_from_loaded_root",
        lambda *args, **kwargs: candidate,
    )

    with pytest.raises(
        SCRIPT["BattleScenarioMaterializationPlanV2Error"],
        match="additive venue capacity",
    ):
        SCRIPT["_freeze_under_shared_lease"](
            scan=SimpleNamespace(roots=(root,)),
            registry_path=tmp_path / "claims.json",
            rom_path=tmp_path / "red.gb",
            plan_id="red-battle-v2-additive-completion",
            source_commit="c" * 40,
            source_bundle_sha256=HELPERS["_sha"]("completion-bundle"),
            rom_sha256=predecessor.rom_sha256,
            capture_directory=tmp_path,
            predecessor_plan=predecessor,
            predecessor_journal_sha256=HELPERS["_sha"]("predecessor-journal"),
            predecessor_failure_count=2,
            retained_successes=retained,
            destination=tmp_path / "plan.json",
        )
