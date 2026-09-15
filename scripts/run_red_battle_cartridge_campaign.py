#!/usr/bin/env python3
"""Run one prospectively frozen V2 Red cartridge qualification campaign."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pokemon_red_completion.collection_protocol import (  # noqa: E402
    committed_source_bundle_sha256,
)
from pokemon_red_completion.emulator import PyBoyAdapter  # noqa: E402
from pokemon_red_completion.private_artifacts import open_private_root  # noqa: E402
from pokemon_red_completion.provenance import (  # noqa: E402
    detect_source_identity,
    require_clean_source,
    require_published_source,
)
from pokemon_red_completion.red_battle_cartridge_campaign import (  # noqa: E402
    RedBattleCartridgeCampaignError,
    execute_durable_red_battle_cartridge_campaign,
    parse_red_battle_cartridge_campaign,
)
from pokemon_red_completion.red_battle_cartridge_qualification import (  # noqa: E402
    qualify_repeatable_red_wild_battle,
)
from pokemon_red_completion.rom import resolve_rom_path, verify_rom  # noqa: E402

_MAXIMUM_STATE_BYTES = 64 * 1024 * 1024


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-plan", type=Path, required=True)
    parser.add_argument("--expected-plan-sha256", required=True)
    parser.add_argument("--source-state", type=Path, required=True)
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    parser.add_argument("--qualification-ci-run-id", type=int, required=True)
    parser.add_argument("--allow-same-device-private-root", action="store_true")
    return parser


def _run(args: argparse.Namespace) -> dict[str, object]:
    plan_payload = _read(args.private_plan, maximum_bytes=64 * 1024)
    plan = parse_red_battle_cartridge_campaign(plan_payload)
    if plan.sha256 != args.expected_plan_sha256:
        raise RedBattleCartridgeCampaignError("campaign plan digest differs")
    if plan.qualification_ci_run_id != args.qualification_ci_run_id:
        raise RedBattleCartridgeCampaignError("qualification CI run differs")
    identity = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_clean_source(identity)
    require_published_source(PROJECT_ROOT, identity)
    if identity.git_commit != plan.source_commit:
        raise RedBattleCartridgeCampaignError("published source commit differs")
    if committed_source_bundle_sha256(PROJECT_ROOT) != plan.source_bundle_sha256:
        raise RedBattleCartridgeCampaignError("published source bundle differs")
    state = _read(args.source_state, maximum_bytes=_MAXIMUM_STATE_BYTES)
    if hashlib.sha256(state).hexdigest() != plan.source.state_sha256:
        raise RedBattleCartridgeCampaignError("source state digest differs")
    rom_path = resolve_rom_path(args.rom)
    rom = verify_rom(rom_path)
    if rom.sha256 != plan.rom_sha256:
        raise RedBattleCartridgeCampaignError("ROM digest differs")
    rom_bytes = rom_path.read_bytes()
    store = open_private_root(
        args.private_root,
        repository_root=PROJECT_ROOT,
        allow_same_device=args.allow_same_device_private_root,
    )

    def session_factory() -> PyBoyAdapter:
        return PyBoyAdapter(rom_path, watch=False, speed=None)

    def run_case(case, assignment, campaign):  # type: ignore[no-untyped-def]
        return qualify_repeatable_red_wild_battle(
            store,
            case.episode_id,
            plan.source,
            assignment,
            state,
            rom_bytes=rom_bytes,
            materializer_source_commit=plan.source_commit,
            session_factory=session_factory,
            limits=plan.case_limits,
            campaign=campaign,
            maximum_encounter_steps=plan.maximum_encounter_steps,
        )

    return execute_durable_red_battle_cartridge_campaign(store, plan, run_case)


def _read(path: Path, *, maximum_bytes: int) -> bytes:
    try:
        size = path.stat().st_size
        if not 1 <= size <= maximum_bytes:
            raise RedBattleCartridgeCampaignError("private input size is invalid")
        return path.read_bytes()
    except OSError:
        raise RedBattleCartridgeCampaignError("private input is unavailable") from None


def main(argv: list[str] | None = None) -> int:
    result = _run(_parser().parse_args(argv))
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "passed_with_declared_coverage_gaps" else 1


if __name__ == "__main__":
    raise SystemExit(main())
