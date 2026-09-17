"""One source-bound, claim-first Red battle-training episode in the Mansion."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from pokemon_red_completion.battle_neural_model import MaskedMLPMoveRanker
from pokemon_red_completion.battle_outcome_capture_authentication import (
    BattleScenarioSourceBinding,
    authenticate_battle_scenario_source_binding,
)
from pokemon_red_completion.battle_runtime import advance_battle_to_policy_boundary
from pokemon_red_completion.battle_scenario_source_venue import battle_scenario_source_venue
from pokemon_red_completion.blaine import MANSION_TRAINING_VENUE
from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING
from pokemon_red_completion.claim_first_admission import (
    ClaimFirstRootPair,
    claim_first_pair_registry,
)
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.executor import (
    CountingExecutor,
    FrameBudgetController,
    FrameSafeExecutor,
)
from pokemon_red_completion.goal_manager_composition_qualification import (
    HardCompositionActionLimiter,
    fixed_account_claim_registry_lease,
    open_fixed_account_claim_registry,
    root_claim_is_available,
)
from pokemon_red_completion.goal_manager_context_catalog import parse_goal_manager_context_catalog
from pokemon_red_completion.goal_manager_protocol import (
    load_committed_goal_manager_registry_at_revision,
)
from pokemon_red_completion.observation import MapId, PokemonRedStateReader, RamAddress
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_autonomous_player import _record, _write
from pokemon_red_completion.red_battle_scenario import red_battle_supported_move_count
from pokemon_red_completion.red_model_battle_episode import run_model_battle_train_episode
from pokemon_red_completion.red_trajectory import PokemonRedObservationEncoder
from pokemon_red_completion.scenario_lab import ScenarioPartition

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "pokemon.red.model-battle-mansion-train-plan.v1"
ROM_SHA256 = "5ca7ba01642a3b27b0cc0b5349b52792795b62d3ed977e98a09390659af96b7b"


def _file(record: object, subject: str) -> bytes:
    if not isinstance(record, dict) or set(record) != {"path", "sha256"}:
        raise ValueError(f"{subject} input record differs")
    path, digest = record["path"], record["sha256"]
    if not isinstance(path, str) or not isinstance(digest, str):
        raise ValueError(f"{subject} input identity differs")
    payload = Path(path).read_bytes()
    if hashlib.sha256(payload).hexdigest() != digest:
        raise ValueError(f"{subject} input hash differs")
    return payload


def _limits(plan: dict[str, object]) -> dict[str, int]:
    ceilings = {
        "maximum_encounters": 4,
        "maximum_decisions": 16,
        "maximum_decisions_per_encounter": 8,
        "maximum_actions": 1600,
        "maximum_frames": 150000,
        "maximum_encounter_walks": 128,
    }
    limits: dict[str, int] = {}
    for key, ceiling in ceilings.items():
        value = plan.get(key)
        if type(value) is not int or not 1 <= value <= ceiling:  # noqa: E721
            raise ValueError(f"battle episode {key} bound differs")
        limits[key] = value
    return limits


def _authenticate(
    plan: dict[str, object], plan_bytes: bytes
) -> tuple[BattleScenarioSourceBinding, bytes, bytes, bytes, dict[str, int], str]:
    if plan.get("schema") != SCHEMA:
        raise ValueError("unsupported battle episode plan")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip():
        raise ValueError("commit bounded implementation before gameplay")
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    if plan.get("source_commit") != revision:
        raise ValueError("prospective battle episode source commit differs")
    limits = _limits(plan)
    rom = _file(plan.get("rom"), "ROM")
    if hashlib.sha256(rom).hexdigest() != ROM_SHA256:
        raise ValueError("battle episode Red ROM differs")
    state = _file(plan.get("state"), "source state")
    model = _file(plan.get("model"), "battle model")
    catalog_bytes = _file(plan.get("context_catalog"), "context catalog")
    registry_commit = plan.get("registry_source_commit")
    if not isinstance(registry_commit, str):
        raise ValueError("historical registry commit differs")
    registry = load_committed_goal_manager_registry_at_revision(ROOT, registry_commit)
    if registry.registry_sha256 != plan.get("registry_sha256"):
        raise ValueError("historical registry hash differs")
    catalog = parse_goal_manager_context_catalog(catalog_bytes, registry)
    binding = authenticate_battle_scenario_source_binding(
        hashlib.sha256(state).hexdigest(),
        expected_partition=ScenarioPartition.TRAIN,
        catalog=catalog,
        registry=registry,
    )
    if (
        binding.source_slot_id != plan.get("source_slot_id")
        or binding.root_lineage_id != plan.get("root_lineage_id")
        or plan.get("expected_venue_id") != "pokemon_mansion_1f"
    ):
        raise ValueError("prospective train source or venue differs")
    output = plan.get("output")
    if not isinstance(output, str) or Path(output).exists():
        raise ValueError("battle episode output must be new")
    if not plan_bytes:
        raise ValueError("empty battle episode plan")
    return binding, state, model, rom, limits, revision


def _claim(binding: BattleScenarioSourceBinding, plan_bytes: bytes, revision: str) -> str:
    logical = canonical_sha256({"root_lineage_id": binding.root_lineage_id})
    physical = binding.root_consumption_sha256
    pair = ClaimFirstRootPair(
        logical_root_sha256=logical,
        physical_root_sha256=physical,
        stage="train-model-battle-episode",
        execution_identity_sha256=canonical_sha256(
            {
                "plan_sha256": hashlib.sha256(plan_bytes).hexdigest(),
                "root_lineage_id": binding.root_lineage_id,
                "source_commit": revision,
            }
        ),
        plan_sha256=hashlib.sha256(plan_bytes).hexdigest(),
        slot_sha256=canonical_sha256({"source_slot_id": binding.source_slot_id}),
        runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        source_commit=revision,
    )
    with claim_first_pair_registry(open_fixed_account_claim_registry()) as ledger:
        ledger.claim(pair)
    return pair.claim_sha256


def run(plan_path: Path, *, check_only: bool = False) -> dict[str, object]:
    plan_bytes = plan_path.read_bytes()
    plan = json.loads(plan_bytes)
    if not isinstance(plan, dict):
        raise ValueError("battle episode plan must be an object")
    binding, state, model_bytes, _, limits, revision = _authenticate(plan, plan_bytes)
    model = MaskedMLPMoveRanker.from_dict(json.loads(model_bytes))
    output = Path(plan["output"])
    with PyBoyAdapter(Path(plan["rom"]["path"]), watch=False, speed=None) as emulator:
        emulator.load_state_bytes(state)
        initial_frame = emulator.frame_count
        reader = PokemonRedStateReader(emulator)
        raw = reader.read()
        venue = battle_scenario_source_venue(
            raw,
            last_blackout_map=reader.read_last_blackout_map(),
            current_map_tileset=emulator.read_u8(RamAddress.CURRENT_MAP_TILESET),
        )
        if (
            venue.source_map != int(MapId.CINNABAR_POKECENTER)
            or venue.encounter_map != int(MapId.POKEMON_MANSION_1F)
            or (raw.player_x, raw.player_y) not in {(3, 3), (3, 7)}
            or raw.party_count is None
            or raw.party_count < 1
            or raw.party_hp is None
            or raw.party_hp[0] <= 0
            or raw.party_moves is None
            or raw.party_pp is None
            or red_battle_supported_move_count(raw.party_moves[0], raw.party_pp[0]) < 2
            or not reader.read_input_readiness().ready
            or emulator.frame_count != initial_frame
        ):
            raise ValueError("source is not a ready, choice-rich Mansion transition")
        registry_path = open_fixed_account_claim_registry()
        with fixed_account_claim_registry_lease(registry_path, exclusive=False):
            if not root_claim_is_available(registry_path, binding.root_consumption_sha256):
                raise ValueError("prospective training source root is already consumed")
        if check_only:
            return {
                "status": "action_free_preflight_passed",
                "root_lineage_id": binding.root_lineage_id,
                "source_slot_id": binding.source_slot_id,
                "venue_id": venue.venue_id,
                "controller_actions": 0,
                "emulator_frames": 0,
                "root_claims_created": 0,
            }
        budget = FrameBudgetController(emulator, maximum_frames=limits["maximum_frames"])
        reader = PokemonRedStateReader(budget)
        limiter = HardCompositionActionLimiter(
            FrameSafeExecutor(budget, DEFAULT_NEW_GAME_TIMING.controller_timing()),
            maximum_actions_per_decision=limits["maximum_actions"],
            maximum_episode_actions=limits["maximum_actions"],
        )
        actions = CountingExecutor(limiter)
        walker = MANSION_TRAINING_VENUE.fresh_walk_to_grass()
        claim_sha256 = _claim(binding, plan_bytes, revision)
        _record(
            plan_path.parent / "claim-receipt.json",
            {
                "schema": "pokemon.red.model-battle-train-claim.v1",
                "claim_sha256": claim_sha256,
                "root_lineage_id": binding.root_lineage_id,
                "source_state_sha256": binding.source_state_sha256,
                "plan_sha256": hashlib.sha256(plan_bytes).hexdigest(),
            },
        )

        def setup(index: int) -> None:
            if index == 0:
                MANSION_TRAINING_VENUE.heal_and_return(actions, reader, budget)
            raw_field = reader.read()
            if raw_field.map_id != MapId.POKEMON_MANSION_1F or raw_field.battle_state != 0:
                raise ValueError("encounter setup left the declared Mansion field")
            steps = 0
            calls = 0
            while reader.read().battle_state == 0:
                calls += 1
                if calls > 4 * limits["maximum_encounter_walks"]:
                    raise RuntimeError("natural encounter walker made no bounded progress")
                steps += walker(actions, reader, budget)
                if steps > limits["maximum_encounter_walks"]:
                    raise RuntimeError("natural encounter exceeded its walk bound")
            advance_battle_to_policy_boundary(
                reader,
                actions,
                expected_map=int(MapId.POKEMON_MANSION_1F),
                expected_battle_state=1,
                timing=MANSION_TRAINING_VENUE.battle_timing,
                label="model-owned natural Mansion encounter",
            )

        try:
            report = run_model_battle_train_episode(
                output=output,
                source=binding,
                reader=reader,
                executor=actions,
                encoder=PokemonRedObservationEncoder.from_state_reader(reader),
                model=model,
                snapshot=emulator.save_state_bytes,
                costs=lambda: {
                    "actions": actions.actions_executed,
                    "attempted_actions": limiter.attempted_actions,
                    "frames": emulator.frame_count - initial_frame,
                },
                setup_encounter=setup,
                expected_map=int(MapId.POKEMON_MANSION_1F),
                maximum_encounters=limits["maximum_encounters"],
                maximum_decisions=limits["maximum_decisions"],
                maximum_decisions_per_encounter=limits["maximum_decisions_per_encounter"],
                maximum_actions=limits["maximum_actions"],
                maximum_frames=limits["maximum_frames"],
                timing=MANSION_TRAINING_VENUE.battle_timing,
            )
        except Exception as error:
            _write(plan_path.parent / "failure-terminal.state", emulator.save_state_bytes())
            _record(
                plan_path.parent / "failure.json",
                {
                    "error_type": type(error).__name__,
                    "error_message": str(error),
                    "root_lineage_id": binding.root_lineage_id,
                    "claim_sha256": claim_sha256,
                },
            )
            raise
        _record(
            plan_path.parent / "episode-summary.json",
            {
                "stop_reason": report["stop_reason"],
                "model_queries": report["model_queries"],
                "completed_decisions": report["completed_decisions"],
                "distinct_semantic_decisions": report["distinct_semantic_decisions"],
                "claim_sha256": claim_sha256,
                "teacher_battle_fallbacks": 0,
                "fit_eligible_examples": 0,
                "authority_promoted": False,
            },
        )
        return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    report = run(args.plan, check_only=args.check_only)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 2 if report.get("stop_reason") == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
