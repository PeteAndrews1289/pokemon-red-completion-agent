"""Reobserve existing TRAIN snapshots with zero inputs; never generate new labels."""

import argparse
import json
import time
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

from pokemon_red_completion.battle_scenario_capture import open_battle_scenario_capture
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.observation import PokemonRedStateReader
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_battle_practice_cartridge import RedPracticeCartridge
from pokemon_red_completion.red_retained_status import enrich_retained_status
from pokemon_red_completion.red_trajectory import PokemonRedObservationEncoder

ROM_SHA256 = "5ca7ba01642a3b27b0cc0b5349b52792795b62d3ed977e98a09390659af96b7b"


def bound(path, digest):
    data = path.read_bytes()
    if sha256(data).hexdigest() != digest:
        raise ValueError("reobservation source digest differs")
    return data


def write(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write("\n")


def run(args):
    corpus = json.loads(bound(args.corpus, args.corpus_sha256))
    index = json.loads(bound(args.index, args.index_sha256))
    rom = bound(args.rom, ROM_SHA256)
    groups = {"anchors": corpus["anchors"], "current": corpus["current"], **corpus["retention"]}
    if index.get("target_sha256") != args.corpus_sha256:
        raise ValueError("snapshot index belongs to a different corpus")
    by_capture = {}
    for rows in groups.values():
        for row in rows:
            by_capture.setdefault(row["capture_id"], {})[canonical_sha256(row)] = row
    if not 1 <= len(by_capture) <= 400 or set(by_capture) != set(index["captures"]):
        raise ValueError("retained snapshot inventory differs")
    captures = {}
    for identity, variants in by_capture.items():
        pin = index["captures"][identity]
        capture = open_battle_scenario_capture(Path(pin["state"]), Path(pin["manifest"]))
        if (
            capture.manifest_sha256 != pin["manifest_sha256"]
            or capture.manifest.state_sha256 != pin["state_sha256"]
        ):
            raise ValueError("indexed native bytes differ")
        for row in variants.values():
            if (
                row["partition"] != "train"
                or capture.manifest.partition.value != "train"
                or row["capture_id"] != capture.manifest.capture_id
                or row["root_lineage_id"] != capture.manifest.root_lineage_id
                or row["manifest_sha256"] != capture.manifest_sha256
            ):
                raise ValueError("indexed TRAIN identity differs")
        captures[identity] = capture
    if args.preflight:
        print(json.dumps({"preflight": True, "captures": len(captures), "runtimes": 0}))
        return
    if args.output.exists():
        raise ValueError("reobservation output must be new")
    args.output.mkdir(parents=True, mode=0o700)
    write(
        args.output / "plan.json",
        {
            "schema": "pokemon.red.retained-status-reobservation.v1",
            "corpus_sha256": args.corpus_sha256,
            "index_sha256": args.index_sha256,
            "rom_sha256": ROM_SHA256,
            "captures": len(captures),
            "maximum_seconds": 120,
            "maximum_frames": 0,
            "maximum_inputs": 0,
            "new_outcomes": 0,
            "fits": 0,
            "script_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
            "merge_sha256": sha256(
                (
                    Path(__file__).parents[1]
                    / "src/pokemon_red_completion"
                    / "red_retained_status.py"
                ).read_bytes()
            ).hexdigest(),
        },
    )
    started = time.monotonic()
    augmented, receipts = {}, []
    cartridge = RedPracticeCartridge(rom)
    error = None
    try:
        # Reuse one emulator; each snapshot loads independently and gets no tick/input.
        with PyBoyAdapter(args.rom, watch=False, speed=None) as emulator:
            for identity, capture in captures.items():
                if time.monotonic() - started > 120:
                    raise TimeoutError("zero-input reobservation time budget exhausted")
                emulator.load_state_bytes(capture.state_bytes)
                before = emulator.save_state_bytes()
                reader = PokemonRedStateReader(emulator)
                raw = reader.read()
                encoder = PokemonRedObservationEncoder(reader, True, cartridge.public_base_stats)
                legacy = encoder.snapshot_from_raw(raw).to_dict()
                observed = (
                    replace(encoder, include_status_context=True).snapshot_from_raw(raw).to_dict()
                )
                staged = []
                for digest, target in by_capture[identity].items():
                    updated, receipt = enrich_retained_status(target, capture, legacy, observed)
                    staged.append((digest, updated, receipt))
                if emulator.frame_count != 0 or emulator.save_state_bytes() != before:
                    raise ValueError("reobservation changed native state or advanced time")
                for digest, updated, receipt in staged:
                    augmented[digest] = updated
                    receipts.append(receipt)
        result = deepcopy(corpus)
        for key in ("anchors", "current"):
            result[key] = [augmented[canonical_sha256(row)] for row in corpus[key]]
        result["retention"] = {
            key: [augmented[canonical_sha256(row)] for row in rows]
            for key, rows in corpus["retention"].items()
        }
        # Inputs must still authenticate after all native reads.
        bound(args.corpus, args.corpus_sha256)
        bound(args.index, args.index_sha256)
        write(args.output / "targets.json", result)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    audit = {
        "passed": error is None,
        "error": error,
        "captures": len({r["capture_id"] for r in receipts}),
        "target_versions": len(receipts),
        "frames": 0,
        "inputs": 0,
        "new_outcomes": 0,
        "fits": 0,
        "seconds": time.monotonic() - started,
        "receipts": receipts,
        "corpus_sha256": args.corpus_sha256,
        "enriched_corpus_sha256": (
            sha256((args.output / "targets.json").read_bytes()).hexdigest()
            if error is None
            else None
        ),
    }
    write(args.output / "audit.json", audit)
    print(json.dumps({k: v for k, v in audit.items() if k != "receipts"}))
    if error is not None:
        raise RuntimeError(error)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("corpus", "index", "rom", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("corpus-sha256", "index-sha256"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--preflight", action="store_true")
    run(parser.parse_args())
