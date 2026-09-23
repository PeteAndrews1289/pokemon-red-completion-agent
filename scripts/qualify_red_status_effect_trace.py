"""Bounded TRAIN-only effect telemetry qualification; no learner or player promotion."""

import argparse
import json
import subprocess
import time
from contextlib import ExitStack, contextmanager
from copy import deepcopy
from pathlib import Path

import run_red_status_curriculum as lab
from red_status_root_coverage import SEED, crossed_recipes, validate_recipes

from pokemon_red_completion.red_status_effect_trace import RedStatusEffectTrace


def native_first_actor_case(template, cartridge):
    """Prospective native-stat construction shared by narrowly bounded TRAIN packets."""
    catalog = lab.PokemonRedBattleCatalog()
    row = deepcopy(template)
    p = row["practice"]
    actor = cartridge.species(int(p["actor_species_ref"].rsplit(":", 1)[1]))
    own = actor.neutral_stats(p["actor_level"])
    own_types = catalog.resolve_species(p["actor_species_ref"]).types
    for species in cartridge.species_ids:
        enemy = cartridge.species(species)
        stats = enemy.trainer_stats(p["opponent_level"])
        if (stats.speed >= own.speed or stats.attack > 1.5 * own.defense or
                stats.special > 1.5 * own.special):
            continue
        moves = []
        for move in enemy.teachable_moves_at_level(p["opponent_level"]):
            ref = lab.pokemon_red_move_ref(move)
            semantic = catalog.resolve_move(ref)
            if (catalog.recovery_attack_supported(ref) and 35 <= semantic.power <= 40
                    and semantic.priority == 0 and not semantic.effect_flags &
                    {"multi_hit", "drain", "recoil", "trapping", "charge"} and
                    0 < catalog.type_effectiveness(semantic.type_name, own_types) <= 1):
                moves.append(move)
        if len(moves) >= 2:
            break
    else:
        raise ValueError("no prospective native-stat diagnostic opponent")
    p.update(opponent_species_ref=f"pokemon.red.gb.us.rev0:species:{species:03d}",
             opponent_national_number=enemy.national_number, opponent_hp=stats.max_hp)
    if row["family"] in {"confusion", "disable"}:
        p["actor_hp"] = own.max_hp
    p["opponent_moves"] = [{"move_ref": lab.pokemon_red_move_ref(m),
                           "pp": catalog.resolve_move(lab.pokemon_red_move_ref(m)).max_pp}
                          for m in moves[:2]]
    if row["family"] == "rest" and row["contrast"] == 0:
        row["conditions"]["player_status"] = "burn"
    return row


def diagnostic_recipes(rows, cartridge):
    cases = []
    for i, family in enumerate(("heal", "rest", "confusion", "disable")):
        for contrast in (0, 1):
            template = next(r for r in rows if r["source_index"] == i % 3 and
                            r["id"].endswith(f"balanced-{family}-0-{contrast}"))
            row = native_first_actor_case(template, cartridge)
            row["id"] += "-natural-trace-check"
            cases.append(row)
    return cases


def play_one(args, capture, frozen, output, cartridge, slot, *, traced, allow_terminal=False):
    output.mkdir(mode=0o700)
    log = lab.TrainerPracticeEventLog(output / "events", run_identity={
        "capture_id": capture.manifest.capture_id, "root": capture.manifest.root_lineage_id,
        "partition": "train", "purpose": "effect_instrumentation_diagnostic",
        "first_slot": slot, "traced": traced, "actor_memory_writes": 0,
        "model_sha256": lab.K_SHA, "forced_diagnostic_actions": 1})
    active = {}

    class Actions:
        def execute(self, action):
            return active["limiter"].execute(action)

    @contextmanager
    def session():
        with (lab.PyBoyAdapter(args.rom, watch=False, speed=None) as emulator,
              lab.retained_session(emulator, maximum_frames=5000, output=output,
                                   maximum_controller_actions=500,
                                   maximum_wall_seconds=45) as retained,
              ExitStack() as hooks):
            active["limiter"] = lab.ControllerActionLimiter(
                lab.FrameSafeExecutor(retained), maximum_actions=500,
                admit_action=retained.check_wall_time_budget)

            class Session:
                def __getattr__(self, name):
                    return getattr(retained, name)

                def load_state_bytes(self, payload):
                    retained.load_state_bytes(payload)
                    if traced:
                        trace = RedStatusEffectTrace(
                            emulator._require_backend(), args.rom.read_bytes(),
                            partition=capture.manifest.partition)
                        active["trace"] = trace
                        hooks.enter_context(trace.installed())

            yield Session()

    policy = lab._FirstChoicePolicy(
        lab.TrainerPracticeFirstChoice(lab.BattleAction.move(slot)),
        lab.DamageContinuation("effect-trace-diagnostic", capture.manifest.capture_id, frozen))
    try:
        episode = lab.run_red_trainer_practice_episode(
            capture, session_factory=session, policy=policy, max_decisions=4,
            max_player_turns=1, event_sink=log.emit,
            public_species_base_stats=cartridge.public_base_stats,
            allow_status_moves=True, action_executor=Actions()).public_dict()
        lab.write(output / "episode.json", episode)
        log.finish({"episode_sha256": lab.canonical_sha256(episode),
                    "stop_reason": episode["stop_reason"]})
        lab.verify_trainer_practice_event_log(output / "events")
        stops = ({"player_turn_budget", "battle_won", "party_defeated"} if allow_terminal
                 else {"player_turn_budget"})
        if (episode["stop_reason"] not in stops or len(episode["decisions"]) != 1
                or episode["decisions"][0]["move_slot"] != slot
                or episode["metrics"]["invalid_action_failures"]):
            raise ValueError("diagnostic turn did not settle safely")
        return episode
    except Exception as exc:
        if not log.closed:
            log.fail(exc)
        lab.write(output / "failure.json", {"type": type(exc).__name__, "error": str(exc)})
        raise
    finally:
        trace = active.get("trace")
        lab.write(output / "effect-trace.json", {"enabled": traced,
            "records": trace.records if trace else [], "pending": trace.pending if trace else None,
            "training_only": True, "actor_features_added": 0})


