#!/usr/bin/env python3
"""Run Red from clean power to a private, authenticated first-badge capture.

The normal mode authenticates an existing objective-model artifact.  The explicit
integration mode uses a zero-weight ranker only to exercise singleton semantic
dispatch; it is not a learned-policy result and cannot support a competence claim.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pokemon_red_completion.captured_progress import (  # noqa: E402
    load_captured_progress,
    write_captured_progress,
)
from pokemon_red_completion.collection_protocol import (  # noqa: E402
    collection_document_sha256,
    objective_graph_document,
)
from pokemon_red_completion.emulator import PyBoyAdapter  # noqa: E402
from pokemon_red_completion.planner_model import (  # noqa: E402
    ObjectiveRanker,
    load_objective_model_artifact,
)
from pokemon_red_completion.planner_semantics import ObjectiveFeatureProjector  # noqa: E402
from pokemon_red_completion.provenance import (  # noqa: E402
    canonical_sha256,
    detect_source_identity,
    require_clean_source,
    require_published_source,
)
from pokemon_red_completion.quest import quest_graph_payload  # noqa: E402
from pokemon_red_completion.red_fresh_start_conductor import (  # noqa: E402
    FIRST_BADGE_VERIFIED_OBJECTIVE_IDS,
    FreshStartConductorError,
    run_fresh_first_badge_conductor,
)
from pokemon_red_completion.rom import resolve_rom_path  # noqa: E402
from pokemon_red_completion.route import COMPLETION_QUEST  # noqa: E402

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
CHECKPOINT_ID = "red-first-badge-v1"
CHECKPOINT_LABEL = "Stable post-Brock control boundary"


def _outside_repository(path: Path) -> bool:
    try:
        path.resolve().relative_to(REPOSITORY_ROOT.resolve())
    except ValueError:
        return True
    return False


def _require_new_private_output(parser: argparse.ArgumentParser, path: Path) -> None:
    if not _outside_repository(path):
        parser.error("private state and envelope outputs must be outside the repository")
    if path.exists() or path.is_symlink():
        parser.error(f"refusing to overwrite existing private output: {path.name}")
    if not path.parent.is_dir() or path.parent.is_symlink():
        parser.error(f"private output parent is unavailable: {path.parent.name}")


def _load_ranker(
    parser: argparse.ArgumentParser,
    *,
    artifact: Path | None,
    integration_neutral: bool,
) -> tuple[ObjectiveRanker, dict[str, object]]:
    projector = ObjectiveFeatureProjector(COMPLETION_QUEST)
    if integration_neutral:
        model = ObjectiveRanker(
            feature_names=projector.feature_names,
            weights=[0.0] * len(projector.feature_names),
            training_seed=0,
        )
        return model, {
            "artifact_authenticated": False,
            "kind": "integration_only_zero_weight_ranker",
            "learned": False,
            "model_sha256": canonical_sha256(model.to_dict()),
        }
    if artifact is None:  # pragma: no cover - argparse's mutually exclusive group proves this
        parser.error("an objective ranker is required")
    graph_sha256 = collection_document_sha256(
        objective_graph_document(quest_graph_payload(COMPLETION_QUEST))
    )
    model = load_objective_model_artifact(
        artifact,
        expected_feature_names=projector.feature_names,
        expected_objective_graph_sha256=graph_sha256,
    )
    return model, {
        "artifact_authenticated": True,
        "artifact_manifest_sha256": hashlib.sha256(
            (artifact / "manifest.json").read_bytes()
        ).hexdigest(),
        "kind": "authenticated_objective_model",
        "learned": True,
        "model_sha256": canonical_sha256(model.to_dict()),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    ranker = parser.add_mutually_exclusive_group(required=True)
    ranker.add_argument("--objective-model", type=Path)
    ranker.add_argument("--integration-neutral-ranker", action="store_true")
    parser.add_argument("--rom", type=Path)
    parser.add_argument("--out-state", type=Path, required=True)
    parser.add_argument("--out-envelope", type=Path, required=True)
    parser.add_argument("--out-report", type=Path)
    parser.add_argument("--initial-wait-frames", type=int, default=0)
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--speed", type=int, choices=(1, 2, 4), default=4)
    args = parser.parse_args(argv)

    if not 0 <= args.initial_wait_frames <= 255:
        parser.error("--initial-wait-frames must be from zero through 255")
    _require_new_private_output(parser, args.out_state)
    _require_new_private_output(parser, args.out_envelope)
    if args.out_state.resolve() == args.out_envelope.resolve():
        parser.error("state and envelope outputs must differ")

    source = detect_source_identity(REPOSITORY_ROOT, include_untracked=True)
    require_clean_source(source)
    require_published_source(REPOSITORY_ROOT, source)
    objective_model, model_identity = _load_ranker(
        parser,
        artifact=args.objective_model,
        integration_neutral=args.integration_neutral_ranker,
    )
    rom_path = resolve_rom_path(args.rom)

    try:
        with PyBoyAdapter(
            rom_path,
            watch=args.watch,
            speed=args.speed if args.watch else None,
        ) as emulator:
            report = run_fresh_first_badge_conductor(
                rom_path,
                objective_model=objective_model,
                initial_wait_frames=args.initial_wait_frames,
                _emulator=emulator,
            )
            emulator.save_state(args.out_state)
            envelope = write_captured_progress(
                args.out_envelope,
                state_path=args.out_state,
                checkpoint_id=CHECKPOINT_ID,
                checkpoint_label=CHECKPOINT_LABEL,
                checkpoints_completed=len(FIRST_BADGE_VERIFIED_OBJECTIVE_IDS),
                checkpoints_total=len(COMPLETION_QUEST.objectives),
                verified_objective_ids=FIRST_BADGE_VERIFIED_OBJECTIVE_IDS,
            )
    except FreshStartConductorError as error:
        failure = error.evidence or {
            "schema": "pokemon-red-fresh-first-badge-failure-v1",
            "status": "failed",
            "message": str(error),
        }
        print(json.dumps(failure, ensure_ascii=True, sort_keys=True), file=sys.stderr)
        return 1

    authenticated = load_captured_progress(args.out_envelope, state_path=args.out_state)
    if authenticated != envelope:
        raise RuntimeError("fresh first-badge capture failed its authentication reread")
    public = report.public_dict()
    public.update(
        {
            "capture": envelope.to_dict(),
            "model": model_identity,
            "source": source.public_dict(),
        }
    )
    encoded = json.dumps(public, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    if args.out_report is not None:
        args.out_report.write_text(encoded, encoding="ascii")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
