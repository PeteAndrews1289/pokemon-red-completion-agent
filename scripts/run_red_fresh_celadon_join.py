#!/usr/bin/env python3
"""Resume the authenticated Red first-badge state and retain the Celadon join."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from run_red_fresh_first_badge import (  # noqa: E402
    REPOSITORY_ROOT,
    _load_ranker,
    _require_new_private_output,
)

from pokemon_red_completion.captured_progress import (  # noqa: E402
    load_captured_progress,
    write_captured_progress,
)
from pokemon_red_completion.emulator import PyBoyAdapter  # noqa: E402
from pokemon_red_completion.provenance import (  # noqa: E402
    detect_source_identity,
    require_clean_source,
    require_published_source,
)
from pokemon_red_completion.red_fresh_start_conductor import (  # noqa: E402
    CELADON_JOIN_VERIFIED_OBJECTIVE_IDS,
    FreshStartConductorError,
    run_first_badge_to_celadon_conductor,
)
from pokemon_red_completion.rom import resolve_rom_path  # noqa: E402
from pokemon_red_completion.route import COMPLETION_QUEST  # noqa: E402

CHECKPOINT_ID = "red-fresh-celadon-v1"
CHECKPOINT_LABEL = "Fresh lineage at the Celadon midgame boundary"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    ranker = parser.add_mutually_exclusive_group(required=True)
    ranker.add_argument("--objective-model", type=Path)
    ranker.add_argument("--integration-neutral-ranker", action="store_true")
    parser.add_argument("--rom", type=Path)
    parser.add_argument("--source-state", type=Path, required=True)
    parser.add_argument("--source-envelope", type=Path, required=True)
    parser.add_argument("--out-state", type=Path, required=True)
    parser.add_argument("--out-envelope", type=Path, required=True)
    parser.add_argument("--out-report", type=Path)
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--speed", type=int, choices=(1, 2, 4), default=4)
    args = parser.parse_args(argv)

    _require_new_private_output(parser, args.out_state)
    _require_new_private_output(parser, args.out_envelope)
    distinct = {
        args.source_state.resolve(),
        args.source_envelope.resolve(),
        args.out_state.resolve(),
        args.out_envelope.resolve(),
    }
    if len(distinct) != 4:
        parser.error("source and output state/envelope paths must all differ")

    source = detect_source_identity(REPOSITORY_ROOT, include_untracked=True)
    require_clean_source(source)
    require_published_source(REPOSITORY_ROOT, source)
    objective_model, model_identity = _load_ranker(
        parser,
        artifact=args.objective_model,
        integration_neutral=args.integration_neutral_ranker,
    )
    rom_path = resolve_rom_path(args.rom)
    captured = load_captured_progress(args.source_envelope, state_path=args.source_state)
    source_state_sha256 = hashlib.sha256(args.source_state.read_bytes()).hexdigest()

    try:
        with PyBoyAdapter(
            rom_path,
            watch=args.watch,
            speed=args.speed if args.watch else None,
        ) as emulator:
            report = run_first_badge_to_celadon_conductor(
                rom_path,
                state_path=args.source_state,
                captured_progress=captured,
                objective_model=objective_model,
                ranker_training_status=(
                    "authenticated_learned"
                    if model_identity["learned"] is True
                    else "integration_only_unlearned"
                ),
                _emulator=emulator,
            )
            emulator.save_state(args.out_state)
            envelope = write_captured_progress(
                args.out_envelope,
                state_path=args.out_state,
                checkpoint_id=CHECKPOINT_ID,
                checkpoint_label=CHECKPOINT_LABEL,
                checkpoints_completed=len(CELADON_JOIN_VERIFIED_OBJECTIVE_IDS),
                checkpoints_total=len(COMPLETION_QUEST),
                verified_objective_ids=CELADON_JOIN_VERIFIED_OBJECTIVE_IDS,
            )
    except FreshStartConductorError as error:
        failure = error.evidence or {
            "schema": "pokemon-red-fresh-celadon-join-failure-v1",
            "status": "failed",
            "message": str(error),
        }
        print(json.dumps(failure, ensure_ascii=True, sort_keys=True), file=sys.stderr)
        return 1

    if hashlib.sha256(args.source_state.read_bytes()).hexdigest() != source_state_sha256:
        raise RuntimeError("fresh Celadon join changed its authenticated source state")
    authenticated = load_captured_progress(args.out_envelope, state_path=args.out_state)
    if authenticated != envelope:
        raise RuntimeError("fresh Celadon capture failed its authentication reread")
    public = report.public_dict()
    public.update(
        {
            "capture": envelope.to_dict(),
            "model": model_identity,
            "source": source.public_dict(),
            "source_capture": {
                "checkpoint_id": captured.checkpoint_id,
                "state_sha256": source_state_sha256,
            },
        }
    )
    encoded = json.dumps(public, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    if args.out_report is not None:
        args.out_report.write_text(encoded, encoding="ascii")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
