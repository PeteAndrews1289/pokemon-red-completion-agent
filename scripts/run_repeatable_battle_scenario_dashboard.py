#!/usr/bin/env python3
"""Show live, view-only progress for Red battle scenario materialization."""

from __future__ import annotations

import argparse
import json
import sys
import time
import webbrowser
from collections.abc import Mapping
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pokemon_red_completion.progress_dashboard import (  # noqa: E402
    DashboardExperimentState,
    DashboardModelState,
    DashboardSnapshot,
    DashboardState,
    ProgressDashboardError,
    ProgressDashboardServer,
)

DEFAULT_PORT = 8768


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--progress", type=Path, required=True)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--duration-seconds", type=int, default=0)
    parser.add_argument("--no-browser", action="store_true")
    return parser


def repeatable_battle_materialization_snapshot(
    progress: Mapping[str, object],
) -> DashboardSnapshot:
    if progress.get("schema") != "pokemon.red.battle.repeatable-materialization-progress.v1":
        raise ProgressDashboardError("repeatable battle progress schema is invalid")
    total = _count(progress, "total")
    pending = _count(progress, "pending")
    started = _count(progress, "started")
    succeeded = _count(progress, "succeeded")
    failed = _count(progress, "failed")
    completed = _count(progress, "completed")
    if total < 1 or pending + started + succeeded + failed != total:
        raise ProgressDashboardError("repeatable battle progress counts differ")
    if completed != started + succeeded + failed:
        raise ProgressDashboardError("repeatable battle completion count differs")
    if pending:
        run_status = "running" if completed else "waiting"
        message = "Creating natural Red battle starts; no model choices or outcomes yet."
    elif started:
        run_status = "paused"
        message = "A power-loss terminal was retained; completed work will not be replayed."
    elif failed:
        run_status = "failed"
        message = "Materialization finished with quarantined failures; outcomes remain unopened."
    else:
        run_status = "passed"
        message = "Every frozen scenario was materialized; outcome collection is the next gate."
    plan_sha256 = _digest(progress, "plan_sha256")
    catalog_sha256 = _digest(progress, "source_catalog_sha256")
    source_commit = _commit(progress, "materializer_source_commit")
    partition = progress.get("partition")
    if partition not in {"train", "development"}:
        raise ProgressDashboardError("repeatable battle partition is invalid")
    return DashboardSnapshot(
        game="Pokemon Red battle learner",
        run_status=run_status,
        stage="Natural battle-scenario materialization",
        message=message,
        stage_progress=completed / total,
        location=f"Red · {partition} partition · Crystal deferred",
        collection_target=151,
        model=DashboardModelState(
            mode="waiting",
            candidate="No new model fit",
            choice="Materialization only · move authority locked",
            decisions=0,
            teacher_queries=_count(progress, "teacher_queries"),
            fallbacks=0,
        ),
        experiment=DashboardExperimentState(
            phase="training",
            zero_shot_completed=succeeded,
            zero_shot_total=total,
            adaptation_completed=completed,
            adaptation_total=total,
            sealed_completed=0,
            sealed_total=total,
            predictions_committed=False,
            heading="Red battle curriculum",
            eyebrow="Natural cartridge scenarios",
            counter_labels=(
                "Materialized scenarios",
                "Terminal assignments",
                "Outcomes collected",
            ),
        ),
        events=(
            f"Frozen plan · {plan_sha256[:12]}…",
            f"Source catalog · {catalog_sha256[:12]}…",
            f"Published source · {source_commit[:12]}…",
            f"Progress · {completed}/{total} terminal · {pending} pending",
            f"Results · {succeeded} succeeded · {failed} failed · {started} interrupted",
            "Coverage · 8 source lineages · 3 party menus · 3 wild venues",
            "Current operation · restore → route → wait → encounter → switch → verify MAIN",
            "Model effects · predictions 0 · fits 0 · outcomes 0 · authority 0",
            "Safety · memory edits 0 · teacher queries 0 · private paths hidden",
            "Next gate · train outcomes → shadow fit → commit development predictions",
            "Falsifier · learned scorer must beat the strongest legal fixed-power heuristic",
            "Mission · bounded Red competence first; living Pokédex and Crystal remain downstream",
        ),
    )


def _read_progress(path: Path) -> Mapping[str, object]:
    try:
        value = json.loads(path.read_text("ascii"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise ProgressDashboardError("repeatable battle progress is unavailable") from None
    if not isinstance(value, dict):
        raise ProgressDashboardError("repeatable battle progress must be an object")
    return value


def _count(value: Mapping[str, object], name: str) -> int:
    result = value.get(name)
    if type(result) is not int or result < 0:  # noqa: E721
        raise ProgressDashboardError(f"repeatable battle {name} is invalid")
    return result


def _digest(value: Mapping[str, object], name: str) -> str:
    result = value.get(name)
    if (
        not isinstance(result, str)
        or len(result) != 64
        or any(character not in "0123456789abcdef" for character in result)
    ):
        raise ProgressDashboardError(f"repeatable battle {name} is invalid")
    return result


def _commit(value: Mapping[str, object], name: str) -> str:
    result = value.get(name)
    if (
        not isinstance(result, str)
        or len(result) != 40
        or any(character not in "0123456789abcdef" for character in result)
    ):
        raise ProgressDashboardError(f"repeatable battle {name} is invalid")
    return result


def main() -> int:
    args = _parser().parse_args()
    if args.duration_seconds < 0:
        raise ProgressDashboardError("dashboard duration must be non-negative")
    initial = repeatable_battle_materialization_snapshot(_read_progress(args.progress))
    state = DashboardState(initial)
    with ProgressDashboardServer(state, port=args.port) as dashboard:
        print(
            json.dumps(
                {
                    "schema": "pokemon.red.battle.repeatable-materialization-dashboard.v1",
                    "url": dashboard.url,
                    "view_only": True,
                    "controller_endpoints": 0,
                    "private_path_fields": 0,
                },
                sort_keys=True,
            ),
            flush=True,
        )
        if not args.no_browser:
            webbrowser.open(dashboard.url)
        started = time.monotonic()
        previous = initial
        try:
            while args.duration_seconds == 0 or time.monotonic() - started < args.duration_seconds:
                time.sleep(0.5)
                latest = repeatable_battle_materialization_snapshot(
                    _read_progress(args.progress)
                )
                if latest != previous:
                    state.publish(latest)
                    previous = latest
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
