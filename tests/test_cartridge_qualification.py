from __future__ import annotations

import json
from contextlib import suppress

import pytest

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.battle_runtime_diagnostics import diagnose_battle_runtime
from pokemon_red_completion.cartridge_qualification import (
    QualificationCampaign,
    QualificationError,
    QualificationLimits,
    run_qualification_case,
)
from pokemon_red_completion.executor import ControllerTiming
from pokemon_red_completion.private_artifacts import EpisodeWriter, initialize_private_root

WAIT = MacroAction(MacroActionKind.WAIT)
CONFIRM = MacroAction(MacroActionKind.CONFIRM)
TIMING = ControllerTiming(press_frames=3, release_frames=2, wait_frames=5)


@pytest.fixture
def store(tmp_path):
    root = tmp_path / "private"
    repository = tmp_path / "repository"
    root.mkdir()
    repository.mkdir()
    return initialize_private_root(
        root,
        repository_root=repository,
        device_id=lambda path: 2 if path == root.resolve() else 1,
        git_worktree_probe=lambda path: False,
    )


class Session:
    def __init__(self, *, initial=0, partial=False, missing_counter=False):
        self.frames = initial
        self.partial = partial
        self.missing_counter = missing_counter
        self.buttons = set()

    @property
    def frame_count(self):
        if self.missing_counter and self.frames:
            raise RuntimeError("secret counter failure")
        return self.frames

    def press(self, button):
        self.buttons.add(button)

    def release(self, button):
        self.buttons.remove(button)

    def tick(self, frames):
        self.frames += 2 if self.partial else frames
        if self.partial:
            raise RuntimeError("private partial tick")


def campaign(actions=20, frames=100):
    return QualificationCampaign(QualificationLimits(actions, frames), maximum_cases=3)


def run(store, execute, *, budget=None, limits=None, episode="case-v2"):
    return run_qualification_case(
        store,
        episode,
        {"case_id": "synthetic"},
        limits=limits or QualificationLimits(20, 100),
        campaign=budget or campaign(),
        execute=execute,
    )


@pytest.mark.parametrize(
    "phase,actions",
    [
        ("source_inspection", 0),
        ("relocation", 2),
        ("encounter_setup", 3),
        ("battle", 4),
        ("terminal", 5),
    ],
)
def test_failure_phase_and_exact_cost_reopen(store, phase, actions):
    budget = campaign()

    def execute(journal):
        journal.enter_phase(phase)
        executor = journal.executor(Session(), TIMING)
        for _ in range(actions):
            executor.execute(WAIT)
        raise ValueError("do not persist /private/secret or token=secret")

    with pytest.raises(ValueError):
        run(store, execute, budget=budget)
    evidence = store.read_failed_episode_diagnostic("case-v2")
    failure = evidence.failure_diagnostic
    assert evidence.claim == {"input_status_at_claim": "not_yet_sent"}
    assert failure["phase"] == phase
    assert failure["reason"] == f"{phase}_failed"
    assert failure["actions_attempted"] == failure["actions_completed"] == actions
    assert failure["emulator_frames"] == actions * 5
    assert failure["cost_known"] is True
    assert "secret" not in json.dumps(failure)
    assert budget.closed
    with pytest.raises(QualificationError, match="campaign_closed"):
        run(store, lambda _: pytest.fail("must not run"), budget=budget, episode="next-case")


def test_partial_tick_keeps_original_error_and_releases_button(store):
    session = Session(partial=True)

    def execute(journal):
        journal.enter_phase("relocation")
        journal.executor(session, TIMING).execute(CONFIRM)

    with pytest.raises(RuntimeError, match="private partial tick"):
        run(store, execute)
    failure = store.read_failed_episode_diagnostic("case-v2").failure_diagnostic
    assert (
        failure["actions_attempted"],
        failure["actions_completed"],
        failure["emulator_frames"],
        failure["cost_known"],
    ) == (1, 0, 2, True)
    assert failure["action_in_flight"] is True
    assert failure["pending_frames"] is None
    assert not session.buttons


def test_unreadable_post_tick_counter_is_unknown_not_zero(store):
    session = Session(missing_counter=True)
    with pytest.raises(RuntimeError, match="counter failure"):
        run(store, lambda journal: journal.executor(session, TIMING).execute(WAIT))
    failure = store.read_failed_episode_diagnostic("case-v2").failure_diagnostic
    assert session.frames == 5
    assert failure["cost_known"] is False
    assert failure["campaign_cost_known"] is False
    assert failure["pending_frames"] == 5
    assert failure["actions_completed"] == 0


