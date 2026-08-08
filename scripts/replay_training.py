"""Run the Mansion training block alone, from a captured state.

This is what the capture is for. Twelve runs in one session each spent about
six minutes replaying 275 checkpoints to reach the same thirty seconds of game,
and every one was iterating on a single menu. Loading a state reaches that menu
in about a second.

It is not a substitute for a full run. A captured state is a real starting
point -- actual memory, not a fake's idea of it -- but it is *one* starting
point, and a change that works from here still has to survive the route
arriving here on its own. Iterate here, confirm with ``cli play``.

Usage::

    POKEMON_RED_ROM=<path> python scripts/replay_training.py --state <path>.state
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pokemon_red_completion.actions import MacroAction, MacroActionKind  # noqa: E402
from pokemon_red_completion.emulator import PyBoyAdapter  # noqa: E402
from pokemon_red_completion.executor import CountingExecutor, FrameSafeExecutor  # noqa: E402
from pokemon_red_completion.observation import PokemonRedStateReader  # noqa: E402
from pokemon_red_completion.opening import DEFAULT_NEW_GAME_TIMING  # noqa: E402
from pokemon_red_completion.red_party import PokemonRedPartyReader  # noqa: E402
from pokemon_red_completion.rom import resolve_rom_path  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True, help="a captured state file")
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    parser.add_argument(
        "--max-steps",
        type=int,
        default=None,
        help="shrink the policy's step budget so a spinning loop fails in seconds",
    )
    parser.add_argument(
        "--swap-only",
        action="store_true",
        help="exercise just the party swap rather than the whole training block",
    )
    parser.add_argument(
        "--out-decisions",
        type=Path,
        default=None,
        help="write portable seek/fight/flee/heal/stop teacher decisions as JSON",
    )
    parser.add_argument("--shadow-model", type=Path, default=None)
    parser.add_argument("--shadow-model-sha256", default=None)
    parser.add_argument("--out-shadow", type=Path, default=None)
    parser.add_argument(
        "--battle-control",
        action="store_true",
        help="grant the authenticated model fight/flee authority; fail closed on unsafe fights",
    )
    parser.add_argument(
        "--lineage-id",
        default=None,
        help="stable root-lineage identity required when writing decisions",
    )
    parser.add_argument(
        "--partition",
        choices=("train", "validation", "test", "unassigned"),
        default="unassigned",
        help="whole-lineage data partition",
    )
    parser.add_argument(
        "--seed-wait-frames",
        type=int,
        default=0,
        help="advance frames before saving a root; rejected if the serialized state is unchanged",
    )
    parser.add_argument(
        "--seed-walk-cycles",
        type=int,
        default=0,
        help="derive a root with bounded down-and-back movement and semantic equality checks",
    )
    parser.add_argument(
        "--out-root-state",
        type=Path,
        default=None,
        help="private state created by one seed perturbation for exact lineage replay",
    )
    parser.add_argument(
        "--root-only",
        action="store_true",
        help="derive and verify --out-root-state without running the training lesson",
    )
    args = parser.parse_args(argv)
    if args.out_decisions is not None and not args.lineage_id:
        parser.error("--lineage-id is required with --out-decisions")
    if args.seed_wait_frames < 0:
        parser.error("--seed-wait-frames must be non-negative")
    if not 0 <= args.seed_walk_cycles <= 16:
        parser.error("--seed-walk-cycles must be between zero and sixteen")
    if args.seed_wait_frames and args.seed_walk_cycles:
        parser.error("choose only one seed perturbation")
    seed_perturbation = bool(args.seed_wait_frames or args.seed_walk_cycles)
    if seed_perturbation and args.out_root_state is None:
        parser.error("--out-root-state is required with a seed perturbation")
    if args.out_root_state is not None and not seed_perturbation:
        parser.error("--out-root-state requires a positive seed perturbation")
    if args.out_root_state is not None and args.out_root_state.resolve() == args.state.resolve():
        parser.error("--out-root-state must not overwrite the input state")
    if args.root_only and not seed_perturbation:
        parser.error("--root-only requires a seed perturbation and --out-root-state")
    shadow_values = (args.shadow_model, args.shadow_model_sha256, args.out_shadow)
    if any(value is not None for value in shadow_values) and not all(
        value is not None for value in shadow_values
    ):
        parser.error("shadow mode requires --shadow-model, --shadow-model-sha256, and --out-shadow")
    if args.out_shadow is not None and args.out_decisions is None:
        parser.error("shadow mode requires --out-decisions and its lineage provenance")
    if args.battle_control and args.shadow_model is None:
        parser.error("--battle-control requires the authenticated model/output bundle")

    shadow = None
    decision_authority = None
    if args.shadow_model is not None:
        from pokemon_red_completion.training_control_model import (
            TrainingControlShadowAudit,
            load_training_control_model,
        )

        model = load_training_control_model(
                args.shadow_model,
                expected_sha256=args.shadow_model_sha256,
            )
        shadow = TrainingControlShadowAudit(model)
        if args.battle_control:
            from pokemon_red_completion.training_control import TrainingControlPhase

            def decision_authority(decision):
                assert shadow is not None
                shadow.observe(decision)
                if decision.observation.phase is TrainingControlPhase.BATTLE:
                    return model.predict(decision.observation)
                return decision.action

    emulator = PyBoyAdapter(resolve_rom_path(args.rom))
    emulator.start()
    try:
        emulator.load_state(args.state)
        reader = PokemonRedStateReader(emulator)
        actions = CountingExecutor(
            FrameSafeExecutor(emulator, DEFAULT_NEW_GAME_TIMING.controller_timing())
        )
        party_reader = PokemonRedPartyReader(emulator)
        collection_state = args.state
        if seed_perturbation:
            before_semantics = _collection_semantics(reader, party_reader)
            if args.seed_wait_frames:
                actions.execute(MacroAction(MacroActionKind.WAIT, args.seed_wait_frames))
            else:
                for _ in range(args.seed_walk_cycles):
                    actions.execute(MacroAction(MacroActionKind.MOVE, "down"))
                    actions.execute(MacroAction(MacroActionKind.WAIT, 60))
                    actions.execute(MacroAction(MacroActionKind.MOVE, "up"))
                    actions.execute(MacroAction(MacroActionKind.WAIT, 60))
            after_semantics = _collection_semantics(reader, party_reader)
            if after_semantics != before_semantics:
                raise RuntimeError(
                    "seed perturbation did not return to the same semantic checkpoint"
                )
            assert args.out_root_state is not None
            emulator.save_state(args.out_root_state)
            if _sha256(args.out_root_state) == _sha256(args.state):
                raise RuntimeError(
                    "seed perturbation left the serialized root unchanged; "
                    "this cannot count as an independent lineage"
                )
            collection_state = args.out_root_state
            print(
                "saved a semantically equivalent, serialized-distinct collection root",
                flush=True,
            )
        provenance = (
            _collection_provenance(collection_state, args.lineage_id, args.partition)
            if args.out_decisions is not None
            else None
        )
        raw = reader.read()
        party = party_reader.read()
        print(f"resumed on map {raw.map_id} at {(raw.player_x, raw.player_y)!r}")
        described = tuple(
            f"{hex(species)}@{level}"
            for species, level in zip(party.species_ids(), party.levels, strict=True)
        )
        print(f"party: {described}")

        if args.root_only:
            return 0
        if args.swap_only:
            return _replay_swap(actions, reader, emulator, party_reader)
        return _replay_training(
            actions,
            reader,
            emulator,
            args.max_steps,
            args.out_decisions,
            provenance,
            shadow,
            args.out_shadow,
            args.shadow_model_sha256,
            decision_authority,
            args.battle_control,
        )
    finally:
        emulator.close()


def _step_into_the_field(actions, reader) -> None:
    """Leave the tile the capture happens to have stopped on.

    "Returned safely from Mansion" leaves the player at the Cinnabar nurse,
    facing her, where opening the menu feeds her dialogue instead. The real
    run never swaps from there -- heal_and_return walks away first -- so the
    harness does the same rather than pretending the position is neutral.
    """

    for _ in range(4):
        actions.execute(MacroAction(MacroActionKind.CANCEL, None))
        actions.execute(MacroAction(MacroActionKind.WAIT, 30))
    for _ in range(2):
        actions.execute(MacroAction(MacroActionKind.MOVE, "down"))
        actions.execute(MacroAction(MacroActionKind.WAIT, 60))
    raw = reader.read()
    print(f"stepped clear of the nurse to {(raw.player_x, raw.player_y)!r}")


def _replay_swap(actions, reader, emulator, party_reader) -> int:
    """Swap the party's first two slots and report what happened.

    The narrowest possible exercise of the menu that has cost the most runs.
    """

    from pokemon_red_completion.red_team_training import swap_field_party_slots

    _step_into_the_field(actions, reader)

    before = party_reader.read().species_ids()
    print(f"\nswapping slots 1 and 2 of {tuple(hex(s) for s in before)}")
    try:
        swap_field_party_slots(
            actions,
            reader,
            emulator,
            first_index=0,
            second_index=1,
            label="replay swap",
            hideout_timing=None,
        )
    except Exception as error:  # noqa: BLE001 - the failure is the output
        print(f"\nFAILED: {error}")
        return 1
    after = party_reader.read().species_ids()
    print(f"result: {tuple(hex(s) for s in after)}")
    swapped = after[0] == before[1] and after[1] == before[0]
    print("swap succeeded" if swapped else "swap did not do what was asked")
    return 0 if swapped else 1


def _replay_training(
    actions,
    reader,
    emulator,
    max_steps: int | None,
    out_decisions: Path | None,
    provenance: dict[str, object] | None,
    shadow,
    out_shadow: Path | None,
    model_artifact_sha256: str | None,
    decision_authority,
    battle_control: bool,
) -> int:
    """Run the Mansion evolution and balancing blocks exactly as Blaine does."""

    from dataclasses import replace

    from pokemon_red_completion import blaine

    policy = blaine.MANSION_TEAM_POLICY
    if max_steps is not None:
        policy = replace(policy, max_steps=max_steps)

    party_reader = PokemonRedPartyReader(emulator)
    evolution_decisions = []
    balance_decisions = []

    def record_evolution(decision) -> None:
        evolution_decisions.append(decision)
        if shadow is not None and decision_authority is None:
            shadow.observe(decision)

    def record_balance(decision) -> None:
        balance_decisions.append(decision)
        if shadow is not None and decision_authority is None:
            shadow.observe(decision)

    def note(message: str) -> None:
        levels = party_reader.read().levels
        print(f"  {message} | levels={levels}", flush=True)

    print("\nrunning the Mansion development blocks", flush=True)
    try:
        development = blaine.plan_team_development(
            party_reader.read(), blaine.MANSION_DEVELOPMENT_POLICY
        )
        evolution_battles = 0
        evolution_heals = 0
        if development.directive is blaine.TeamTrainingDirective.EVOLVE_MEMBER:
            print("\nrunning participation-based Diglett evolution", flush=True)
            _, evolution_battles, evolution_heals = blaine.run_red_team_balancing(
                actions,
                reader,
                emulator,
                policy=policy,
                venues=(
                    blaine.ROUTE_11_TRAINING_VENUE,
                    blaine.DIGLETTS_CAVE_TRAINING_VENUE,
                    blaine.MANSION_TRAINING_VENUE,
                ),
                intent=blaine.MANSION_BALANCED_TEAM_TRAINING_INTENT,
                flee_timing=blaine.MANSION_TRAINING_FLEE_TIMING,
                hideout_timing=blaine.DEFAULT_HIDEOUT_TIMING,
                flee_func=blaine._flee,
                volatile_enemy_species=blaine.MANSION_VOLATILE_ENEMY_SPECIES,
                escort_enemy_species=blaine.MANSION_ESCORT_ENEMY_SPECIES,
                max_consecutive_flees=blaine.MANSION_MAX_CONSECUTIVE_FLEES,
                cancel_interval=blaine.MANSION_LEVEL_UP_MOVE_CANCEL_INTERVAL,
                evolution_target=(blaine.DIGLETT_SPECIES_ID, blaine.DUGTRIO_SPECIES_ID),
                decision_sink=record_evolution,
                decision_authority=decision_authority,
                report_label="replay evolution",
                checkpoint_count=blaine.BLAINE_CHECKPOINT_COUNT,
            )
        print("\nrunning the Mansion balancing block", flush=True)
        report, battles, heals = blaine.run_red_team_balancing(
            actions,
            reader,
            emulator,
            policy=policy,
            venues=(
                blaine.ROUTE_11_TRAINING_VENUE,
                blaine.DIGLETTS_CAVE_TRAINING_VENUE,
                blaine.MANSION_TRAINING_VENUE,
            ),
            intent=blaine.MANSION_BALANCED_TEAM_TRAINING_INTENT,
            flee_timing=blaine.MANSION_TRAINING_FLEE_TIMING,
            hideout_timing=blaine.DEFAULT_HIDEOUT_TIMING,
            flee_func=blaine._flee,
            volatile_enemy_species=blaine.MANSION_VOLATILE_ENEMY_SPECIES,
            escort_enemy_species=blaine.MANSION_ESCORT_ENEMY_SPECIES,
            max_consecutive_flees=blaine.MANSION_MAX_CONSECUTIVE_FLEES,
            cancel_interval=blaine.MANSION_LEVEL_UP_MOVE_CANCEL_INTERVAL,
            progress_sink=note,
            decision_sink=record_balance,
            decision_authority=decision_authority,
            report_label="replay training",
            checkpoint_count=blaine.BLAINE_CHECKPOINT_COUNT,
        )
    except Exception as error:  # noqa: BLE001 - the failure is the output
        _write_decisions(
            out_decisions,
            status="failed",
            evolution=evolution_decisions,
            balance=balance_decisions,
            error=f"{type(error).__name__}: {error}",
            provenance=provenance,
        )
        _write_shadow(
            out_shadow,
            shadow,
            status="failed",
            error=f"{type(error).__name__}: {error}",
            provenance=provenance,
            model_artifact_sha256=model_artifact_sha256,
            battle_control=battle_control,
        )
        print(f"\nFAILED: {type(error).__name__}: {error}")
        traceback.print_exc(limit=3)
        return 1
    print(
        f"\nfinished: evolution_battles={evolution_battles}, "
        f"evolution_healing_trips={evolution_heals}, "
        f"balance_battles={battles}, balance_healing_trips={heals}, report={report}"
    )
    _write_decisions(
        out_decisions,
        status="ok",
        evolution=evolution_decisions,
        balance=balance_decisions,
        provenance=provenance,
    )
    _write_shadow(
        out_shadow,
        shadow,
        status="ok",
        provenance=provenance,
        model_artifact_sha256=model_artifact_sha256,
        battle_control=battle_control,
    )
    return 0


def _write_shadow(
    path: Path | None,
    shadow,
    *,
    status: str,
    provenance: dict[str, object] | None,
    model_artifact_sha256: str | None,
    battle_control: bool,
    error: str | None = None,
) -> None:
    if path is None:
        return
    if shadow is None or provenance is None or model_artifact_sha256 is None:
        raise RuntimeError("shadow output lacks authenticated model or lineage provenance")
    payload = shadow.public_dict()
    payload.update(
        {
            "status": status,
            "error": error,
            "provenance": provenance,
            "model_artifact_sha256": model_artifact_sha256,
            "model_had_execution_authority": battle_control,
            "authority_phases": ["battle"] if battle_control else [],
            "teacher_fallback_on_model_disagreement": False if battle_control else None,
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)
    print(f"wrote shadow audit for {shadow.decisions} decisions to {path}", flush=True)


def _write_decisions(
    path: Path | None,
    *,
    status: str,
    evolution: list,
    balance: list,
    error: str | None = None,
    provenance: dict[str, object] | None,
) -> None:
    """Persist even a failed rehearsal so useful supervision is not discarded."""

    if path is None:
        return
    from pokemon_red_completion.training_control import (
        TRAINING_CONTROL_FEATURE_NAMES,
        TRAINING_CONTROL_FEATURE_SCHEMA_ID,
    )

    payload = {
        "schema": "pokemon-training-control-replay-v2",
        "status": status,
        "feature_schema_id": TRAINING_CONTROL_FEATURE_SCHEMA_ID,
        "feature_names": list(TRAINING_CONTROL_FEATURE_NAMES),
        "error": error,
        "provenance": provenance,
        "segments": {
            "evolution": [decision.public_dict() for decision in evolution],
            "balance": [decision.public_dict() for decision in balance],
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)
    print(
        f"wrote {len(evolution) + len(balance)} portable training decisions to {path}",
        flush=True,
    )


def _collection_provenance(
    state: Path,
    lineage_id: str,
    partition: str,
) -> dict[str, object]:
    """Bind a stream to its root state and exact committed source."""

    repository = Path(__file__).resolve().parent.parent
    try:
        commit = subprocess.run(
            ("git", "rev-parse", "HEAD"),
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ("git", "status", "--porcelain", "--untracked-files=no"),
                cwd=repository,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise RuntimeError("could not bind training collection to Git source") from error
    state_sha256 = hashlib.sha256(state.read_bytes()).hexdigest()
    return {
        "lineage_id": lineage_id,
        "partition": partition,
        "source_commit": commit,
        "source_dirty": dirty,
        "state_sha256": state_sha256,
    }


def _collection_semantics(
    reader: PokemonRedStateReader,
    party_reader: PokemonRedPartyReader,
) -> tuple[object, ...]:
    """Capture facts that a root perturbation is not allowed to change."""

    raw = reader.read()
    return (raw.map_id, raw.player_x, raw.player_y, raw.battle_state, party_reader.read())


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
