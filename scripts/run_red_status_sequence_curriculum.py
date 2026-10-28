"""One sequence-aware status selector; K retains exact damage ranking.

No fitting on the first packet's heldout episodes. Only declared TRAIN starting
captures are reset. A new heldout configuration inventory is frozen before fitting.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import replace
from pathlib import Path
from statistics import fmean

import numpy as np
import run_red_status_curriculum as lab

from pokemon_red_completion.battle_scenario_capture import (
    OBSERVATION_SCHEMA_V2,
    build_battle_scenario_capture_payload,
    open_battle_scenario_capture,
)
from pokemon_red_completion.battle_semantics import BattleFeatureProjector
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.observation import BattleMenuPhase, PokemonRedStateReader
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_battle_catalog import PokemonRedBattleCatalog
from pokemon_red_completion.red_battle_practice_cartridge import RedPracticeCartridge
from pokemon_red_completion.red_battle_scenario import prepare_red_battle_scenario
from pokemon_red_completion.red_status_battle_features import (
    STATUS_MOVE_NAMES,
    STATUS_MOVE_SCHEMA,
    project_status_moves,
    status_choice_slots,
)
from pokemon_red_completion.red_trainer_practice_features import TrainerCandidateFeatures
from pokemon_red_completion.red_trainer_practice_fit import TrainerPracticeThreeHeadModel
from pokemon_red_completion.red_trainer_practice_head import TrainerHeadExample, TrainerHeadModel
from pokemon_red_completion.red_trainer_practice_returns import tied_best_indices
from pokemon_red_completion.red_trajectory import PokemonRedObservationEncoder
from pokemon_red_completion.scenario_lab import ScenarioPartition

SEED = 2026092116


def selector_example(target, frozen):
    if target["role"] != "train":
        raise ValueError("selector cannot fit heldout outcomes")
    projected = TrainerCandidateFeatures(
        STATUS_MOVE_SCHEMA,
        STATUS_MOVE_NAMES,
        tuple(tuple(x) for x in target["vectors"]),
        tuple(target["slots"]),
    )
    slots = status_choice_slots(projected, projected.candidate_slots, frozen.move)
    if len(slots) < 2:
        return None
    indices = [projected.candidate_slots.index(s) for s in slots]
    returns = tuple(target["returns"][i] for i in indices)
    # Outcome-derived soft labels provide gradients even where the frozen old
    # move head assigned effectively zero probability to a previously excluded move.
    logits = np.asarray(returns) * 3
    weights = np.exp(logits - logits.max())
    return TrainerHeadExample(
        tuple(projected.candidate_vectors[i] for i in indices),
        tied_best_indices(returns),
        tuple(weights / weights.sum()),
        returns,
    )


def capture_intermediate(args, state, directory, root, commit, cartridge):
    with PyBoyAdapter(args.rom, watch=False, speed=None) as emulator:
        emulator.load_state_bytes(state.read_bytes())
        reader = PokemonRedStateReader(emulator)
        raw = reader.read()
        if raw.battle_state != 2 or not raw.battler_hp or not raw.enemy_hp:
            return None
        if reader.read_battle_menu_state(raw).phase is not BattleMenuPhase.MAIN:
            raise ValueError("sequence opening did not settle at MAIN")
        encoder = PokemonRedObservationEncoder(reader, True, cartridge.public_base_stats)
        prepared = prepare_red_battle_scenario(
            encoder, raw, allow_no_attack=True, allow_status_moves=True
        )
        if sum(prepared.features.legal_mask) < 2:
            return None
        payload = state.read_bytes()
        manifest = build_battle_scenario_capture_payload(
            capture_id=f"status-sequence-{directory.name}",
            root_lineage_id=root,
            partition=ScenarioPartition.TRAIN,
            state_bytes=payload,
            initial_observation_sha256=prepared.initial_observation_sha256,
            source_commit=commit,
            expected_map=raw.map_id,
            expected_battle_state=2,
            source_state_sha256=lab.common._binding(state)["sha256"],
            observation_schema=OBSERVATION_SCHEMA_V2,
        )
        lab.write(directory / "intermediate.state", payload)
        lab.write(directory / "intermediate.state.json", manifest)
    return open_battle_scenario_capture(
        directory / "intermediate.state", directory / "intermediate.state.json"
    )


def run(args):
    if (
        args.output.exists()
        or subprocess.check_output(["git", "status", "--porcelain"], cwd=lab.ROOT).strip()
    ):
        raise ValueError("new output and committed code required")
    if lab.common._binding(args.frozen)["sha256"] != lab.K_SHA:
        raise ValueError("frozen K differs")
    if lab.common._binding(args.rom)["sha256"] != lab.common.ROM_SHA256:
        raise ValueError("ROM differs")
    parent_plan = json.loads((args.parent / "plan.json").read_bytes())
    parent_result = json.loads((args.parent / "result.json").read_bytes())
    if parent_plan["seed"] != lab.SEED or parent_result["fits"] != 1:
        raise ValueError("completed first status packet required")
    frozen = TrainerPracticeThreeHeadModel.from_dict(json.loads(args.frozen.read_bytes()))
    cartridge = RedPracticeCartridge(args.rom.read_bytes())
    sources = lab.common._source_rows(args.batch)
    if ({receipt["source_id"] for _, receipt in sources} != set(frozen.train_root_ids)
            or parent_plan["frozen"]["sha256"] != lab.K_SHA):
        raise ValueError("sequence sources or parent baseline ancestry differ")
    rows = [r for r in parent_plan["recipes"] if r["role"] == "train"]
    heldout = [r for r in lab.recipes(cartridge, seed=SEED) if r["role"] == "holdout"]
    if len(rows) != 24 or len(heldout) != 8:
        raise ValueError("prospective inventory differs")
    # The first packet's holdouts are never loaded, copied or used as targets.
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=lab.ROOT).decode().strip()
    args.output.mkdir(mode=0o700)
    lab.write(
        args.output / "plan.json",
        {
            "source_commit": commit,
            "seed": SEED,
            "train_ids": [r["id"] for r in rows],
            "parent_plan": lab.common._binding(args.parent / "plan.json"),
            "parent_targets": [
                lab.common._binding(args.parent / r["id"] / "target.json") for r in rows
            ],
            "frozen": lab.common._binding(args.frozen),
            "heldout": heldout,
            "offsets": [0, 4],
            "sequence_openings": 24,
            "max_new_branches": 144,
            "max_fits": 1,
            "epochs": 1800,
            "learning_rate": 0.03,
            "hidden_units": 24,
            "training": "outcome-soft-label cross-entropy, K damage ranking immutable",
            "gates": {
                "withheld_wins_no_regression": True,
                "invalid_actions": 0,
                "damage_only_decisions_unchanged": True,
            },
            "independent_heldout_roots": 0,
            "authority_promotions": 0,
            "closed_loop_failure_rejects_promotion": True,
        },
    )
    targets = [json.loads((args.parent / r["id"] / "target.json").read_bytes()) for r in rows]
    new_ids, censored = [], []
    for row in rows:
        directory = args.output / f"sequence-{row['id']}"
        directory.mkdir(mode=0o700)
        capture = open_battle_scenario_capture(
            args.parent / row["id"] / "capture.state",
            args.parent / row["id"] / "capture.state.json",
        )
        if capture.manifest.partition is not ScenarioPartition.TRAIN:
            raise ValueError("sequence source must remain TRAIN")
        status_id = lab.FAMILIES[row["family"]]
        slot = next(
            i + 1
            for i, m in enumerate(row["practice"]["actor_moves"])
            if int(m["move_ref"].rsplit(":", 1)[1]) == status_id
        )
        if row["conditions"]["disabled_slot"] == slot:
            censored.append({"case": row["id"], "reason": "declared status slot disabled"})
            continue
        episode = lab.play(
            args, capture, frozen, directory / "opening", cartridge, first_slot=slot, horizon=1
        )
        intermediate = capture_intermediate(
            args,
            directory / "opening/final.state",
            directory,
            capture.manifest.root_lineage_id,
            commit,
            cartridge,
        )
        if intermediate is None:
            censored.append({"case": row["id"], "reason": episode["stop_reason"]})
            continue
        new_ids.append(intermediate.manifest.capture_id)
        returns, vectors, slots = {}, None, None
        # Full inventory is observed, never inferred from teacher desirability.
        with PyBoyAdapter(args.rom, watch=False, speed=None) as emulator:
            emulator.load_state_bytes(intermediate.state_bytes)
            reader = PokemonRedStateReader(emulator)
            encoder = PokemonRedObservationEncoder(reader, True, cartridge.public_base_stats, True)
            prepared = prepare_red_battle_scenario(encoder, reader.read(), allow_status_moves=True)
            slots = tuple(
                s + 1
                for s, legal in zip(
                    prepared.features.slot_indices, prepared.features.legal_mask, strict=True
                )
                if legal
            )
        for offset in (0, 4):
            for slot in slots:
                result = lab.play(
                    args,
                    intermediate,
                    frozen,
                    directory / f"branch-{offset}-{slot}",
                    cartridge,
                    first_slot=slot,
                    offset=offset,
                    horizon=8,
                )
                obs = result["decisions"][0]["observation"]
                projected = project_status_moves(
                    obs, BattleFeatureProjector(PokemonRedBattleCatalog()).project(obs)
                )
                current = [
                    projected.candidate_vectors[projected.candidate_slots.index(s)] for s in slots
                ]
                if vectors is not None and vectors != current:
                    raise ValueError("matched sequence observations differ")
                vectors = current
                returns.setdefault(slot, []).append(lab.outcome_value(result))
        target = {
            "role": "train",
            "root": intermediate.manifest.root_lineage_id,
            "capture_id": intermediate.manifest.capture_id,
            "slots": slots,
            "vectors": vectors,
            "returns": [fmean(returns[s]) for s in slots],
            "timing_returns": returns,
        }
        lab.write(directory / "target.json", target)
        targets.append(target)
        print(json.dumps({"sequence_context": row["id"], "returns": target["returns"]}), flush=True)
    lab.write(
        args.output / "collection.json",
        {"contexts": len(targets), "censored": censored, "new_capture_ids": new_ids},
    )
    examples = [e for t in targets if (e := selector_example(t, frozen)) is not None]
    head = TrainerHeadModel.fit(
        schema_id=STATUS_MOVE_SCHEMA,
        feature_names=STATUS_MOVE_NAMES,
        examples=examples,
        seed=SEED,
        hidden_units=24,
        epochs=1800,
        learning_rate=0.03,
    )
    candidate = replace(
        frozen,
        move=head,
        damage_reference=frozen.move,
        train_capture_ids=(*frozen.train_capture_ids, *(t["capture_id"] for t in targets)),
    )
    lab.write(args.output / "candidate-model.json", candidate.to_dict())
    baseline_regret = fmean(
        max(e.mean_returns)
        - e.mean_returns[
            next(
                i
                for i, row in enumerate(e.candidate_vectors)
                if row[STATUS_MOVE_NAMES.index("move.category.status")] == 0
            )
        ]
        for e in examples
    )
    regret = fmean(
        max(e.mean_returns) - e.mean_returns[head.predict_index(e.candidate_vectors)]
        for e in examples
    )
    lab.write(
        args.output / "fit.json",
        {
            "fits": 1,
            "examples": len(examples),
            "baseline_regret": baseline_regret,
            "candidate_regret": regret,
            "candidate": lab.common._binding(args.output / "candidate-model.json"),
            "damage_reference_equal": canonical_sha256(candidate.damage_reference.to_dict())
            == canonical_sha256(frozen.move.to_dict()),
        },
    )
    evaluations = []
    for i, row in enumerate(heldout):
        capture = lab.materialize(args, row, i, sources, cartridge, commit)
        for arm, model, status in (("frozen", frozen, False), ("candidate", candidate, True)):
            episode = lab.play(
                args, capture, model, args.output / row["id"] / arm, cartridge, status=status
            )
            result = {
                "case": row["id"],
                "arm": arm,
                "won": episode["battle_won"],
                "stop": episode["stop_reason"],
                "metrics": episode["metrics"],
                "decisions": episode["decision_count"],
            }
            evaluations.append(result)
            print(json.dumps(result), flush=True)
    lab.write(
        args.output / "result.json",
        {
            "evaluations": evaluations,
            "fits": 1,
            "wins": {
                arm: sum(r["won"] for r in evaluations if r["arm"] == arm)
                for arm in ("frozen", "candidate")
            },
            "authority_promotions": 0,
            "independent_heldout_roots": 0,
            "natural_qualified": False,
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("rom", "batch", "frozen", "parent", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    run(parser.parse_args())