@pytest.mark.parametrize("kind", ["case_action", "campaign_action", "case_frame", "campaign_frame"])
def test_setup_limits_refuse_before_exceeding_budget(store, kind):
    budget = campaign(
        actions=1 if kind == "campaign_action" else 20,
        frames=7 if kind == "campaign_frame" else 100,
    )
    limits = QualificationLimits(
        1 if kind == "case_action" else 20, 7 if kind == "case_frame" else 100
    )
    session = Session()

    def execute(journal):
        journal.enter_phase("encounter_setup")
        executor = journal.executor(session, TIMING)
        executor.execute(WAIT)
        executor.execute(WAIT)

    with pytest.raises(QualificationError, match=f"{kind}_limit"):
        run(store, execute, budget=budget, limits=limits)
    failure = store.read_failed_episode_diagnostic("case-v2").failure_diagnostic
    assert session.frames == failure["emulator_frames"] == 5
    assert failure["actions_completed"] == 1
    assert failure["actions_attempted"] == (1 if "action" in kind else 2)
    assert failure["reason"] == f"{kind}_limit"


def test_multiple_sessions_and_cases_share_actual_cost_not_frame_origins(store):
    budget = campaign()

    def execute(journal):
        journal.enter_phase("relocation")
        journal.executor(Session(initial=500), TIMING).execute(WAIT)
        journal.enter_phase("battle")
        journal.executor(Session(initial=7), TIMING).execute(CONFIRM)
        return {"settled": True}

    first = run(store, execute, budget=budget)
    second = run(store, execute, budget=budget, episode="second-case")
    assert first["emulator_frames"] == second["emulator_frames"] == 10
    assert second["campaign_emulator_frames"] == 20
    assert second["campaign_actions_completed"] == 4
    assert first["phase"] == "terminal"
    assert not budget.closed


def test_battle_sink_and_outer_failure_are_both_retained_once(store):
    @diagnose_battle_runtime
    def battle(journal):
        journal.executor(Session(), TIMING).execute(WAIT)
        raise ValueError("private battle failure")

    def execute(journal):
        journal.enter_phase("battle")
        battle(journal)

    with pytest.raises(ValueError):
        run(store, execute)
    reader = store.open_failed_episode("case-v2")
    failures = list(reader.iter_stream("failure_diagnostic"))
    diagnostics = list(reader.iter_stream("runtime_diagnostic"))
    assert len(failures) == len(diagnostics) == 1
    assert failures[0]["diagnostic"] == diagnostics[0]["diagnostic"]
    assert failures[0]["emulator_frames"] == 5


@pytest.mark.parametrize("stream", ["assignment", "claim", "journal"])
def test_storage_failure_before_input_never_calls_controller(store, monkeypatch, stream):
    original = EpisodeWriter.append
    session = Session()
    budget = campaign()

    def append(self, name, record, **kwargs):
        if name == stream:
            raise OSError("synthetic disk failure")
        return original(self, name, record, **kwargs)

    monkeypatch.setattr(EpisodeWriter, "append", append)
    with pytest.raises((OSError, RuntimeError)):
        run(store, lambda j: j.executor(session, TIMING).execute(WAIT), budget=budget)
    assert session.frames == 0 and not session.buttons
    assert budget.closed


def test_ignored_sink_failure_cannot_report_success(store, monkeypatch):
    original = EpisodeWriter.append

    def append(self, name, record, **kwargs):
        if name == "runtime_diagnostic":
            raise OSError("synthetic disk failure")
        return original(self, name, record, **kwargs)

    monkeypatch.setattr(EpisodeWriter, "append", append)

    @diagnose_battle_runtime
    def failing():
        raise ValueError("actor failed")

    def execute(journal):
        with suppress(ValueError):
            failing()
        return {"incorrect_success": True}

    with pytest.raises(QualificationError, match="journal_unhealthy"):
        run(store, execute)
    assert (
        store.read_failed_episode_diagnostic("case-v2").failure_diagnostic["journal_healthy"]
        is False
    )


def test_interrupt_is_retained_and_propagates(store):
    def execute(journal):
        journal.executor(Session(), TIMING).execute(WAIT)
        raise KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        run(store, execute)
    failure = store.read_failed_episode_diagnostic("case-v2").failure_diagnostic
    assert failure["reason"] == "process_interrupted"
    assert failure["emulator_frames"] == 5


