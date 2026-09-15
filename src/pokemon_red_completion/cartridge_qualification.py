"""Fail-closed, durable accounting for disposable cartridge qualification.

This is engineering evidence, never a training or evaluation result. A campaign
is one process-local budget: after any failure it cannot open another case.
An interrupted journal is evidence of incomplete work, not permission to resume.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pokemon_red_completion.actions import MacroAction
from pokemon_red_completion.battle_runtime_diagnostics import (
    BattleRuntimeDiagnostic,
    bind_battle_runtime_failure_sink,
)
from pokemon_red_completion.executor import (
    ControllerTiming,
    ExecutedAction,
    FrameSafeExecutor,
    JournaledController,
)
from pokemon_red_completion.private_artifacts import EpisodeWriter, PrivateArtifactRoot


class QualificationPhase(StrEnum):
    SOURCE_INSPECTION = "source_inspection"
    RELOCATION = "relocation"
    ENCOUNTER_SETUP = "encounter_setup"
    BATTLE = "battle"
    TERMINAL = "terminal"


class QualificationError(RuntimeError):
    """A known, path-free qualification reason."""

    def __init__(self, reason: str) -> None:
        if reason not in {
            "case_action_limit",
            "campaign_action_limit",
            "case_frame_limit",
            "campaign_frame_limit",
            "unsettled_terminal",
            "unmetered_input",
            "frame_accounting_unknown",
            "campaign_closed",
            "journal_unhealthy",
            "frame_tick_incomplete",
            "frame_tick_overrun",
            "battle_runtime_failed",
            "journal_closed",
        }:
            raise ValueError("unknown qualification reason")
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class QualificationLimits:
    maximum_actions: int
    maximum_frames: int

    def __post_init__(self) -> None:
        if any(
            type(value) is not int or value <= 0
            for value in (
                self.maximum_actions,
                self.maximum_frames,
            )
        ):
            raise ValueError("qualification limits must be positive integers")


class QualificationCampaign:
    def __init__(self, limits: QualificationLimits, *, maximum_cases: int) -> None:
        if type(maximum_cases) is not int or maximum_cases <= 0:
            raise ValueError("maximum_cases must be a positive integer")
        self.limits = limits
        self.maximum_cases = maximum_cases
        self.cases_started = 0
        self.actions_attempted = 0
        self.actions_completed = 0
        self.frames = 0
        self.cost_known = True
        self.closed = False
        self.active = False


class QualificationJournal:
    def __init__(
        self,
        writer: EpisodeWriter,
        limits: QualificationLimits,
        campaign: QualificationCampaign,
    ) -> None:
        self.writer = writer
        self.limits = limits
        self.campaign = campaign
        self.phase = QualificationPhase.SOURCE_INSPECTION
        self.actions_attempted = 0
        self.actions_completed = 0
        self.frames = 0
        self.cost_known = True
        self.in_flight = False
        self.pending_frames: int | None = None
        self.healthy = True
        self.finished = False
        self.runtime_diagnostic: dict[str, object] | None = None
        self.last_tick_frames = 0

    def snapshot(self) -> dict[str, object]:
        return {
            "phase": self.phase.value,
            "actions_attempted": self.actions_attempted,
            "actions_completed": self.actions_completed,
            "emulator_frames": self.frames,
            "cost_known": self.cost_known,
            "action_in_flight": self.in_flight,
            "pending_frames": self.pending_frames,
            "campaign_actions_attempted": self.campaign.actions_attempted,
            "campaign_actions_completed": self.campaign.actions_completed,
            "campaign_emulator_frames": self.campaign.frames,
            "campaign_cost_known": self.campaign.cost_known,
        }

    def append(self, stream: str, record: Mapping[str, object]) -> None:
        try:
            self.writer.append(stream, record, durable=True)
        except BaseException:
            self.healthy = False
            self.campaign.closed = True
            raise

    def checkpoint(self) -> None:
        self.append("journal", self.snapshot())

    def enter_phase(self, phase: str) -> None:
        if self.in_flight:
            raise QualificationError("unmetered_input")
        self.phase = QualificationPhase(phase)
        self.checkpoint()

    def require_healthy(self) -> None:
        if not self.healthy:
            raise QualificationError("journal_unhealthy")
        if self.finished or self.campaign.closed:
            raise QualificationError("journal_closed")
        if self.runtime_diagnostic is not None:
            raise QualificationError("battle_runtime_failed")
        if not self.cost_known:
            raise QualificationError("frame_accounting_unknown")

    def admit_frames(self, frames: int) -> None:
        self.require_healthy()
        if not self.in_flight or self.pending_frames is not None:
            raise QualificationError("unmetered_input")
        if type(frames) is not int or frames <= 0:
            raise ValueError("tick frames must be a positive integer")
        if self.frames + frames > self.limits.maximum_frames:
            raise QualificationError("case_frame_limit")
        if self.campaign.frames + frames > self.campaign.limits.maximum_frames:
            raise QualificationError("campaign_frame_limit")
        self.pending_frames = frames
        self.checkpoint()  # A hard crash leaves a prospective, explicitly unresolved tick.

    def record_frames(self, frames: int) -> None:
        self.last_tick_frames = frames
        self.frames += frames
        self.campaign.frames += frames
        self.pending_frames = None
        self.checkpoint()

    def retain_runtime_failure(self, diagnostic: BattleRuntimeDiagnostic) -> None:
        # Runtime events contain tuples. Compare their persisted JSON shape,
        # not Python tuples against the lists returned by readback.
        self.runtime_diagnostic = json.loads(json.dumps(diagnostic.to_dict(), allow_nan=False))
        self.append(
            "runtime_diagnostic",
            {
                **self.snapshot(),
                "diagnostic": self.runtime_diagnostic,
            },
        )

    def executor(self, session: Any, timing: ControllerTiming) -> FrameSafeExecutor:
        return _QualificationExecutor(self, session, timing)


    def admit_input(self) -> None:
        self.require_healthy()
        if not self.in_flight:
            raise QualificationError("unmetered_input")

    def tick_failed(self) -> None:
        if self.pending_frames is not None:
            self.cost_known = False
            self.campaign.cost_known = False

    def tick_completed(self, frames: int) -> None:
        if self.last_tick_frames < frames:
            raise QualificationError("frame_tick_incomplete")
        if self.last_tick_frames > frames:
            raise QualificationError("frame_tick_overrun")


class _QualificationExecutor(FrameSafeExecutor):
    def __init__(
        self, journal: QualificationJournal, session: Any, timing: ControllerTiming
    ) -> None:
        super().__init__(JournaledController(
            session, admit_input=journal.admit_input, admit_frames=journal.admit_frames,
            record_frames=journal.record_frames, tick_failed=journal.tick_failed,
            tick_completed=journal.tick_completed,
        ), timing)
        self.journal = journal

    def execute(self, action: MacroAction) -> ExecutedAction:
        journal = self.journal
        journal.require_healthy()
        if journal.in_flight:
            raise QualificationError("unmetered_input")
        if journal.actions_attempted >= journal.limits.maximum_actions:
            raise QualificationError("case_action_limit")
        if journal.campaign.actions_attempted >= journal.campaign.limits.maximum_actions:
            raise QualificationError("campaign_action_limit")
        journal.actions_attempted += 1
        journal.campaign.actions_attempted += 1
        journal.in_flight = True
        journal.checkpoint()
        result = super().execute(action)
        journal.actions_completed += 1
        journal.campaign.actions_completed += 1
        journal.in_flight = False
        journal.checkpoint()
        return result


def _failure_reason(error: BaseException, phase: QualificationPhase) -> str:
    if isinstance(error, QualificationError):
        return error.reason
    if isinstance(error, (KeyboardInterrupt, SystemExit)):
        return "process_interrupted"
    from pokemon_red_completion.red_repeatable_battle_scenario_runtime import (
        RepeatableRedBattleScenarioRuntimeError,
    )

    if isinstance(error, RepeatableRedBattleScenarioRuntimeError):
        reasons = {
            "source state bytes are unavailable": "source_state_unavailable",
            "immutable ROM bytes are unavailable": "rom_unavailable",
            "materializer source commit is invalid": "source_commit_invalid",
            "maximum encounter steps must be positive": "encounter_limit_invalid",
            "emulator returned no materialized state bytes": "materialized_state_unavailable",
            "loaded source differs from its authenticated observation": (
                "source_observation_mismatch"
            ),
            "source state digest differs": "source_digest_mismatch",
            "assignment differs from its authenticated source": "assignment_source_mismatch",
            "assignment party menu differs from its authenticated source": "party_menu_mismatch",
            "assignment venue is not reachable from its source": "venue_unreachable",
            "trainer assignment is inconsistent with its source boundary": (
                "trainer_boundary_mismatch"
            ),
            "trainer source is not at the MAIN policy boundary": "trainer_policy_boundary_mismatch",
            "selected venue cannot be reauthenticated": "venue_authentication_failed",
            "selected venue mechanics differ from its reachable edge": "venue_mechanics_mismatch",
            "relocation source is not at its expected safe boundary": "unsafe_relocation_boundary",
            "portable relocation source is not at a safe boundary": "unsafe_portable_boundary",
            "direct source is not at its selected venue boundary": "direct_venue_mismatch",
            "source did not reach its selected encounter venue": "relocation_destination_mismatch",
            "wild encounter walker made no bounded progress": "encounter_no_progress",
            "wild encounter exceeded its step bound": "encounter_step_limit",
            "materialized state is not its selected live MAIN boundary": (
                "capture_boundary_mismatch"
            ),
            "materialized state lacks active party move mechanics": "party_mechanics_unavailable",
            "materialized party menu differs from its prospective assignment": (
                "materialized_menu_mismatch"
            ),
        }
        # Lookup only exact trusted literals; arbitrary text is never retained.
        if len(error.args) == 1 and isinstance(error.args[0], str):
            return reasons.get(error.args[0], f"{phase.value}_failed")
    # Do not serialize arbitrary exception messages (which can contain paths,
    # credentials, or emulator state). Component phase is a semantic reason.
    return f"{phase.value}_failed"


def run_qualification_case(
    store: PrivateArtifactRoot,
    episode_id: str,
    assignment: Mapping[str, object],
    *,
    limits: QualificationLimits,
    campaign: QualificationCampaign,
    execute: Callable[[QualificationJournal], Mapping[str, object]],
) -> dict[str, object]:
    """Claim before work, meter every executor, seal and reopen before returning.

    Execution failures propagate after their exact evidence is reopened. Storage
    failures also close the campaign; no fallback can turn them into success.
    Completion/reopen run outside the execution handler: a published episode
    must never be aborted a second time after a readback error.
    """
    if campaign.closed or campaign.active or campaign.cases_started >= campaign.maximum_cases:
        raise QualificationError("campaign_closed")
    campaign.active = True
    campaign.cases_started += 1
    journal: QualificationJournal | None = None
    try:
        writer = store.begin_episode(episode_id)
        journal = QualificationJournal(writer, limits, campaign)
        try:
            journal.append(
                "assignment",
                {
                    **assignment,
                    "schema": "pokemon.red.cartridge-qualification.v2",
                    "learning_credit": False,
                    "evaluation_credit": False,
                    "retry_allowed": False,
                    "maximum_case_actions": limits.maximum_actions,
                    "maximum_case_frames": limits.maximum_frames,
                    "maximum_campaign_actions": campaign.limits.maximum_actions,
                    "maximum_campaign_frames": campaign.limits.maximum_frames,
                    "maximum_cases": campaign.maximum_cases,
                },
            )
            journal.append("claim", {"input_status_at_claim": "not_yet_sent"})
            journal.checkpoint()
            with bind_battle_runtime_failure_sink(journal.retain_runtime_failure):
                result = execute(journal)
            journal.require_healthy()
            if journal.in_flight or journal.pending_frames is not None:
                raise QualificationError("unsettled_terminal")
            journal.enter_phase(QualificationPhase.TERMINAL.value)
            terminal = {
                "result": json.loads(json.dumps(dict(result), allow_nan=False)),
                **journal.snapshot(), "status": "complete",
            }
            journal.append("terminal", terminal)
        except BaseException as error:
            campaign.closed = True
            failure = {
                **journal.snapshot(),
                "reason": _failure_reason(error, journal.phase),
                "error_type": type(error).__name__,
                "diagnostic": journal.runtime_diagnostic,
                "journal_healthy": journal.healthy,
                "retry_allowed": False,
            }
            journal.append("failure_diagnostic", failure)
            writer.abort("qualification_failed")
            reopened = store.read_failed_episode_diagnostic(episode_id)
            if reopened.failure_diagnostic != failure:
                raise RuntimeError("qualification failure readback differs") from error
            raise
        writer.complete()
        records = list(store.open_episode(episode_id).iter_stream("terminal", max_records=1))
        if records != [terminal]:
            raise RuntimeError("qualification terminal readback differs")
        return terminal
    except BaseException:
        campaign.closed = True
        raise
    finally:
        if journal is not None:
            journal.finished = True
        campaign.active = False