def verify_pair(plain, traced, directory, selected_move):
    bind = lab.common._binding
    a, b = plain["decisions"][0], traced["decisions"][0]
    fields = ("observation", "move_slot", "kind", "outcome", "state_before", "state_after",
              "frames_executed", "legal_move_slots", "legal_party_slots", "model_input")
    if (any(a[k] != b[k] for k in fields) or
            plain["final_observation"] != traced["final_observation"] or
            bind(directory / "plain/final.state")["sha256"] !=
            bind(directory / "traced/final.state")["sha256"]):
        raise ValueError("instrumentation changed native execution or terminal state")
    trace = json.loads((directory / "traced/effect-trace.json").read_bytes())
    matches = [r for r in trace["records"] if r["before"]["turn"] == 0 and
               r["before"]["move"] == selected_move]
    if (trace["pending"] is not None or len(matches) != 1 or
            matches[0]["label"]["kind"] != "observed"):
        raise ValueError("selected native effect is not uniquely observable")
    return {"state_sha256": bind(directory / "plain/final.state")["sha256"],
            "frames_per_arm": a["frames_executed"], "effect": matches[0],
            "episode_bindings": [bind(directory / arm / "episode.json")
                                 for arm in ("plain", "traced")],
            "trace": bind(directory / "traced/effect-trace.json"),
            "exact_state_equal": True, "actions_equal": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=lab.ROOT).strip():
        raise ValueError("new output and committed source required")
    if lab.common._binding(args.rom)["sha256"] != lab.common.ROM_SHA256:
        raise ValueError("cartridge differs")
    frozen_path = args.root / "red-trainer-J-canonical-20260920-v1/candidate-model.json"
    if lab.common._binding(frozen_path)["sha256"] != lab.K_SHA:
        raise ValueError("frozen K differs")
    frozen = lab.TrainerPracticeThreeHeadModel.from_dict(json.loads(frozen_path.read_bytes()))
    sources = sorted(lab.common._source_rows(args.root / "red-fresh-trainer-train-batch-20260917"),
                     key=lambda pair: pair[1]["source_id"])
    roots = [receipt["source_id"] for _, receipt in sources]
    if set(roots) != set(frozen.train_root_ids):
        raise ValueError("TRAIN ancestry differs")
    cartridge = lab.RedPracticeCartridge(args.rom.read_bytes())
    rows = crossed_recipes(cartridge, roots)
    cases = diagnostic_recipes(rows, cartridge)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=lab.ROOT).decode().strip()
    args.output.mkdir(mode=0o700)
    lab.write(args.output / "plan.json", {"source_commit": commit, "seed": SEED,
        "rom": lab.common._binding(args.rom), "frozen": lab.common._binding(frozen_path),
        "sources": [lab.common._binding(path / "source.state.json") for path, _ in sources],
        "recipes": rows, "coverage": validate_recipes(rows, roots, cartridge),
        "diagnostic_cases": cases, "max_episodes": 16, "max_frames": 80000,
        "max_minutes": 90, "max_fits": 0, "actor_promotions": 0})
    started, pairs = time.monotonic(), []
    try:
        for row in cases:
            if time.monotonic() - started > 5400:
                raise TimeoutError("effect qualification90minute limit")
            capture = lab.materialize(args, row, row["source_index"], sources, cartridge, commit)
            directory = args.output / row["id"]
            move = lab.FAMILIES[row["family"]]
            slot = next(i+1 for i, m in enumerate(row["practice"]["actor_moves"])
                        if m["move_ref"] == lab.pokemon_red_move_ref(move))
            plain = play_one(args, capture, frozen, directory / "plain", cartridge, slot,
                             traced=False)
            traced = play_one(args, capture, frozen, directory / "traced", cartridge, slot,
                              traced=True)
            pair = {"case": row["id"], "root": row["root"], "family": row["family"],
                    "contrast": row["contrast"], **verify_pair(plain, traced, directory, move)}
            lab.write(directory / "pair.json", pair)
            pairs.append(pair)
            print(json.dumps({"case": row["id"], "label": pair["effect"]["label"],
                              "paired_state_equal": True}), flush=True)
        lab.write(args.output / "result.json", {"passed": len(pairs) == 8,
            "pairs": pairs, "episodes": len(pairs)*2, "fits": 0, "actor_promotions": 0,
            "reserved_recipes_executed": 0, "learned_choices": 0,
            "seconds": time.monotonic() - started})
    except Exception as exc:
        lab.write(args.output / "failure.json", {"type": type(exc).__name__, "error": str(exc),
                                                  "completed_pairs": len(pairs)})
        raise


if __name__ == "__main__":
    main()
