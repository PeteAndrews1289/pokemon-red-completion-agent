"""Snapshot the emulator mid-route so later work does not replay the route.

Twelve runs in one session each replayed 275 checkpoints, roughly six minutes,
to reach the same thirty seconds of game. Every one of them was iterating on a
single menu. This captures the state at a checkpoint so that menu can be
exercised in seconds instead.

The snapshot is derived from the ROM and is private in exactly the way the ROM
is. Write it outside the repository -- the default lands in the session
scratchpad -- and never commit it.

Usage::

    POKEMON_RED_ROM=<path> python scripts/capture_checkpoint.py \\
        --at "Returned safely from Mansion" --out <path>.state
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pokemon_red_completion.captured_progress import write_captured_progress  # noqa: E402
from pokemon_red_completion.emulator import PyBoyAdapter  # noqa: E402
from pokemon_red_completion.rom import resolve_rom_path  # noqa: E402


class _CaptureReached(Exception):
    """Raised to stop the route once the wanted checkpoint has been recorded."""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--at",
        required=True,
        help="checkpoint label to snapshot at, matched as a substring",
    )
    parser.add_argument("--out", type=Path, required=True, help="where to write the state")
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    args = parser.parse_args(argv)

    rom = resolve_rom_path(args.rom)
    # An injected emulator is wrapped in nullcontext by the play path, so it
    # is never entered there and has to be started here.
    emulator = PyBoyAdapter(rom)
    emulator.start()
    captured: list[tuple[str, str, int, int]] = []

    def progress(update: object) -> None:
        # The sink receives a QualifiedPlayProgress, not a string. Match on its
        # label and its checkpoint id so either form of --at works.
        label = str(getattr(update, "label", update))
        checkpoint_id = str(getattr(update, "checkpoint_id", ""))
        completed = getattr(update, "completed", "?")
        total = getattr(update, "total", "?")
        print(f"[{completed}/{total}] {label}", flush=True)
        wanted = args.at.lower()
        if captured or (wanted not in label.lower() and wanted not in checkpoint_id.lower()):
            return
        emulator.save_state(args.out)
        captured.append((checkpoint_id, label, int(completed), int(total)))
        raise _CaptureReached(label)

    from pokemon_red_completion.play import run_qualified_play

    try:
        # ``_emulator`` is the seam the play path already exposes for injecting
        # an adapter, so the snapshot needs no change to the route itself.
        run_qualified_play(rom, _emulator=emulator, progress=progress)
    except _CaptureReached:
        pass
    except Exception as error:  # noqa: BLE001 - the route's own failures are the news
        if not captured:
            print(f"route stopped before {args.at!r}: {error}", file=sys.stderr)
            return 1

    emulator.close()

    if not captured:
        print(f"never reached a checkpoint matching {args.at!r}", file=sys.stderr)
        return 1

    checkpoint_id, label, completed, total = captured[0]
    from pokemon_red_completion.play import QUALIFIED_OBJECTIVE_COMPLETION_CHECKPOINTS

    verified = tuple(
        objective_id
        for completion_checkpoint, objective_id in QUALIFIED_OBJECTIVE_COMPLETION_CHECKPOINTS
        if completion_checkpoint <= completed
    )
    envelope_path = args.out.with_name(args.out.name + ".json")
    write_captured_progress(
        envelope_path,
        state_path=args.out,
        checkpoint_id=checkpoint_id,
        checkpoint_label=label,
        checkpoints_completed=completed,
        checkpoints_total=total,
        verified_objective_ids=verified,
    )
    size = args.out.stat().st_size
    print(f"\ncaptured at {label!r}\nwrote {args.out} ({size} bytes)")
    print(f"wrote authenticated progress envelope {envelope_path}")
    print("This file is ROM-derived private data. Do not commit it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
