#!/usr/bin/env python3
"""Run one non-promotable clean-power teacher diagnostic through Mansion return.

This development-only surface exists to localize fresh-root generator failures
without claiming an official assignment, saving a state, creating a root, or
collecting a learner outcome.  Every seed receives one durable private JSONL
ledger before the emulator starts.  A stopped process therefore leaves its last
verified checkpoint instead of losing the only useful evidence in console
output.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Any, Never, cast

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
while str(SRC_ROOT) in sys.path:
    sys.path.remove(str(SRC_ROOT))
sys.path.insert(0, str(SRC_ROOT))

from pokemon_red_completion.collection_protocol import (  # noqa: E402
    working_source_bundle_sha256,
)
from pokemon_red_completion.constants import POKEMON_RED_US_REV_0  # noqa: E402
from pokemon_red_completion.emulator import PyBoyAdapter  # noqa: E402
from pokemon_red_completion.observation import PokemonRedStateReader  # noqa: E402
from pokemon_red_completion.play import (  # noqa: E402
    QUALIFIED_OBJECTIVE_COMPLETION_CHECKPOINTS,
    QualifiedPlayProgress,
    run_qualified_play,
)
from pokemon_red_completion.provenance import canonical_sha256  # noqa: E402
from pokemon_red_completion.red_living_dex_episode_lineage import (  # noqa: E402
    RED_LIVING_DEX_FRESH_EPISODE_ASSIGNMENT_SCHEMA,
    RED_LIVING_DEX_FRESH_EPISODE_CAMPAIGN_ID,
    RED_LIVING_DEX_FRESH_EPISODE_CHECKPOINT_ID,
    RED_LIVING_DEX_FRESH_EPISODE_PARTITION,
    RedLivingDexFreshEpisodeAssignment,
    compose_red_living_dex_fresh_episode_teacher_execution_sha256,
    derive_red_living_dex_initial_wait_frames,
)
from pokemon_red_completion.red_living_dex_fresh_episode_runtime import (  # noqa: E402
    CleanPowerFreshEpisodeEmulator,
)
from pokemon_red_completion.rom import resolve_rom_path  # noqa: E402

_LEDGER_SCHEMA = "pokemon.red.private-fresh-teacher-diagnostic-ledger.v1"
_RESULT_SCHEMA = "pokemon.red.fresh-teacher-diagnostic-result.v1"


class FreshTeacherDiagnosticError(RuntimeError):
    """One development-only teacher diagnostic failed its local contract."""


@dataclass(frozen=True, slots=True)
class _CheckpointReached(Exception):
    update: QualifiedPlayProgress


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        del message
        raise FreshTeacherDiagnosticError("arguments")


class _DurableLedger:
    """An exclusive, append-only ledger claimed before emulator construction."""

    def __init__(self, root: Path, seed: int) -> None:
        resolved_root = root.resolve()
        try:
            resolved_root.relative_to(PROJECT_ROOT.resolve())
        except ValueError:
            pass
        else:
            raise FreshTeacherDiagnosticError("private_ledger_inside_repository")
        resolved_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        path = resolved_root / f"red-fresh-teacher-diagnostic-{seed}.jsonl"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(path, flags, 0o600)
        except OSError:
            raise FreshTeacherDiagnosticError("diagnostic_seed_already_claimed") from None
        self.path = path
        self._descriptor = descriptor

    def append(self, event: dict[str, object]) -> None:
        payload = (
            json.dumps(
                {"schema": _LEDGER_SCHEMA, **event},
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            + b"\n"
        )
        os.write(self._descriptor, payload)
        os.fsync(self._descriptor)

    def close(self) -> None:
        if self._descriptor >= 0:
            os.close(self._descriptor)
            self._descriptor = -1


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(description=__doc__)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--private-ledger-root", type=Path, required=True)
    parser.add_argument("--rom", type=Path)
    return parser


def _diagnostic_assignment(seed: int) -> RedLivingDexFreshEpisodeAssignment:
    if type(seed) is not int or seed <= 0:  # noqa: E721
        raise FreshTeacherDiagnosticError("seed")
    source_bundle_sha256 = working_source_bundle_sha256(PROJECT_ROOT)
    runner_sha256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    generator_execution_sha256 = canonical_sha256(
        {
            "promotion_eligible": False,
            "runner_sha256": runner_sha256,
            "schema": "pokemon.red.fresh-teacher-diagnostic-execution.v1",
            "source_bundle_sha256": source_bundle_sha256,
        }
    )
    teacher_execution_sha256 = compose_red_living_dex_fresh_episode_teacher_execution_sha256(
        source_bundle_sha256=source_bundle_sha256,
        generator_execution_sha256=generator_execution_sha256,
    )
    wait_frames = derive_red_living_dex_initial_wait_frames(seed)
    commitment = {
        "campaign_id": RED_LIVING_DEX_FRESH_EPISODE_CAMPAIGN_ID,
        "capacity_evidence_sha256": canonical_sha256(
            {
                "purpose": "development-only-failure-localization",
                "schema": "pokemon.red.fresh-teacher-diagnostic-capacity.v1",
            }
        ),
        "declared_runs": 1,
        "harness_seed": seed,
        "initial_wait_frames": wait_frames,
        "generator_execution_sha256": generator_execution_sha256,
        "ordinal": 1,
        "partition": RED_LIVING_DEX_FRESH_EPISODE_PARTITION,
        "run_id": f"red-fresh-teacher-diagnostic-{seed}",
        "schema": RED_LIVING_DEX_FRESH_EPISODE_ASSIGNMENT_SCHEMA,
        "source_bundle_sha256": source_bundle_sha256,
        "target_active_box_count": 17,
        "target_checkpoint_id": RED_LIVING_DEX_FRESH_EPISODE_CHECKPOINT_ID,
        "target_template_ordinal": 2,
        "teacher_execution_sha256": teacher_execution_sha256,
    }
    assignment_id = canonical_sha256(commitment)
    return RedLivingDexFreshEpisodeAssignment(
        campaign_id=RED_LIVING_DEX_FRESH_EPISODE_CAMPAIGN_ID,
        run_id=cast(str, commitment["run_id"]),
        ordinal=1,
        declared_runs=1,
        partition=RED_LIVING_DEX_FRESH_EPISODE_PARTITION,
        harness_seed=seed,
        initial_wait_frames=wait_frames,
        target_template_ordinal=2,
        target_active_box_count=17,
        target_checkpoint_id=RED_LIVING_DEX_FRESH_EPISODE_CHECKPOINT_ID,
        source_bundle_sha256=source_bundle_sha256,
        teacher_execution_sha256=teacher_execution_sha256,
        generator_execution_sha256=generator_execution_sha256,
        capacity_evidence_sha256=cast(
            str,
            commitment["capacity_evidence_sha256"],
        ),
        assignment_id=assignment_id,
        root_lineage_id=f"red-living-dex-fresh-root-{assignment_id}",
        episode_id=f"red-ldx-fresh-{assignment_id}",
    )


def _path_free_failure(error: BaseException) -> dict[str, object]:
    chain: list[dict[str, object]] = []
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and len(chain) < 4 and id(current) not in seen:
        seen.add(id(current))
        frames: list[dict[str, object]] = []
        cursor: TracebackType | None = current.__traceback__
        while cursor is not None:
            code = cursor.tb_frame.f_code
            frames.append(
                {
                    "function_name": code.co_name,
                    "line_number": cursor.tb_lineno,
                    "source_name": Path(code.co_filename).name,
                }
            )
            cursor = cursor.tb_next
        raw_message = str(current)
        safe_message, message_redacted = _path_free_message(raw_message)
        chain.append(
            {
                "exception_module": type(current).__module__,
                "exception_name": type(current).__name__,
                "message": safe_message,
                "message_redacted": message_redacted,
                "message_sha256": hashlib.sha256(
                    raw_message.encode("utf-8", errors="replace")
                ).hexdigest(),
                "traceback_frames": frames[-16:],
            }
        )
        current = current.__cause__ or current.__context__
    first = chain[0]
    return {
        "exception_chain": chain,
        "exception_module": first["exception_module"],
        "exception_name": first["exception_name"],
        "message_sha256": first["message_sha256"],
    }


def _path_free_message(message: str) -> tuple[str, bool]:
    """Retain bounded diagnostics only when the message cannot contain a path."""

    if (
        not isinstance(message, str)
        or len(message) > 512
        or "/" in message
        or "\\" in message
        or "~" in message
        or re.search(r"(?:^|\s)[A-Za-z]:", message)
    ):
        return "[path-bearing-or-unbounded-message]", True
    return message, False


def _verified_objectives(completed: int) -> tuple[str, ...]:
    return tuple(
        objective_id
        for checkpoint, objective_id in QUALIFIED_OBJECTIVE_COMPLETION_CHECKPOINTS
        if checkpoint <= completed
    )


def _gameplay_snapshot(memory: Any) -> dict[str, object]:
    """Read a compact path-free failure state before the emulator is closed."""

    raw = PokemonRedStateReader(memory).read()
    return {
        "badge_bits": raw.badge_bits,
        "bag_items": raw.bag_items,
        "battle_state": raw.battle_state,
        "enemy_hp": raw.enemy_hp,
        "enemy_level": raw.enemy_level,
        "enemy_max_hp": raw.enemy_max_hp,
        "enemy_species_id": raw.enemy_species_id,
        "game_started": raw.game_started,
        "map_id": raw.map_id,
        "party_hp": raw.party_hp,
        "party_levels": raw.party_levels,
        "party_max_hp": raw.party_max_hp,
        "party_moves": raw.party_moves,
        "party_pp": raw.party_pp,
        "party_species_ids": raw.party_species_ids,
        "party_status": raw.party_status,
        "player_money": raw.player_money,
        "player_x": raw.player_x,
        "player_y": raw.player_y,
    }


def _run(args: argparse.Namespace) -> dict[str, object]:
    assignment = _diagnostic_assignment(args.seed)
    ledger = _DurableLedger(args.private_ledger_root, args.seed)
    emulator: PyBoyAdapter | None = None
    guarded: CleanPowerFreshEpisodeEmulator | None = None
    last_checkpoint: QualifiedPlayProgress | None = None
    try:
        ledger.append(
            {
                "assignment_id": assignment.assignment_id,
                "event": "claimed",
                "harness_seed": assignment.harness_seed,
                "initial_wait_frames": assignment.initial_wait_frames,
                "promotion_eligible": False,
                "root_generation_authorized": False,
                "state_save_authorized": False,
            }
        )
        emulator = PyBoyAdapter(
            resolve_rom_path(args.rom),
            watch=False,
            expected_rom=POKEMON_RED_US_REV_0,
        ).start()
        guarded = CleanPowerFreshEpisodeEmulator(emulator, assignment)
        guarded.perform_initial_wait()

        def progress(update: QualifiedPlayProgress) -> None:
            nonlocal last_checkpoint
            last_checkpoint = update
            ledger.append(
                {
                    "checkpoint_completed": update.completed,
                    "checkpoint_id": update.checkpoint_id,
                    "checkpoint_total": update.total,
                    "controller_actions": guarded.controller_actions,
                    "emulator_frames": guarded.frame_count,
                    "event": "checkpoint",
                    "harness_seed": assignment.harness_seed,
                }
            )
            if update.checkpoint_id == RED_LIVING_DEX_FRESH_EPISODE_CHECKPOINT_ID:
                raise _CheckpointReached(update)

        try:
            run_qualified_play(
                args.rom,
                progress=progress,
                _emulator=cast(Any, guarded),
            )
        except _CheckpointReached as reached:
            guarded.reconcile_runtime_accounting()
            if (
                reached.update.checkpoint_id != RED_LIVING_DEX_FRESH_EPISODE_CHECKPOINT_ID
                or guarded.pressed_buttons
                or guarded.save_state_loads
                or guarded.terminal_state_saves
            ):
                raise FreshTeacherDiagnosticError("terminal_gate") from None
            result = {
                "actions": guarded.controller_actions,
                "checkpoint_completed": reached.update.completed,
                "checkpoint_id": reached.update.checkpoint_id,
                "checkpoint_total": reached.update.total,
                "frames": guarded.frame_count,
                "harness_seed": assignment.harness_seed,
                "initial_wait_frames": assignment.initial_wait_frames,
                "promotion_eligible": False,
                "root_generated": False,
                "schema": _RESULT_SCHEMA,
                "status": "mansion_returned",
            }
            ledger.append({"event": "terminal", **result})
            return result
        raise FreshTeacherDiagnosticError("checkpoint_not_reached")
    except BaseException as error:
        actions = guarded.controller_actions if guarded is not None else 0
        frames = guarded.frame_count if guarded is not None else 0
        try:
            gameplay_state: dict[str, object] | None = (
                _gameplay_snapshot(guarded) if guarded is not None else None
            )
        except BaseException:
            gameplay_state = {"snapshot_unavailable": True}
        failure = {
            "controller_actions": actions,
            "emulator_frames": frames,
            "event": "failure",
            "failure": _path_free_failure(error),
            "gameplay_state": gameplay_state,
            "harness_seed": assignment.harness_seed,
            "last_checkpoint_id": (
                last_checkpoint.checkpoint_id if last_checkpoint is not None else None
            ),
            "promotion_eligible": False,
            "root_generated": False,
        }
        ledger.append(failure)
        return {
            "actions": actions,
            "failure": failure["failure"],
            "frames": frames,
            "gameplay_state": gameplay_state,
            "harness_seed": assignment.harness_seed,
            "last_checkpoint_id": failure["last_checkpoint_id"],
            "promotion_eligible": False,
            "root_generated": False,
            "schema": _RESULT_SCHEMA,
            "status": "failed",
        }
    finally:
        if guarded is not None:
            guarded.close()
        elif emulator is not None:
            emulator.close()
        ledger.close()


def main() -> int:
    try:
        result = _run(_parser().parse_args())
    except BaseException as error:
        result = {
            "failure": _path_free_failure(error),
            "promotion_eligible": False,
            "root_generated": False,
            "schema": _RESULT_SCHEMA,
            "status": "failed_before_ledger",
        }
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "mansion_returned" else 1


if __name__ == "__main__":
    raise SystemExit(main())
