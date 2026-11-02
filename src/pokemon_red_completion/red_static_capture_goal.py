"""Source-bound static acquisition offered to the existing learned goal menu.

The model owns whether to execute this option. The caller's explicit ball and
attempt allocation is mechanical support, not a learned ball/preparation choice.
Offers are action-free and leave no files. Selected execution writes its intent
and every throw commitment before input and retains a terminal receipt on error.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path

from .goal_manager import GoalFailureReason, GoalKind, GoalUnavailableReason
from .goal_manager_runtime import ExecutableGoalBinding, GoalExecutionReport, GoalVerification
from .observation import ItemId, event_flag_is_set
from .provenance import canonical_sha256
from .red_capture_checkpoint import create_capture_journal, write_capture_checkpoint
from .red_capture_status_runtime import RedCaptureStatusPreparer
from .red_goal_manager import RedGoalBindingOffer
from .red_one_off_capture import OneOffCaptureBudget, OneOffCapturePaused, OneOffCaptureRequest
from .red_static_capture import (
    RedStaticCaptureTarget,
    red_static_capture_targets,
    require_static_capture_admission,
)
from .red_static_capture_runtime import execute_static_capture


@dataclass(frozen=True, slots=True)
class RedStaticCaptureGoalProvider:
    rom: bytes
    target: RedStaticCaptureTarget
    ball: ItemId
    max_throws: int
    reader: object
    adapter: object
    emulator: object
    actions: object
    checkpoint_directory: Path
    prepare_status: bool = True
    maximum_status_attempts: int = 3
    preserve_viable_active: bool = True
    minimum_prepared_helper_level: int | None = None
    estimated_effort: float = 0.15
    estimated_risk: float = 0.25
    weaken_capture: bool = False
    maximum_weakening_attempts: int = 3
    prepare_facing: bool = False
    require_status_success: bool = False
    kind: GoalKind = GoalKind.ACQUIRE_SPECIES
    readiness_budget: object = None
    allow_snorlax: bool = False

    def __post_init__(self):
        if self.readiness_budget is not None:
            from .red_capture_readiness import CapturePreparationBudget

            b = self.readiness_budget
            if not isinstance(b, CapturePreparationBudget) or (
                b.ball is not self.ball or b.throws != self.max_throws
                or b.require_status != self.require_status_success
            ):
                raise ValueError("static readiness budget differs from capture allocation")
        snorlax = False
        if self.allow_snorlax and self.target.species_number == 143:
            from .red_snorlax_capture import route12_snorlax_target

            snorlax = self.target == route12_snorlax_target(self.rom)
        if not snorlax and self.target not in red_static_capture_targets(self.rom):
            raise ValueError("static goal target differs from cartridge")
        OneOffCaptureBudget(
            OneOffCaptureRequest(self.target.internal_species, self.target.level, self.ball),
            self.max_throws,
            99,
        )
        if self.kind is not GoalKind.ACQUIRE_SPECIES:
            raise ValueError("static capture is only an acquisition goal")
        if (
            type(self.prepare_status) is not bool
            or type(self.preserve_viable_active) is not bool
            or type(self.weaken_capture) is not bool
            or type(self.prepare_facing) is not bool
            or type(self.require_status_success) is not bool
            or type(self.allow_snorlax) is not bool
        ):
            raise ValueError("static capture support must be explicit")
        if self.require_status_success and not self.prepare_status:
            raise ValueError("required capture status needs status preparation")
        if self.minimum_prepared_helper_level is not None and (
            type(self.minimum_prepared_helper_level) is not int
            or not 1 <= self.minimum_prepared_helper_level <= 100
            or not self.preserve_viable_active or not self.require_status_success
        ):
            raise ValueError("prepared helper level requires explicit status and preservation")
        if (
            type(self.maximum_status_attempts) is not int
            or not 1 <= self.maximum_status_attempts <= 10
        ):
            raise ValueError("static capture status budget differs")
        if (
            type(self.maximum_weakening_attempts) is not int
            or not 1 <= self.maximum_weakening_attempts <= 10
        ):
            raise ValueError("static capture weakening budget differs")

    @property
    def configuration_sha256(self):
        return canonical_sha256(
            {
                "target": asdict(self.target),
                "ball": int(self.ball),
                "max_throws": self.max_throws,
                "prepare_status": self.prepare_status,
                "status_attempts": self.maximum_status_attempts,
                "preserve_viable_active": self.preserve_viable_active,
                **({"minimum_prepared_helper_level": self.minimum_prepared_helper_level}
                   if self.minimum_prepared_helper_level is not None else {}),
                "weaken_capture": self.weaken_capture,
                "weakening_attempts": self.maximum_weakening_attempts,
                "prepare_facing": self.prepare_facing,
                "require_status_success": self.require_status_success,
                **({"allow_snorlax": True} if self.allow_snorlax else {}),
                **({"readiness_budget": asdict(self.readiness_budget)}
                   if self.readiness_budget is not None else {}),
            }
        )

    def offer(self, observation):
        if self.readiness_budget is not None:
            from .red_capture_readiness import assess_capture_readiness

            readiness = assess_capture_readiness(
                observation, self.readiness_budget, target_available=True,
                enemy_species_id=self.target.internal_species,
            )
            if readiness.hard_blocks:
                return RedGoalBindingOffer.unavailable(
                    self.kind, GoalUnavailableReason.MISSING_RESOURCE
                )
        request = OneOffCaptureRequest(self.target.internal_species, self.target.level, self.ball)
        if self.checkpoint_directory.exists():
            return RedGoalBindingOffer.unavailable(
                self.kind, GoalUnavailableReason.TEMPORARILY_BLOCKED
            )
        try:
            if self.target.species_number == 143 and not dict(
                self.reader.read().bag_items or ()
            ).get(int(ItemId.POKE_FLUTE)):
                raise ValueError("Snorlax requires the held Flute")
            require_static_capture_admission(
                self.reader,
                self.target,
                internal_species=request.internal_species,
                level=request.level,
                ball_id=int(request.ball),
                minimum_balls=self.max_throws,
                allow_facing_preparation=self.prepare_facing,
            )
        except ValueError:
            return RedGoalBindingOffer.unavailable(
                self.kind, GoalUnavailableReason.MISSING_CAPABILITY
            )
        if observation != self.adapter.observe():
            raise ValueError("static goal offered from a stale observation")
        origin = self.emulator.save_state_bytes()
        origin_sha = sha256(origin).hexdigest()
        configuration_sha = self.configuration_sha256
        before_actions = self.actions.actions_executed
        before_frames = self.emulator.frame_count
        initial_raw = self.reader.read()
        initial_owned = self.reader.read_pokedex_state().owned_species

        def specimens():
            return Counter(self.reader.read().party_species_ids or ()) + Counter(
                species
                for box in self.reader.read_all_box_states().boxes
                for species in box.species_ids
            )

        initial_specimens = specimens()
        initial_bag = dict(initial_raw.bag_items or ())
        budget = OneOffCaptureBudget(request, self.max_throws, initial_bag[int(self.ball)])
        used = False
        completed = False
        receipt_hashes = []
        report = None
        decisions = []
        weakening = []
        prepare = RedCaptureStatusPreparer(
            self.emulator,
            self.actions,
            self.reader,
            maximum_attempts=self.maximum_status_attempts,
            expected_original_species_id=request.internal_species,
            preserve_viable_active=self.preserve_viable_active,
            minimum_prepared_helper_level=self.minimum_prepared_helper_level,
        )

        def checkpoint(phase):
            digest = write_capture_checkpoint(
                self.checkpoint_directory / f"{len(receipt_hashes):03d}-{phase}",
                state=self.emulator.save_state_bytes(),
                origin_state_sha256=origin_sha,
                target=self.target,
                budget=budget,
                status_attempts=prepare.attempts,
                maximum_status_attempts=self.maximum_status_attempts,
                preserve_viable_active=self.preserve_viable_active,
                minimum_prepared_helper_level=self.minimum_prepared_helper_level,
                phase=phase,
                parent_receipt_sha256=receipt_hashes[-1] if receipt_hashes else None,
            )
            receipt_hashes.append(digest)

        def replacement(raw):
            candidates = [
                i
                for i, hp in enumerate(raw.party_hp or ())
                if hp > 0 and i != raw.active_party_index
            ]
            return max(candidates, key=lambda i: raw.party_hp[i]) if candidates else -1

        def require_prepared_status():
            if not self.require_status_success or self.ball is ItemId.MASTER_BALL:
                return
            status = self.reader.read_enemy_capture_status()
            # Sleep, freeze or paralysis: no residual poison/burn damage.
            if status not in (1, 2, 3, 4, 5, 6, 7, 0x20, 0x40):
                raise OneOffCapturePaused("required capture status was not observed; no ball spent")

        def prepare_encounter():
            from dataclasses import asdict

            from .red_capture_weakening_runtime import prepare_nonlethal_capture

            if self.prepare_status and not prepare():
                raise RuntimeError("static capture status preparation ended encounter")
            require_prepared_status()
            weakening.append(
                asdict(
                    prepare_nonlethal_capture(
                        self.reader,
                        self.actions,
                        internal_species=request.internal_species,
                        level=request.level,
                        maximum_attempts=self.maximum_weakening_attempts,
                        allow_weakener_switch=True,
                        emulator=self.emulator,
                    )
                )
            )

        def before_throw():
            # Permanent paralysis needs no extra status/switch turn. This does
            # not promise survival; the ball executor handles faints/limits.
            if self.weaken_capture and self.reader.read_enemy_capture_status() == 0x40:
                return True
            ready = prepare()
            require_prepared_status()
            return ready

        def execute():
            nonlocal used, completed, report
            if used:
                raise RuntimeError("static acquisition binding was already attempted")
            used = True
            if (
                self.emulator.save_state_bytes() != origin
                or self.adapter.observe() != observation
                or self.actions.actions_executed != before_actions
                or self.emulator.frame_count != before_frames
            ):
                raise RuntimeError("static acquisition source changed before input")
            create_capture_journal(self.checkpoint_directory)
            checkpoint("admitted")
            try:
                if self.prepare_facing:
                    from .red_pc_storage import face_pc_boundary

                    raw = self.reader.read()
                    delta = (self.target.at[0] - raw.player_y, self.target.at[1] - raw.player_x)
                    direction = {(-1, 0): "up", (1, 0): "down", (0, -1): "left", (0, 1): "right"}[
                        delta
                    ]
                    face_pc_boundary(self.actions, self.reader, direction)
                result = execute_static_capture(
                    self.emulator,
                    self.actions,
                    self.reader,
                    self.target,
                    request,
                    rom=self.rom,
                    budget=budget,
                    before_throw=before_throw if self.prepare_status else None,
                    select_replacement=replacement,
                    record_decision=decisions.append,
                    commit_throw=lambda _: checkpoint("throw_intent"),
                    prepare_encounter=prepare_encounter if self.weaken_capture else None,
                    allow_snorlax=self.allow_snorlax,
                )
                completed = result.captured and result.consumed_event and result.source_removed
            finally:
                checkpoint("settled" if completed else "paused")
            report = GoalExecutionReport(
                self.actions.actions_executed - before_actions,
                self.emulator.frame_count - before_frames,
                dict(
                    mechanic="static_capture",
                    captured=completed,
                    throws_committed=budget.throws_committed,
                    status_attempts=prepare.attempts,
                    receipts=tuple(receipt_hashes),
                    status_reports=tuple(prepare.reports),
                    preparations=tuple(prepare.throw_preparations),
                    decisions=tuple(decisions),
                    learned_ball_selection=False,
                    weakening=tuple(weakening),
                ),
            )
            return report

        def verify(candidate_report):
            after = self.adapter.observe()
            raw = after.raw
            expected_bag = dict(initial_bag)
            expected_bag[int(self.ball)] -= budget.throws_committed
            expected_bag = {key: value for key, value in expected_bag.items() if value}
            expected_specimens = initial_specimens + Counter({self.target.internal_species: 1})
            if (
                used
                and completed
                and candidate_report is report
                and not self.emulator.pressed_buttons
                and after.input_ready
                and not raw.battle_state
                and raw.map_id == self.target.map_id
                and raw.player_money == initial_raw.player_money
                and dict(raw.bag_items or ()) == expected_bag
                and self.reader.read_pokedex_state().owned_species
                == initial_owned | {self.target.species_number}
                and specimens() == expected_specimens
                and raw.event_flags is not None
                and event_flag_is_set(raw.event_flags, self.target.event_flag)
                and not any(
                    o.sprite_index == self.target.object_index and o.visible
                    for o in self.reader.read_current_map_objects()
                )
            ):
                return GoalVerification.succeeded()
            return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)

        return RedGoalBindingOffer.available(
            ExecutableGoalBinding(
                binding_ref=(
                    f"pokemon.red:static-capture:{self.target.map_id}:"
                    f"{self.target.object_index}:{origin_sha}:{configuration_sha}"
                ),
                kind=self.kind,
                estimated_effort=self.estimated_effort,
                estimated_risk=self.estimated_risk,
                execute=execute,
                verify=verify,
                search_source_ref=f"pokemon.red:static-capture:{self.target.map_id}:{self.target.object_index}",
            )
        )
