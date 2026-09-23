"""One approved two-origin/six-case assisted DEVELOPMENT pilot, never a fit.

Preparation and evaluation are separate, one-shot stages. The inventory-adjacent
claim prevents changing output names to repeat this fixed source schedule.
All six constructed inputs are frozen before the first J query.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

import capture_fresh_red_trainer_train_batch as sources
import materialize_red_teacher_battle_practice as factory
import run_red_trainer_practice_model as player

from pokemon_red_completion.battle_practice_factory import AssistedDevelopmentPracticeSpec
from pokemon_red_completion.battle_scenario_capture import (
    OBSERVATION_SCHEMA_V2,
    parse_battle_scenario_capture_manifest,
)
from pokemon_red_completion.red_battle_catalog import (
    PokemonRedBattleCatalog,
    pokemon_red_move_ref,
    pokemon_red_species_ref,
)
from pokemon_red_completion.red_battle_practice_cartridge import RedPracticeCartridge
from pokemon_red_completion.red_trainer_practice_log import verify_trainer_practice_event_log
from pokemon_red_completion.scenario_lab import ScenarioPartition

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "pokemon.red.six-party-assisted-pilot.v1"
BOOTS = (3300, 3500)
PARTY_SIZES = (4, 5, 6)
MODEL_SHA256 = "260b227a2fb3ba46a80be9c42e1f7e17977068e890f135407f8faafe2336fb09"
INVENTORY_SHA256 = "8815963794839d78455e67ee946bae4c08d557557813b08140f5d42130a4a45e"
ORIGINAL_PROTOCOL_SHA256 = "a9c1de0af502cfc16551c7e7a2e58dc2a0e562124771d787085d70fe3a4b7607"
RETAINED_HASHES = {
    "origin.state": "eaef973f6a3722e6c8a53df05ffccc722219f93f74c2cf11fb26b6be7cee0cd4",
    "source.state": "fab22a7a47b85abbb983e78620fb1197654fe120550de6c10438c0484e9cea1e",
    "source.state.json": "786355bc83c2e386300997022098002cbb0b570d9a25ef5536deaab4723b69a8",
}


def binding(path: Path) -> dict[str, str]:
    return {"path": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def write_new(path: Path, value: object) -> None:
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")


def revision() -> str:
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip():
        raise ValueError("pilot requires committed clean source")
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()


def prior_sources(inventory: dict) -> list[dict]:
    result = []
    for row in inventory["manifests"]:
        if row["capture_id"].startswith("fresh-red-"):
            path = Path(row["path"]).parent / "outcome.json"
            receipt = json.loads(path.read_bytes())
            if (
                receipt["root_lineage_id"] != row["root_lineage_id"]
                or receipt["battle_state_sha256"] != row["state_sha256"]
                or receipt["origin_state_sha256"] != row["source_state_sha256"]
                or type(receipt["first_party_ot_id"]) is not int
            ):
                raise ValueError("prior physical source receipt differs")
            result.append({**receipt, "receipt_binding": binding(path)})
    if len(result) != 8:
        raise ValueError("pilot needs the eight retained prior physical source receipts")
    return result


def inventory_ancestry(inventory: dict) -> tuple[set[str], set[str]]:
    """Legacy captures may omit a parent; never invent one or drop their state/root."""
    hashes: set[str] = set()
    roots: set[str] = set()
    for row in inventory["manifests"]:
        root = row["root_lineage_id"]
        if not isinstance(root, str) or not root:
            raise ValueError("inventory ancestry root differs")
        roots.add(root)
        state = row["state_sha256"]
        parent = row.get("source_state_sha256")
        for digest in (state,) if parent is None else (state, parent):
            if not isinstance(digest, str) or re.fullmatch(r"[a-f0-9]{64}", digest) is None:
                raise ValueError("inventory ancestry hash differs")
            hashes.add(digest)
    return hashes, roots


def validate_new_source(report: dict, inventory: dict, prior: list[dict]) -> None:
    used_hashes, used_roots = inventory_ancestry(inventory)
    used_hashes.update(
        value for row in prior
        for value in (row["origin_state_sha256"], row["battle_state_sha256"])
    )
    used_roots.update(row["root_lineage_id"] for row in prior)
    used_ids = {row["first_party_ot_id"] for row in prior}
    if (
        report["partition"] != "development"
        or report["fresh_power_on"] is not True
        or report["boot_frames"] not in BOOTS
        or report["root_lineage_id"] in used_roots
        or report["origin_state_sha256"] in used_hashes
        or report["battle_state_sha256"] in used_hashes
        or report["first_party_ot_id"] in used_ids
    ):
        raise ValueError("new source has reused or unestablished physical ancestry")


def practice(cartridge, *, boot: int, count: int, source: dict) -> dict:
    """Predeclared conditions, resolved from cartridge facts, never policy scores."""
    by_dex = {cartridge.species(i).national_number: cartridge.species(i)
              for i in cartridge.species_ids}

    def moves(ids, *, depleted=False):
        return [{"move_ref": pokemon_red_move_ref(i), "pp": 0 if depleted else 10} for i in ids]

    def member(number, slot, ids):
        return {
            "party_slot": slot, "national_number": number,
            "species_ref": pokemon_red_species_ref(by_dex[number].internal_id),
            "level": 20, "moves": moves(ids),
        }

    # Last slot always offers electric coverage against the active water foe;
    # other living targets remain genuine choices. These are disclosed fixtures.
    roster = [(17, (16, 98)), (20, (33, 98)), (2, (22, 33)), (27, (10, 89))]
    reserves = [member(n, slot, ids)
                for slot, (n, ids) in enumerate(roster[:count - 2], 2)]
    reserves.append(member(25, count, (85, 98)))
    result = {
        "source_state_sha256": source["battle_state_sha256"],
        "root_lineage_id": source["root_lineage_id"],
        "partition": "development", "battle_kind": "trainer",
        "actor_national_number": 5,
        "actor_species_ref": pokemon_red_species_ref(by_dex[5].internal_id),
        "actor_level": 20, "actor_hp": 20,
        "actor_moves": moves((52, 10), depleted=boot == 3500),
        "party_reserves": reserves,
        "opponent_national_number": 8,
        "opponent_species_ref": pokemon_red_species_ref(by_dex[8].internal_id),
        "opponent_level": 20,
        "opponent_hp": by_dex[8].trainer_stats(20).max_hp,
        "opponent_moves": moves((55, 33)),
        "opponent_party_count": 2,
        "opponent_reserves": [member(17, 2, (16, 98))],
    }
    # Gen I reconstructs enemy reserve PP on send-out; reduced declarations
    # cannot persist. Keep player conditions unchanged and disclose full enemy PP.
    catalog = PokemonRedBattleCatalog()
    for reserve in result["opponent_reserves"]:
        for move in reserve["moves"]:
            move["pp"] = catalog.resolve_move(move["move_ref"]).max_pp
    AssistedDevelopmentPracticeSpec.from_dict(result)
    return result


def resume_first_source(args, protocol: dict) -> dict:
    """The user-authorized metadata recovery, not a generic retry facility."""
    original_path = args.output / "protocol.json"
    original = json.loads(original_path.read_bytes())
    claim = args.inventory.parent / "assisted-six-party-20260920-preparation-claim.json"
    if (
        binding(original_path)["sha256"] != ORIGINAL_PROTOCOL_SHA256
        or binding(claim)["sha256"] != ORIGINAL_PROTOCOL_SHA256
        or {**protocol, "source_commit": original["source_commit"]} != original
    ):
        raise ValueError("resume must preserve the exact original pilot conditions")
    if {p.name for p in args.output.iterdir()} != {
        "protocol.json", "preparation-failure.json", "source-3300"
    }:
        raise ValueError("resume requires only the retained first source and original failure")
    failure = json.loads((args.output / "preparation-failure.json").read_bytes())
    if failure != {
        "stage": "source-3300", "error_type": "KeyError", "error": "'source_state_sha256'",
        "completed_sources": 0, "completed_cells": 0,
        "retry_allowed": False, "global_stop": True,
    }:
        raise ValueError("resume is limited to the retained metadata-only failure")
    directory = args.output / "source-3300"
    for name, digest in RETAINED_HASHES.items():
        if binding(directory / name)["sha256"] != digest:
            raise ValueError("retained first source bytes differ")
    report = json.loads((directory / "outcome.json").read_bytes())
    manifest = parse_battle_scenario_capture_manifest(
        (directory / "source.state.json").read_bytes()
    )
    if (
        report["origin_state_sha256"] != RETAINED_HASHES["origin.state"]
        or report["battle_state_sha256"] != RETAINED_HASHES["source.state"]
        or report["root_lineage_id"] != "fresh-red-lab-rival-development-boot3300"
        or report["boot_frames"] != 3300
        or report["source_commit"] != original["source_commit"]
        or report["model_queries"] != 0
        or manifest.state_sha256 != report["battle_state_sha256"]
        or manifest.source_state_sha256 != report["origin_state_sha256"]
        or manifest.root_lineage_id != report["root_lineage_id"]
        or manifest.source_commit != report["source_commit"]
        or manifest.partition is not ScenarioPartition.DEVELOPMENT
    ):
        raise ValueError("retained first source provenance differs")
    inventory = json.loads(args.inventory.read_bytes())
    validate_new_source(report, inventory, prior_sources(inventory))
    recovery = {
        "original_protocol": binding(original_path),
        "original_failure": binding(args.output / "preparation-failure.json"),
        "retained_source": RETAINED_HASHES, "execution_source_commit": protocol["source_commit"],
        "user_authorized_exact_state_continuation": True,
        "first_source_replayed": False, "conditions_changed": False,
    }
    write_new(args.inventory.parent / "assisted-six-party-20260920-resume-claim.json", recovery)
    protocol["continuation"] = recovery
    return report


def prepare(args, *, resume: bool = False) -> dict:
    commit = revision()
    if args.output.exists() and not resume:
        raise ValueError("pilot output must be new")
    if binding(args.inventory)["sha256"] != INVENTORY_SHA256:
        raise ValueError("pilot prior-source inventory differs")
    if binding(args.model)["sha256"] != MODEL_SHA256:
        raise ValueError("pilot frozen J differs")
    inventory = json.loads(args.inventory.read_bytes())
    inventory_ancestry(inventory)  # Validate legacy compatibility BEFORE any emulator/claim.
    prior = prior_sources(inventory)
    model = json.loads(args.model.read_bytes())
    planned_roots = {f"fresh-red-lab-rival-development-boot{boot}" for boot in BOOTS}
    if planned_roots.intersection(model["train_root_ids"]):
        raise ValueError("pilot source overlaps model fitting")
    rom = args.rom.read_bytes()
    if hashlib.sha256(rom).hexdigest() != factory.ROM_SHA256:
        raise ValueError("pilot Red cartridge differs")
    cartridge = RedPracticeCartridge(rom)
    # Validate and freeze every condition before opening even the first source.
    templates = [practice(cartridge, boot=boot, count=count, source={
        "battle_state_sha256": "0" * 64,
        "root_lineage_id": f"fresh-red-lab-rival-development-boot{boot}",
    }) for boot in BOOTS for count in PARTY_SIZES]
    protocol = {
        "schema": SCHEMA, "source_commit": commit,
        "inventory": binding(args.inventory), "prior_sources": prior,
        "rom": binding(args.rom), "model": binding(args.model),
        "output": str(args.output.resolve()), "boot_frames": list(BOOTS),
        "templates": templates, "max_episodes": 6, "independent_origin_clusters": 2,
        "max_decisions": 80, "maximum_frames": 120000,
        "maximum_controller_actions": 5000, "maximum_wall_seconds": 180,
        "setup_max_frames": sources.MAX_TOTAL_FRAMES, "setup_max_wall_seconds": 180,
        "no_retry": True, "fit_allowed": False, "natural_battle_qualification": False,
        "production_promotion": False, "normal_loss_is_failure_to_win_not_invalid_execution": True,
    }
    reports, plans = [], []
    protocol_path = args.output / ("resumed-protocol.json" if resume else "protocol.json")
    if resume:
        reports.append(resume_first_source(args, protocol))
    else:
        claim = args.inventory.parent / "assisted-six-party-20260920-preparation-claim.json"
        write_new(claim, protocol)  # Consumed even on later setup failure.
        args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    write_new(protocol_path, protocol)
    stage = "source"
    try:
        for boot in BOOTS[len(reports):]:
            stage = f"source-{boot}"
            directory = args.output / f"source-{boot}"
            directory.mkdir(mode=0o700)
            origin, state, manifest, report = sources._capture_one(
                args.rom, rom, boot, commit, partition=ScenarioPartition.DEVELOPMENT,
                failure_output=directory,
            )
            # Keep generated evidence even if the disjointness gate rejects it.
            for name, payload in (("origin.state", origin), ("source.state", state),
                                  ("source.state.json", manifest)):
                with (directory / name).open("xb") as stream:
                    stream.write(payload)
            write_new(directory / "outcome.json", report)
            validate_new_source(report, inventory, prior + reports)
            reports.append(report)
            print(json.dumps({"stage": stage, "status": "fresh_source_retained"}), flush=True)
        for boot in BOOTS:
            directory = args.output / f"source-{boot}"
            source = reports[BOOTS.index(boot)]
            for count in PARTY_SIZES:
                stage = f"materialize-{boot}-{count}"
                cell = args.output / f"boot-{boot}-party-{count}"
                cell.mkdir(mode=0o700)
                materialize = cell / "materialize-plan.json"
                write_new(materialize, {
                    "schema": factory.DEVELOPMENT_SCHEMA, "source_commit": commit,
                    "rom": protocol["rom"], "source_state": binding(directory / "source.state"),
                    "source_capture_manifest": binding(directory / "source.state.json"),
                    "practice": practice(cartridge, boot=boot, count=count, source=source),
                    "observation_schema": OBSERVATION_SCHEMA_V2,
                    "fit_allowed": False, "natural_battle_qualification": False,
                    "output": str(cell / "materialized"),
                })
                factory.run(materialize)
                plan = cell / "player-plan.json"
                write_new(plan, {
                    "schema": player.OUTCOME_SCHEMA, "source_commit": commit,
                    "rom": protocol["rom"], "outcome_model": protocol["model"],
                    "capture_state": binding(cell / "materialized/assisted.state"),
                    "capture_manifest": binding(cell / "materialized/assisted.state.json"),
                    **{k: protocol[k] for k in ("max_decisions", "maximum_frames",
                       "maximum_controller_actions", "maximum_wall_seconds")},
                    "opening_idle_frames": 0, "output": str(cell / "episode"),
                })
                plans.append({"boot": boot, "party_count": count, "plan": binding(plan),
                              "materialization": binding(cell / "materialized/outcome.json")})
        freeze = {"schema": SCHEMA, "protocol": binding(protocol_path),
                  "cells": plans, "sources": reports, "model_queries": 0}
        write_new(args.output / "freeze.json", freeze)
        write_new(args.inventory.parent / "assisted-six-party-20260920-freeze.json",
                  binding(args.output / "freeze.json"))
        return {"status": "six_assisted_inputs_frozen", "cells": 6, "model_queries": 0}
    except Exception as error:
        failure_name = "resumption-failure.json" if resume else "preparation-failure.json"
        write_new(args.output / failure_name, {
            "stage": stage, "error_type": type(error).__name__, "error": str(error),
            "completed_sources": len(reports), "completed_cells": len(plans),
            "retry_allowed": False, "global_stop": True,
        })
        raise


def evaluate(args) -> dict:
    commit = revision()
    pin_path = args.inventory.parent / "assisted-six-party-20260920-freeze.json"
    pin = json.loads(pin_path.read_bytes())
    freeze = json.loads(factory._bound_file(pin, "pilot freeze"))
    protocol = json.loads(factory._bound_file(freeze["protocol"], "pilot protocol"))
    expected = [(boot, count) for boot in BOOTS for count in PARTY_SIZES]
    if (
        protocol["source_commit"] != commit
        or protocol["output"] != str(args.output.resolve())
        or binding(args.inventory) != protocol["inventory"]
        or [(row["boot"], row["party_count"]) for row in freeze["cells"]] != expected
    ):
        raise ValueError("pilot freeze/source schedule differs")
    for row in freeze["cells"]:
        factory._bound_file(row["materialization"], "assisted receipt")
        plan = json.loads(factory._bound_file(row["plan"], "player plan"))
        if plan["outcome_model"]["sha256"] != MODEL_SHA256:
            raise ValueError("pilot model identity differs")
        player.run(Path(row["plan"]["path"]), check_only=True)
    claim = args.inventory.parent / "assisted-six-party-20260920-evaluation-claim.json"
    write_new(claim, {"freeze": pin, "no_retry": True, "max_episodes": 6})
    rows = []
    try:
        for row in freeze["cells"]:
            plan_path = Path(row["plan"]["path"])
            plan = json.loads(plan_path.read_bytes())
            output = Path(plan["output"])
            write_new(output.parent / "claimed.json", row)
            player.run(plan_path)
            result = json.loads((output / "outcome.json").read_bytes())
            verification = verify_trainer_practice_event_log(output / "events")
            valid = (
                result["stop_reason"] in {"battle_won", "party_defeated"}
                and result["teacher_queries"] == result["memory_write_actions"] == 0
                and result["metrics"]["invalid_action_failures"] == 0
                and binding(output / "final.state")["sha256"] == result["final_state_sha256"]
                and verification["complete"] is True
                and verification["terminal_event"] == "run_finished"
            )
            retained = {"boot": row["boot"], "party_count": row["party_count"],
                        "valid_terminal": valid, "outcome": result, "verification": verification}
            rows.append(retained)
            write_new(args.output / f"completed-{len(rows):02d}.json", retained)
            print(json.dumps({"boot": row["boot"], "party_count": row["party_count"],
                              "stop_reason": result["stop_reason"],
                              "decisions": result["decision_count"]}), flush=True)
            if not valid:
                raise ValueError("pilot terminal failed; remaining cells must not run")
    except Exception as error:
        write_new(args.output / "evaluation-failure.json", {
            "error_type": type(error).__name__, "error": str(error),
            "completed_cells": len(rows), "global_stop": True, "retry_allowed": False,
        })
        raise
    result = {"schema": SCHEMA, "status": "bounded_pilot_completed", "cells": rows,
              "independent_origins": 2, "assisted": True, "fit_allowed": False,
              "natural_full_party_qualified": False, "authority_promotions": 0}
    write_new(args.output / "result.json", result)
    return {k: v for k, v in result.items() if k != "cells"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("prepare", "resume", "evaluate"))
    for name in ("rom", "model", "inventory", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args()
    result = evaluate(args) if args.stage == "evaluate" else prepare(
        args, resume=args.stage == "resume"
    )
    print(json.dumps(result), flush=True)
