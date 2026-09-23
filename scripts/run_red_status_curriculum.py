"""One bounded status-move experiment on existing TRAIN laboratory origins.

Holdouts are withheld configurations, NOT new independent roots or a promotion.
Never loads campaign saves. One fit; terminal outcomes and failures are retained.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import subprocess
from contextlib import contextmanager
from dataclasses import asdict, replace
from pathlib import Path
from statistics import fmean

import run_fresh_red_trainer_curriculum as common
from run_red_trainer_practice_model import retained_session

from pokemon_red_completion.battle_actions import BattleAction
from pokemon_red_completion.battle_practice_factory import BattlePracticeSpec
from pokemon_red_completion.battle_scenario_capture import (
    OBSERVATION_SCHEMA_V2,
    build_battle_scenario_capture_payload,
    open_battle_scenario_capture,
)
from pokemon_red_completion.battle_semantics import BattleFeatureProjector
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.executor import ControllerActionLimiter, FrameSafeExecutor
from pokemon_red_completion.observation import PokemonRedStateReader
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_battle_catalog import PokemonRedBattleCatalog, pokemon_red_move_ref
from pokemon_red_completion.red_battle_practice_cartridge import RedPracticeCartridge
from pokemon_red_completion.red_battle_practice_factory import materialize_red_train_practice
from pokemon_red_completion.red_battle_scenario import prepare_red_battle_scenario
from pokemon_red_completion.red_status_battle_features import (
    STATUS_MOVE_NAMES,
    STATUS_MOVE_SCHEMA,
    expand_frozen_move,
    project_status_moves,
)
from pokemon_red_completion.red_status_practice import (
    StatusPracticeConditions,
    condition_train_status,
)
from pokemon_red_completion.red_status_trajectory_capture import (
    TrajectoryCaptureSink,
    validate_capture_indices,
)
from pokemon_red_completion.red_trainer_practice_counterfactual import (
    TrainerPracticeFirstChoice,
    _FirstChoicePolicy,
)
from pokemon_red_completion.red_trainer_practice_episode import run_red_trainer_practice_episode
from pokemon_red_completion.red_trainer_practice_fit import TrainerPracticeThreeHeadModel
from pokemon_red_completion.red_trainer_practice_head import TrainerHeadExample, TrainerHeadModel
from pokemon_red_completion.red_trainer_practice_log import (
    TrainerPracticeEventLog,
    verify_trainer_practice_event_log,
)
from pokemon_red_completion.red_trainer_practice_outcome_policy import (
    RedTrainerPracticeOutcomePolicy,
)
from pokemon_red_completion.red_trainer_practice_returns import tied_best_indices
from pokemon_red_completion.red_trajectory import PokemonRedObservationEncoder
from pokemon_red_completion.scenario_lab import ScenarioPartition

ROOT = Path(__file__).resolve().parents[1]
K_SHA = "e626e3435d1aa75654593535acf0e5e52a7eb7430481217a80aff3a53c191472"
SEED = 2026092105
OFFSETS = (0, 4, 8)
FAMILIES = {
    "sleep": 79,
    "paralysis": 86,
    "poison": 77,
    "confusion": 109,
    "accuracy": 28,
    "disable": 50,
    "heal": 105,
    "rest": 156,
}


def write(path, data):
    with path.open("xb") as handle:
        handle.write(
            data
            if isinstance(data, bytes)
            else (json.dumps(data, sort_keys=True, indent=2) + "\n").encode()
        )


class DamageContinuation(RedTrainerPracticeOutcomePolicy):
    """Fixed K damage continuation; first-action credit includes delayed effects."""

    def choose_main(self, observation, prepared):
        category = prepared.features.feature_names.index("move.category.status")
        mask = tuple(
            legal and row[category] == 0
            for legal, row in zip(
                prepared.features.legal_mask, prepared.features.candidate_vectors, strict=True
            )
        )
        if not any(mask):
            raise ValueError("measured continuation exhausted its declared damaging moves")
        narrowed = replace(prepared, features=replace(prepared.features, legal_mask=mask))
        return super().choose_main(observation, narrowed)


def recipes(cartridge, *, seed=SEED):
    """Prospective mechanics-derived recipes; no failed campaign identity inputs."""
    catalog, rng = PokemonRedBattleCatalog(), random.Random(seed)
    rows = []
    for family, status_move in FAMILIES.items():
        for variant in range(4):
            level = (32, 40, 48, 36)[variant]
            available = {}
            for species in cartridge.species_ids:
                moves = cartridge.species(species).teachable_moves_at_level(level)
                damage = [
                    m
                    for m in moves
                    if catalog.recovery_attack_supported(pokemon_red_move_ref(m))
                    and 35 <= catalog.resolve_move(pokemon_red_move_ref(m)).power <= 95
                ]
                if len(damage) >= 2:
                    available[species] = damage
            actors = [
                s
                for s in available
                if status_move in cartridge.species(s).teachable_moves_at_level(level)
            ]
            actor = rng.choice(sorted(actors))
            enemy = rng.choice(sorted(available))
            actor_moves = rng.sample(available[actor], 2) + [status_move]
            rng.shuffle(actor_moves)
            enemy_moves = rng.sample(available[enemy], 2)
            actor_data, enemy_data = cartridge.species(actor), cartridge.species(enemy)
            hp = actor_data.neutral_stats(level).max_hp
            ehp = enemy_data.trainer_stats(level).max_hp
            condition = StatusPracticeConditions(
                player_status=("burn", "poison", "paralysis", "none")[variant]
                if family == "rest"
                else "none",
                opponent_status="paralysis"
                if variant == 1 and family in {"sleep", "paralysis", "poison"}
                else "none",
                player_accuracy=-3 if family == "accuracy" and variant == 2 else 0,
                opponent_accuracy=-6 if family == "accuracy" and variant == 1 else 0,
                disabled_slot=1 if family == "disable" and variant == 2 else None,
            )

            def moves(ids):
                return [
                    {
                        "move_ref": pokemon_red_move_ref(m),
                        "pp": catalog.resolve_move(pokemon_red_move_ref(m)).max_pp,
                    }
                    for m in ids
                ]

            rows.append(
                {
                    "id": f"{family}-{variant}",
                    "family": family,
                    "role": "holdout" if variant == 3 else "train",
                    "conditions": asdict(condition),
                    "practice": {
                        "actor_species_ref": f"pokemon.red.gb.us.rev0:species:{actor:03d}",
                        "actor_national_number": actor_data.national_number,
                        "actor_level": level,
                        "actor_moves": moves(actor_moves),
                        "actor_hp": max(1, hp * (40 if variant % 2 == 0 else 100) // 100),
                        "opponent_species_ref": f"pokemon.red.gb.us.rev0:species:{enemy:03d}",
                        "opponent_national_number": enemy_data.national_number,
                        "opponent_level": level,
                        "opponent_moves": moves(enemy_moves),
                        "opponent_hp": ehp if variant != 1 else max(1, ehp // 5),
                        "opponent_party_count": 1,
                        "battle_kind": "trainer",
                        "partition": "train",
                    },
                }
            )
    return rows


def materialize(args, row, index, sources, cartridge, commit):
    if "source_index" in row:
        if (type(row["source_index"]) is not int or not 0 <= row["source_index"] < len(sources)
                or row.get("root") != sources[row["source_index"]][1]["source_id"]):
            raise ValueError("explicit TRAIN root assignment differs")
        index = row["source_index"]
    directory = args.output / row["id"]
    directory.mkdir(mode=0o700)
    source, receipt = sources[index % len(sources)]
    capture = open_battle_scenario_capture(source / "source.state", source / "source.state.json")
    spec = BattlePracticeSpec.from_dict(
        {
            **row["practice"],
            "root_lineage_id": receipt["source_id"],
            "source_state_sha256": capture.manifest.state_sha256,
        }
    )
    with PyBoyAdapter(args.rom, watch=False, speed=None) as emulator:
        emulator.load_state_bytes(capture.state_bytes)
        reader = PokemonRedStateReader(emulator)
        encoder = PokemonRedObservationEncoder.from_state_reader(
            reader, include_battle_stats=True, public_species_base_stats=cartridge.public_base_stats
        )
        if (
            prepare_red_battle_scenario(
                encoder, reader.read(), allow_no_attack=True
            ).initial_observation_sha256
            != capture.manifest.initial_observation_sha256
        ):
            raise ValueError("source observation differs")
        frame = emulator.frame_count
        memory = emulator._require_backend().memory  # teacher-only isolated setup
        setup = materialize_red_train_practice(reader, memory, spec, cartridge=cartridge)
        intervention = condition_train_status(
            reader,
            memory,
            StatusPracticeConditions(**row["conditions"]),
            partition=ScenarioPartition.TRAIN,
        )
        effect_intervention = None
        if "effect_conditions" in row:
            from pokemon_red_completion.red_status_practice import condition_train_effect_state
            effect_intervention = condition_train_effect_state(
                reader, memory, partition=ScenarioPartition.TRAIN, **row["effect_conditions"])
        if emulator.frame_count != frame:
            raise ValueError("setup advanced frames")
        raw = reader.read()
        state = emulator.save_state_bytes()
        obs_sha = canonical_sha256(encoder.snapshot_from_raw(raw).to_dict())
        manifest = build_battle_scenario_capture_payload(
            capture_id=f"status-{row['id']}-{hashlib.sha256(state).hexdigest()[:12]}",
            root_lineage_id=receipt["source_id"],
            partition=ScenarioPartition.TRAIN,
            state_bytes=state,
            initial_observation_sha256=obs_sha,
            source_commit=commit,
            expected_map=raw.map_id,
            expected_battle_state=2,
            source_state_sha256=capture.manifest.state_sha256,
            observation_schema=OBSERVATION_SCHEMA_V2,
        )
        write(directory / "capture.state", state)
        write(directory / "capture.state.json", manifest)
        write(
            directory / "setup.json",
            {
                "recipe": row,
                "configuration_sha256": spec.configuration_sha256,
                "intervention": intervention,
                **({"effect_intervention": effect_intervention} if effect_intervention else {}),
                "source_manifest_sha256": capture.manifest_sha256,
                "source_sha256": capture.manifest.state_sha256,
                "root": receipt["source_id"],
                "legal_moves": setup.legal_move_count,
            },
        )
    return open_battle_scenario_capture(
        directory / "capture.state", directory / "capture.state.json"
    )


def play(
    args, capture, model, output, cartridge, *, first_slot=None, offset=0, horizon=None,
    status=True, learner_continuation=False, capture_decisions=(), capture_source_commit=None,
    damage_only=False,
):
    if capture_decisions:
        validate_capture_indices(capture_decisions, capture)
        if not status or first_slot is not None or capture_source_commit is None:
            raise ValueError("trajectory snapshots require an unforced status learner")
    output.mkdir(mode=0o700)
    if damage_only and learner_continuation:
        raise ValueError("damage-only teacher and status learner modes cannot be combined")
    policy_type = (DamageContinuation if damage_only or
                   (first_slot is not None and not learner_continuation)
                   else RedTrainerPracticeOutcomePolicy)
    policy = policy_type("status-experiment", capture.manifest.capture_id, model)
    if first_slot is not None:
        policy = _FirstChoicePolicy(
            TrainerPracticeFirstChoice(BattleAction.move(first_slot)), policy
        )
    log = TrainerPracticeEventLog(
        output / "events",
        run_identity={
            "capture_id": capture.manifest.capture_id,
            "root": capture.manifest.root_lineage_id,
            "partition": "train",
            "model_sha256": canonical_sha256(model.to_dict()),
            "first_slot": first_slot,
            "offset": offset,
            "horizon": horizon,
            "allow_status_moves": status,
            "actor_memory_writes": 0,
            **({"damage_only_teacher": True} if damage_only else {}),
            **({"learner_continuation": True} if learner_continuation else {}),
            **({"capture_decisions": capture_decisions,
                "capture_source_commit": capture_source_commit} if capture_decisions else {}),
        },
    )

    active = {}

    class Actions:
        def execute(self, action):
            return active["limiter"].execute(action)

    @contextmanager
    def session():
        with (
            PyBoyAdapter(args.rom, watch=False, speed=None) as emulator,
            retained_session(
                emulator,
                maximum_frames=120000,
                output=output,
                maximum_controller_actions=5000,
                maximum_wall_seconds=45,
            ) as retained,
        ):
            active["emulator"] = emulator
            active["limiter"] = ControllerActionLimiter(
                FrameSafeExecutor(retained), maximum_actions=5000,
                admit_action=retained.check_wall_time_budget)
            yield retained

    def snapshot():
        emulator = active["emulator"]
        reader = PokemonRedStateReader(emulator)
        raw = reader.read()
        encoder = PokemonRedObservationEncoder(reader, True, cartridge.public_base_stats)
        return {"state_bytes": emulator.save_state_bytes(), "map_id": raw.map_id,
                "battle_state": raw.battle_state,
                "initial_observation_sha256": prepare_red_battle_scenario(
                    encoder, raw, allow_no_attack=True).initial_observation_sha256,
                "policy_observation": replace(encoder, include_status_context=True
                                               ).snapshot_from_raw(raw).to_dict()}

    sink = (TrajectoryCaptureSink(parent=capture, directory=output / "snapshots",
            indices=capture_decisions, source_commit=capture_source_commit, log=log,
            snapshot=snapshot) if capture_decisions else log.emit)

    try:
        episode = run_red_trainer_practice_episode(
            capture,
            session_factory=session,
            policy=policy,
            max_decisions=80,
            max_player_turns=horizon,
            opening_idle_frames=offset,
            event_sink=sink,
            public_species_base_stats=cartridge.public_base_stats,
            allow_status_moves=status,
            action_executor=Actions(),
        )
        result = episode.public_dict()
        write(output / "episode.json", result)
        log.finish({"episode_sha256": canonical_sha256(result), "stop_reason": episode.stop_reason})
        verify_trainer_practice_event_log(output / "events")
        if episode.stop_reason not in {"battle_won", "party_defeated", "player_turn_budget"}:
            raise ValueError(f"unsupported stop {episode.stop_reason}")
        return result
    except Exception as error:
        if not log.closed:
            log.fail(error)
        write(output / "failure.json", {"type": type(error).__name__, "error": str(error)})
        raise


def outcome_value(episode):
    """Endpoint resources credit healing; no direct bonus for inducing status."""
    steps = episode["decisions"]
    if not steps or episode["stop_reason"] not in {
        "battle_won",
        "party_defeated",
        "player_turn_budget",
    }:
        raise ValueError("unusable measured branch")
    before, after = steps[0]["state_before"], steps[-1]["state_after"]
    cap = sum(before["party_max_hp"])
    hp_change = (sum(after["party_hp"]) - sum(before["party_hp"])) / cap
    terminal = {"battle_won": 3, "party_defeated": -3, "player_turn_budget": 0}[
        episode["stop_reason"]
    ]
    foe_cap = steps[0]["observation"]["features"]["battle"]["opponent_max_hp"]
    damage = (steps[0]["opponent_hp_before"] - steps[-1]["opponent_hp_after"]) / foe_cap
    return terminal + 0.75 * hp_change + 0.5 * damage - 0.005 * episode["metrics"]["party_pp_spent"]


def load_examples(output):
    examples = []
    for path in sorted(output.glob("*/target.json")):
        target = json.loads(path.read_bytes())
        if target["role"] != "train":
            raise ValueError("holdout cannot enter training")
        values = tuple(target["returns"])
        examples.append(
            TrainerHeadExample(
                tuple(tuple(row) for row in target["vectors"]),
                tied_best_indices(values),
                mean_returns=values,
            )
        )
    return examples


def run(args):
    if (
        args.output.exists()
        or subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip()
    ):
        raise ValueError("requires new output and committed code")
    if (
        common._binding(args.frozen)["sha256"] != K_SHA
        or common._binding(args.rom)["sha256"] != common.ROM_SHA256
    ):
        raise ValueError("frozen model or cartridge differs")
    sources = common._source_rows(args.batch)
    cartridge = RedPracticeCartridge(args.rom.read_bytes())
    frozen = TrainerPracticeThreeHeadModel.from_dict(json.loads(args.frozen.read_bytes()))
    if {receipt["source_id"] for _, receipt in sources} != set(frozen.train_root_ids):
        raise ValueError("status sources differ from the declared TRAIN ancestry")
    initial = replace(frozen, move=expand_frozen_move(frozen.move))
    rows = recipes(cartridge)
    if args.pilot:
        rows = rows[:1]
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    args.output.mkdir(mode=0o700)
    write(
        args.output / "plan.json",
        {
            "source_commit": commit,
            "seed": SEED,
            "recipes": rows,
            "frozen": common._binding(args.frozen),
            "rom": common._binding(args.rom),
            "sources": [common._binding(p / "source.state.json") for p, _ in sources],
            "offsets": (0,) if args.pilot else OFFSETS,
            "pilot": args.pilot,
            "branch_turns": 8,
            "max_fits": 1,
            "epochs": 1000,
            "learning_rate": 0.01,
            "objective": "expected_regret",
            "new_independent_roots": 0,
            "heldout_tuning": False,
            "authority_promotions": 0,
            "gates": "heldout wins no regression, zero invalid actions; descriptive regret only",
        },
    )
    captures = {}
    # Open no held-out capture until the single fit is frozen.
    for i, row in enumerate(rows):
        if row["role"] != "train":
            continue
        capture = materialize(args, row, i, sources, cartridge, commit)
        captures[row["id"]] = capture
        results, vectors, slots = {}, None, None
        for offset in (0,) if args.pilot else OFFSETS:
            # First obtain only legal inventories from the declared construction.
            with PyBoyAdapter(args.rom, watch=False, speed=None) as emu:
                emu.load_state_bytes(capture.state_bytes)
                reader = PokemonRedStateReader(emu)
                encoder = PokemonRedObservationEncoder(
                    reader, True, cartridge.public_base_stats, True
                )
                prepared = prepare_red_battle_scenario(
                    encoder, reader.read(), allow_status_moves=True
                )
                slots = [
                    slot + 1
                    for slot, legal in zip(
                        prepared.features.slot_indices, prepared.features.legal_mask, strict=True
                    )
                    if legal
                ]
            for slot in slots:
                episode = play(
                    args,
                    capture,
                    frozen,
                    args.output / row["id"] / f"branch-{offset}-{slot}",
                    cartridge,
                    first_slot=slot,
                    offset=offset,
                    horizon=8,
                )
                obs = episode["decisions"][0]["observation"]
                projected = project_status_moves(
                    obs, BattleFeatureProjector(PokemonRedBattleCatalog()).project(obs)
                )
                current = [
                    projected.candidate_vectors[projected.candidate_slots.index(s)] for s in slots
                ]
                if vectors is not None and vectors != current:
                    raise ValueError("matched branch observations differ")
                vectors = current
                results.setdefault(slot, []).append(outcome_value(episode))
        write(
            args.output / row["id"] / "target.json",
            {
                "role": "train",
                "root": capture.manifest.root_lineage_id,
                "capture_id": capture.manifest.capture_id,
                "slots": slots,
                "vectors": vectors,
                "returns": [fmean(results[s]) for s in slots],
                "timing_returns": results,
            },
        )
        print(
            json.dumps(
                {"collected": row["id"], "returns": {s: fmean(v) for s, v in results.items()}}
            ),
            flush=True,
        )
    examples = load_examples(args.output)
    if args.pilot:
        write(
            args.output / "pilot-result.json",
            {
                "contexts": len(examples),
                "fits": 0,
                "status": "completed",
                "authority_promotions": 0,
            },
        )
        return
    if len(examples) != 24:
        raise ValueError("TRAIN inventory incomplete")
    head = TrainerHeadModel.fit(
        schema_id=STATUS_MOVE_SCHEMA,
        feature_names=STATUS_MOVE_NAMES,
        examples=examples,
        seed=SEED,
        hidden_units=initial.move.weights1.shape[1],
        epochs=1000,
        learning_rate=0.01,
        initial_model=initial.move,
        training_objective="expected_regret",
    )
    candidate = replace(
        initial,
        move=head,
        train_capture_ids=(
            *frozen.train_capture_ids,
            *(c.manifest.capture_id for c in captures.values()),
        ),
    )
    write(args.output / "candidate-model.json", candidate.to_dict())
    write(
        args.output / "fit.json",
        {
            "fits": 1,
            "examples": len(examples),
            "candidate": common._binding(args.output / "candidate-model.json"),
            "initial_regret": fmean(
                max(e.mean_returns)
                - e.mean_returns[initial.move.predict_index(e.candidate_vectors)]
                for e in examples
            ),
            "fitted_regret": fmean(
                max(e.mean_returns) - e.mean_returns[head.predict_index(e.candidate_vectors)]
                for e in examples
            ),
        },
    )
    evaluations = []
    for i, row in enumerate(rows):
        if row["role"] != "holdout":
            continue
        capture = materialize(args, row, i, sources, cartridge, commit)
        for arm, model, status in (("frozen", frozen, False), ("candidate", candidate, True)):
            episode = play(
                args, capture, model, args.output / row["id"] / arm, cartridge, status=status
            )
            evaluations.append(
                {
                    "case": row["id"],
                    "arm": arm,
                    "won": episode["battle_won"],
                    "stop": episode["stop_reason"],
                    "metrics": episode["metrics"],
                    "decisions": episode["decision_count"],
                }
            )
            print(json.dumps(evaluations[-1]), flush=True)
    write(
        args.output / "result.json",
        {
            "evaluations": evaluations,
            "fits": 1,
            "train_contexts": 24,
            "withheld_contexts": 8,
            "independent_heldout_roots": 0,
            "authority_promotions": 0,
            "natural_qualified": False,
            "wins": {
                arm: sum(r["won"] for r in evaluations if r["arm"] == arm)
                for arm in ("frozen", "candidate")
            },
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("rom", "batch", "frozen", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--pilot", action="store_true")
    run(parser.parse_args())