def test_readback_failure_does_not_abort_published_episode(store, monkeypatch):
    original = type(store).open_episode

    def fail(*args, **kwargs):
        raise RuntimeError("synthetic readback failure")

    monkeypatch.setattr(type(store), "open_episode", fail)
    budget = campaign()
    with pytest.raises(RuntimeError, match="readback failure"):
        run(store, lambda _: {"ok": True}, budget=budget)
    assert original(store, "case-v2").summary.status == "complete"
    assert budget.closed


def test_duplicate_case_is_never_reexecuted(store):
    run(store, lambda _: {"ok": True})
    with pytest.raises(Exception, match="already"):
        run(store, lambda _: pytest.fail("duplicate executed"))


def test_actual_shared_wild_runtime_failure_reopens_after_setup_and_partial_action(store):
    from dataclasses import replace

    from test_battle_runtime import FakeRuntime

    from pokemon_red_completion.battle_runtime import run_adaptive_wild_battle
    from pokemon_red_completion.observation import BattleMenuPhase, BattleMenuState, MapId

    reader = FakeRuntime(menu=BattleMenuState(BattleMenuPhase.UNKNOWN))
    reader.raw = replace(reader.raw, battle_state=1)

    def execute(journal):
        journal.enter_phase("relocation")
        journal.executor(Session(initial=900), TIMING).execute(WAIT)
        journal.enter_phase("battle")
        run_adaptive_wild_battle(
            reader, journal.executor(Session(partial=True), TIMING), lambda _: 1,
            expected_map=MapId.CERULEAN_CITY,
        )

    with pytest.raises(RuntimeError, match="private partial tick"):
        run(store, execute)
    failure = store.read_failed_episode_diagnostic("case-v2").failure_diagnostic
    assert failure["phase"] == "battle"
    assert (failure["actions_attempted"], failure["actions_completed"],
            failure["emulator_frames"]) == (2, 1, 7)
    assert failure["diagnostic"]["events"][-1]["completed"] is False
    assert failure["diagnostic"]["exception_chain"][0]["error_type"] == "RuntimeError"


@pytest.mark.parametrize("delta,reason", [(2, "frame_tick_incomplete"), (8, "frame_tick_overrun")])
def test_silent_emulator_tick_mismatch_fails_with_observed_cost(store, delta, reason):
    class BrokenSession(Session):
        def tick(self, frames):
            self.frames += delta

    with pytest.raises(QualificationError, match=reason):
        run(store, lambda j: j.executor(BrokenSession(), TIMING).execute(WAIT))
    failure = store.read_failed_episode_diagnostic("case-v2").failure_diagnostic
    assert failure["emulator_frames"] == delta
    assert failure["cost_known"] is True
    assert failure["actions_completed"] == 0


def test_post_action_persistence_failure_records_completed_cost_and_stops(store, monkeypatch):
    original = EpisodeWriter.append
    session = Session()
    failed_once = False

    def append(self, name, record, **kwargs):
        nonlocal failed_once
        if name == "journal" and record["actions_completed"] == 1 and not failed_once:
            failed_once = True
            raise OSError("post-action sync failure")
        return original(self, name, record, **kwargs)

    monkeypatch.setattr(EpisodeWriter, "append", append)
    with pytest.raises(OSError, match="post-action sync failure"):
        run(store, lambda j: j.executor(session, TIMING).execute(WAIT))
    failure = store.read_failed_episode_diagnostic("case-v2").failure_diagnostic
    assert (failure["actions_completed"], failure["emulator_frames"]) == (1, 5)
    assert failure["journal_healthy"] is False


def test_finished_journal_cannot_send_more_input(store):
    retained = []
    session = Session()

    def execute(journal):
        retained.append(journal.executor(session, TIMING))
        return {"ok": True}

    run(store, execute)
    with pytest.raises(QualificationError, match="journal_closed"):
        retained[0].execute(WAIT)
    assert session.frames == 0


def test_swallowed_runtime_failure_cannot_complete(store):
    @diagnose_battle_runtime
    def failing():
        raise ValueError("actor failure")

    def execute(journal):
        with suppress(ValueError):
            failing()
        return {"incorrect_success": True}

    with pytest.raises(QualificationError, match="battle_runtime_failed"):
        run(store, execute)
