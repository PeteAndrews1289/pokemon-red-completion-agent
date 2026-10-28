"""Single-use full-battle comparison of the frozen V2 interaction damage head."""

from __future__ import annotations

import argparse
import json
import random
import subprocess
import time
from collections import Counter
from dataclasses import asdict
from itertools import product
from pathlib import Path

import run_red_interaction_damage_successor as damage

from pokemon_red_completion.battle_practice_factory import BattlePracticeSpec
from pokemon_red_completion.battle_scenario_capture import open_battle_scenario_capture
from pokemon_red_completion.red_trainer_practice_episode import validate_opening_idle_frames

old = damage.old
ROOT = damage.ROOT
OUTPUT = old.PRIVATE / "red-interaction-damage-composition-20260923-v1"
V2 = old.PRIVATE / "red-interaction-damage-successor-20260923-v2"
CANDIDATE = V2 / "candidate-model.json"
CANDIDATE_SHA = "4ea4cfde342406d55e54650572fd9a7991c7fa5216698ff3ecf62109284398c3"
V2_PINS = {
    "PLAN.json": "cdb8267f853ceacc3256a39ca62ea054ef057ee0925b4031b2a12ff1acede9e0",
    "RESULT.json": "c0d8e0532c4c8dc491d37b630a65981aa32dc45b314add22d1495882ed9a73e8",
    "AUDIT.json": "d09765133b998b7fd78afaf96db6a2f494cef08f3afb1acf8ed84717da549379",
}
SEED = 23092331
LEVELS = (37, 41, 45, 49)
OFFSETS = (0, 6, 12)
MAX_SECONDS = 2700
CENSORED_STOPS = frozenset({"decision_budget", "unsupported_struggle_boundary"})
STATUS_MOVES = frozenset({79, 86, 77, 109, 105, 156, 115, 28, 50})


def read(path):
    return json.loads(path.read_bytes())


def require(condition, message):
    if not condition:
        raise ValueError(message)


def assert_models(admitted, candidate):
    baseline, proposed = dict(admitted.to_dict()), dict(candidate.to_dict())
    baseline.pop("damage_reference")
    proposed.pop("damage_reference")
    require(baseline == proposed, "non-damage component or metadata changed")


def exclusions():
    result = damage._prior_pairs()
    for path in (damage.OUTPUT, V2):
        result |= {
            tuple(sorted((family["actor"], family["enemy"])))
            for family in read(path / "PLAN.json")["inventory"]["families"]
        }
    return result


def build_teams(cartridge, catalog, sources, excluded):
    rng = random.Random(SEED)
    used = set(excluded)
    teams = []
    for index in range(24):
        level = LEVELS[index % 4]
        source = (index // 4 + index % 4) % 4
        own_count, foe_count = ((3, 3), (3, 6), (6, 6))[index // 8]
        eligible = sorted(
            s
            for s in cartridge.species_ids
            if s not in old.EXCLUDED_SPECIES
            and len(old.legal_damage(cartridge, catalog, s, level)) >= 2
        )
        for _ in range(10000):
            own = rng.sample(eligible, own_count)
            foe = rng.sample([s for s in eligible if s not in own], foe_count)
            pairs = {tuple(sorted((a, b))) for a in own for b in foe}
            if not pairs & used:
                used |= pairs
                break
        else:
            raise ValueError("input-only fresh team inventory exhausted")

        def member(species, slot, *, actor, level=level):
            return {
                "party_slot": slot,
                "species_ref": old.pokemon_red_species_ref(species),
                "national_number": cartridge.species(species).national_number,
                "level": level,
                "moves": old._team_moves(
                    cartridge, catalog, species, level, rng, status=actor and slot <= 2
                ),
            }

        own_members = [member(s, i, actor=True) for i, s in enumerate(own, 1)]
        foe_members = [member(s, i, actor=False) for i, s in enumerate(foe, 1)]
        practice = {"partition": "train", "battle_kind": "trainer"}
        for side, members in (("actor", own_members), ("opponent", foe_members)):
            for key in ("species_ref", "national_number", "level", "moves"):
                practice[f"{side}_{key}"] = members[0][key]
        practice.update(
            {
                "actor_hp": 1
                if index % 3 == 0
                else cartridge.species(own[0]).neutral_stats(level).max_hp,
                "opponent_hp": cartridge.species(foe[0]).trainer_stats(level).max_hp,
                "party_reserves": own_members[1:],
                "opponent_reserves": foe_members[1:],
                "opponent_party_count": foe_count,
            }
        )
        teams.append(
            {
                "id": f"team-{index:02d}",
                "role": "composition",
                "source_index": source,
                "root": sources[source][1]["source_id"],
                "level": level,
                "own_species": own,
                "opponent_species": foe,
                "roster": f"{own_count}v{foe_count}",
                "low_hp_lead": index % 3 == 0,
                "conditions": asdict(old.StatusPracticeConditions()),
                "practice": practice,
            }
        )
    return teams


def validate_teams(teams, cartridge, catalog, sources, excluded):
    require(len(teams) == 24 and len({t["id"] for t in teams}) == 24, "team inventory")
    require(Counter(t["roster"] for t in teams) == {"3v3": 8, "3v6": 8, "6v6": 8}, "roster balance")
    grid = Counter((t["source_index"], t["level"]) for t in teams)
    require(
        set(grid) == set(product(range(4), LEVELS))
        and max(grid.values()) - min(grid.values()) <= 1,
        "root/level crossing",
    )
    used = set(excluded)
    for team in teams:
        require(team["root"] == sources[team["source_index"]][1]["source_id"], "root join")
        spec = team["practice"]
        own, foe = team["own_species"], team["opponent_species"]
        require(not (set(own) | set(foe)) & old.EXCLUDED_SPECIES, "story species included")
        pairs = {tuple(sorted((a, b))) for a in own for b in foe}
        require(not pairs & used, "used species pair enters composition")
        used |= pairs
        source = sources[team["source_index"]][0]
        capture = open_battle_scenario_capture(
            source / "source.state", source / "source.state.json"
        )
        BattlePracticeSpec.from_dict(
            {
                **spec,
                "root_lineage_id": team["root"],
                "source_state_sha256": capture.manifest.state_sha256,
            }
        )
        for side, reserves, species_ids in (
            ("actor", "party_reserves", own),
            ("opponent", "opponent_reserves", foe),
        ):
            members = [{k: spec[f"{side}_{k}"] for k in ("species_ref", "level", "moves")}]
            members += spec[reserves]
            require([int(m["species_ref"][-3:]) for m in members] == species_ids, "roster join")
            for member in members:
                species = int(member["species_ref"][-3:])
                level = member["level"]
                require(level == team["level"], "member level join")
                legal = set(cartridge.species(species).teachable_moves_at_level(level))
                supported = set(old.legal_damage(cartridge, catalog, species, level)) | STATUS_MOVES
                moves = [int(m["move_ref"][-3:]) for m in member["moves"]]
                require(set(moves) <= legal & supported, "unsupported or own-level illegal move")
    return {
        "root_level_counts": {f"{r}:{level}": count for (r, level), count in sorted(grid.items())},
        "rosters": dict(Counter(t["roster"] for t in teams)),
        "low_hp_leads": sum(t["low_hp_lead"] for t in teams),
        "excluded_pairs": len(excluded),
        "new_team_pairs": len(used) - len(excluded),
    }


def preflight():
    for offset in OFFSETS:
        validate_opening_idle_frames(offset)
    require(not OUTPUT.exists(), "single-use composition identity consumed")
    require(old.sha(CANDIDATE) == CANDIDATE_SHA, "frozen candidate differs")
    for name, digest in V2_PINS.items():
        require(old.sha(V2 / name) == digest, "V2 evidence binding differs")
    cartridge, catalog, sources, _, admitted = old.inputs()
    candidate = old.TrainerPracticeThreeHeadModel.from_dict(read(CANDIDATE))
    assert_models(admitted, candidate)
    excluded = exclusions()
    teams = build_teams(cartridge, catalog, sources, excluded)
    coverage = validate_teams(teams, cartridge, catalog, sources, excluded)
    return cartridge, catalog, sources, admitted, candidate, teams, coverage


def play_arm(args, capture, model, directory, cartridge, offset):
    """Only named completed censored episodes are recoverable; no native retry."""
    require(not directory.exists(), "arm identity consumed")
    try:
        episode = old.lab.play(
            args,
            capture,
            model,
            directory,
            cartridge,
            offset=offset,
            status=True,
            learner_continuation=True,
        )
    except ValueError as error:
        if not (directory / "episode.json").is_file():
            raise
        episode = read(directory / "episode.json")
        stop = episode["stop_reason"]
        if stop not in CENSORED_STOPS or str(error) != f"unsupported stop {stop}":
            raise
        from audit_red_interaction_damage_successor import _audit_events

        _audit_events(directory, "run_finished")
    require(
        episode["stop_reason"] in CENSORED_STOPS | {"battle_won", "party_defeated"},
        "unexpected full-battle terminal",
    )
    metrics = old._composition_metrics(episode, directory)
    terminal = read(directory / "final-state.json")
    metrics.update(
        {
            "actual_actions": terminal["completed_actions"],
            "attempted_actions": terminal["attempted_actions"],
            "actual_frames": terminal["frame_delta"],
            "terminal_sha256": terminal["state_sha256"],
        }
    )
    return metrics


def deadline(start):
    if time.monotonic() - start >= MAX_SECONDS:
        raise TimeoutError("composition packet deadline")


def run(*, inspect=False):
    cartridge, _, sources, admitted, candidate, teams, coverage = preflight()
    if inspect:
        return {"preflight": "ready", "coverage": coverage, "episodes": 144}
    require(
        not subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip(),
        "native dispatch requires clean committed source",
    )
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    source_pins = damage._source_pins()
    for name in (
        "run_red_damage_composition.py",
        "audit_red_damage_composition.py",
        "audit_red_interaction_damage_successor.py",
    ):
        source_pins[f"scripts/{name}"] = old.sha(ROOT / "scripts" / name)
    protected = dict(read(V2 / "PLAN.json")["protected_inputs"])
    protected.update({str(V2 / name): digest for name, digest in V2_PINS.items()})
    protected[str(CANDIDATE)] = CANDIDATE_SHA
    for path, digest in protected.items():
        require(old.sha(Path(path)) == digest, "protected input changed before dispatch")
    plan = {
        "schema": "pokemon.red.frozen-damage-composition.v1",
        "source_commit": commit,
        "source_hashes": source_pins,
        "protected_inputs": protected,
        "seed": SEED,
        "teams": teams,
        "coverage": coverage,
        "offsets": OFFSETS,
        "orders": {
            f"{t['id']}:{offset}": (
                ["admitted", "candidate"] if (i + j) % 2 == 0 else ["candidate", "admitted"]
            )
            for i, t in enumerate(teams)
            for j, offset in enumerate(OFFSETS)
        },
        "budgets": {
            "episodes": 144,
            "packet_seconds": MAX_SECONDS,
            "arm_seconds": 45,
            "frames": 120000,
            "actions": 5000,
            "decisions": 80,
        },
        "censored_stops": sorted(CENSORED_STOPS),
        "fits": 0,
        "gates": {
            "illegal_actions_max": 0,
            "loss_increase_max": 0,
            "censor_increase_max": 0,
            "win_decrease_max": 0,
            "strict_gain": "wins or foes or mean normalized HP >= 0.02",
            "common_win_turn_pp_increase_max": 0.10,
            "common_wins_required": True,
        },
        "authority": "TRAIN full-battle choices; no promotion, story or independent-root claim",
    }
    OUTPUT.mkdir(mode=0o700)
    old.write_once(OUTPUT / "PLAN.json", plan)
    args = argparse.Namespace(output=OUTPUT, rom=old.ROM)
    pairs = []
    start = time.monotonic()
    active = None
    try:
        for team in teams:
            deadline(start)
            capture = old.lab.materialize(
                args, team, team["source_index"], sources, cartridge, commit
            )
            for offset in OFFSETS:
                key = f"{team['id']}:{offset}"
                arms = {}
                for arm in plan["orders"][key]:
                    deadline(start)
                    active = {"team": team["id"], "offset": offset, "arm": arm}
                    directory = OUTPUT / team["id"] / f"offset-{offset}-{arm}"
                    old.write_once(
                        directory.with_suffix(".claim.json"),
                        {
                            **active,
                            "plan_sha256": old.sha(OUTPUT / "PLAN.json"),
                            "elapsed_seconds": time.monotonic() - start,
                        },
                    )
                    arms[arm] = play_arm(
                        args,
                        capture,
                        admitted if arm == "admitted" else candidate,
                        directory,
                        cartridge,
                        offset,
                    )
                pair = {
                    "team_id": team["id"],
                    "roster": team["roster"],
                    "root": team["root"],
                    "offset": offset,
                    "arm_order": plan["orders"][key],
                    **arms,
                }
                old.write_once(OUTPUT / team["id"] / f"pair-{offset}.json", pair)
                pairs.append(pair)
                print(
                    json.dumps(
                        {
                            "pairs": len(pairs),
                            "team": team["id"],
                            "admitted": arms["admitted"]["stop_reason"],
                            "candidate": arms["candidate"]["stop_reason"],
                        }
                    ),
                    flush=True,
                )
        result = old.score_composition(
            pairs,
            plan,
            bindings={
                "plan_sha256": old.sha(OUTPUT / "PLAN.json"),
                "admitted_model_sha256": old.sha(old.ADMITTED),
                "candidate_model_sha256": CANDIDATE_SHA,
            },
        )
        result["native_elapsed_seconds"] = time.monotonic() - start
        for path, digest in protected.items():
            require(old.sha(Path(path)) == digest, "protected input changed")
        old.write_once(OUTPUT / "RESULT.json", result)
        return result["summary"] | {"gate_failures": result["gate_failures"]}
    except BaseException as error:
        old.write_once(
            OUTPUT / "FAILURE.json",
            {
                "type": type(error).__name__,
                "message": str(error),
                "active": active,
                "completed_pairs": len(pairs),
                "elapsed_seconds": time.monotonic() - start,
                "retry_allowed": False,
            },
        )
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight", action="store_true")
    print(json.dumps(run(inspect=parser.parse_args().preflight)))
