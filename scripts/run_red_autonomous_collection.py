"""Run bounded collection choices from an authenticated, private development plan."""

from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import subprocess
from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import Protocol, cast

from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING
from pokemon_red_completion.collection_protocol import committed_source_bundle_sha256
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.executor import (
    CountingExecutor,
    FrameSafeExecutor,
    ReadOnlyController,
    WindowedFrameBudgetController,
)
from pokemon_red_completion.goal_manager_composition_qualification import (
    HardCompositionActionLimiter,
)
from pokemon_red_completion.goal_manager_context_catalog import parse_goal_manager_context_capture
from pokemon_red_completion.observation import PokemonRedStateReader, RamAddress
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_autonomous_collection import (
    autonomous_collection_options,
    autonomous_evolution_continuation_bindings,
)
from pokemon_red_completion.red_autonomous_player import (
    AutonomousSnapshot,
    continuation_binding,
    run_autonomous_goal_continuation,
    run_autonomous_options,
)
from pokemon_red_completion.red_collection import (
    RED_COLLECTION_GAME_ID,
    red_internal_species_number,
    red_species_ref,
)
from pokemon_red_completion.red_goal_context import build_red_goal_context_runtime
from pokemon_red_completion.red_goal_context_profile import parse_red_goal_context_profile
from pokemon_red_completion.red_party import PokemonRedPartyReader
from pokemon_red_completion.red_player_model import (
    RedPlayerModelRecord,
    load_player_goal_model_record,
)
from pokemon_red_completion.red_registration_policy import RedRegistrationPolicy
from pokemon_red_completion.registration_memory import (
    RegistrationSnapshot,
    observation_from_collection,
)
from pokemon_red_completion.strategic_navigation_scenario_runtime import StrategicScenarioRouteWorld

ROOT = Path(__file__).resolve().parents[1]


class _TrainingWritableMemory(Protocol):
    def __setitem__(self, address: int, value: int) -> None: ...


def _apply_assisted_training_money(emulator: PyBoyAdapter, amount: int) -> tuple[int, int]:
    """Change only loaded WRAM money in this isolated development process.

    No controller or policy port exposes the backend's writable memory. This
    operation runs before a decision, against an in-memory restore, and its
    result is explicitly excluded from the ordinary goal-value fit.
    """
    if type(amount) is not int or not 0 <= amount <= 999_999:  # noqa: E721
        raise ValueError("assisted training money must be six-digit BCD")
    if emulator.frame_count != 0 or emulator.pressed_buttons:
        raise ValueError("assisted money requires an untouched loaded state")
    address = int(RamAddress.PLAYER_MONEY)
    previous = tuple(emulator.read_u8(address + offset) for offset in range(3))
    if any((byte >> 4) > 9 or (byte & 15) > 9 for byte in previous):
        raise ValueError("loaded Red money is not valid BCD")
    before = sum(((byte >> 4) * 10 + (byte & 15)) * 100 ** (2 - index)
                 for index, byte in enumerate(previous))
    digits = f"{amount:06d}"
    encoded = tuple(int(digits[index:index + 2], 10) for index in (0, 2, 4))
    bcd = tuple((value // 10 << 4) | value % 10 for value in encoded)
    memory = cast(
        _TrainingWritableMemory, emulator._require_backend().memory
    )  # Training-only trust boundary.
    for offset, value in enumerate(bcd):
        memory[address + offset] = value
    if tuple(emulator.read_u8(address + offset) for offset in range(3)) != bcd:
        raise ValueError("assisted money write did not read back exactly")
    return before, amount


def _verify_reserve_lineage(plan: dict[str, object], payloads: dict[str, bytes]) -> None:
    """Tie inherited party reserves to the exact earned parent outcome."""
    if "reserve_origin" not in plan:
        if "prior_plan" in plan or "prior_outcome" in plan:
            raise ValueError("prior outcome requires a reserve origin")
        return
    if "prior_plan" not in payloads or "prior_outcome" not in payloads:
        raise ValueError("inherited reserves require authenticated parent evidence")
    parent = json.loads(payloads["prior_plan"])
    outcome = json.loads(payloads["prior_outcome"])
    provenance = parent["provenance"]
    reserve = plan["reserve_origin"]
    state = plan["state"]
    assert isinstance(reserve, dict) and isinstance(state, dict)
    if (
        parent["schema"] not in {
            "pokemon.red.autonomous-option-run.v1",
            "pokemon.red.autonomous-goal-continuation.v1",
        }
        or provenance["parent_state_sha256"] != outcome["before_state_sha256"]
        or outcome["terminal_state_sha256"] != state["sha256"]
        or outcome["safe_terminal"] is not True
        or provenance.get(
            "reserve_origin_state_sha256", outcome["before_state_sha256"]
        ) != reserve["sha256"]
    ):
        raise ValueError("inherited reserves do not match the earned parent lineage")


def _verify_goal_continuation(plan: dict[str, object], payloads: dict[str, bytes]) -> str:
    """Authenticate the consumed model choice before carrying its goal forward."""
    if "prior_execution_started" not in payloads:
        raise ValueError("continuation requires authenticated selected-goal evidence")
    _verify_reserve_lineage(plan, payloads)
    started = json.loads(payloads["prior_execution_started"])
    outcome = json.loads(payloads["prior_outcome"])
    parent = json.loads(payloads["prior_plan"])
    binding_ref = started["selected_binding_ref"]
    state = plan["state"]
    assert isinstance(state, dict)
    common = (
        started["selected_kind"] == "evolve_species"
        and started["state_sha256"] == outcome["before_state_sha256"]
        and outcome["safe_terminal"] is True
        and outcome["terminal_state_sha256"] == state["sha256"]
        and isinstance(binding_ref, str)
    )
    if parent["schema"] == "pokemon.red.autonomous-option-run.v1":
        choice = outcome["choice"]
        authorized = (
            outcome["selected_kind"] == "evolve_species"
            and started["menu_sha256"] == choice["menu_sha256"]
            and choice["mode"] == "model_exploration"
            and choice["model_sha256"] == parent["model_sha256"]
            and outcome["learning_eligible"] is True
            and outcome["error_type"] == "CompositionActionBudgetExhausted"
        )
    else:
        if "prior_result" not in payloads:
            raise ValueError("continuation parent requires authenticated result")
        result = json.loads(payloads["prior_result"])
        authorized = (
            parent["schema"] == "pokemon.red.autonomous-goal-continuation.v1"
            and result["status"] == "pending"
            and result["model_queries"] == 0
            and result["outcome"] == outcome
            and outcome["model_queries"] == 0
            and outcome["learning_eligible"] is False
            and started["prior_binding_ref"] == parent["prior_binding_ref"]
            and binding_ref.rsplit(":", 1)[-1]
            == parent["prior_binding_ref"].rsplit(":", 1)[-1]
        )
    if not common or not authorized:
        raise ValueError("continuation does not match the consumed model goal")
    return binding_ref


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--inspect", action="store_true")
    args = parser.parse_args()
    plan_bytes = args.plan.read_bytes()
    plan = json.loads(plan_bytes)
    assisted_money = plan.get("assisted_training_money")
    if assisted_money is not None and plan.get("mode") == "continue_selected_goal":
        raise ValueError("assisted money cannot rewrite a previously selected goal")
    payloads = {}
    for key in (
        "rom", "state", "checkpoint", "profile", "model",
        "reserve_origin", "prior_plan", "prior_outcome", "prior_execution_started",
        "prior_result",
    ):
        if key in {
            "reserve_origin", "prior_plan", "prior_outcome", "prior_execution_started",
            "prior_result",
        } and key not in plan:
            continue
        content = Path(plan[key]["path"]).read_bytes()
        if hashlib.sha256(content).hexdigest() != plan[key]["sha256"]:
            raise ValueError(f"autonomous {key} authentication failed")
        payloads[key] = content
    _verify_reserve_lineage(plan, payloads)
    continuation_ref = (
        _verify_goal_continuation(plan, payloads)
        if plan.get("mode") == "continue_selected_goal" else None
    )
    output = Path(plan["output"])
    if output.exists() and not args.inspect:
        raise FileExistsError("autonomous continuation is already claimed")
    status = subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True)
    if status and not args.inspect:
        raise ValueError("commit the reviewed source before autonomous execution")
    model = load_player_goal_model_record(
        Path(plan["model"]["path"]),
        expected_model_sha256=plan["model_sha256"],
    )
    if (
        not isinstance(model, RedPlayerModelRecord)
        or model.objective != "pokemon.registered-collection.v1"
    ):
        raise ValueError("autonomous player requires its registered model")
    envelope = dict(json.loads(payloads["checkpoint"])["envelope"])
    envelope.update(
        state_sha256=plan["state"]["sha256"],
        checkpoint_id=plan["run_id"],
        checkpoint_label="Autonomous development continuation",
    )
    original_capture = parse_goal_manager_context_capture(
        payloads["state"],
        (json.dumps(envelope, sort_keys=True, separators=(",", ":")) + "\n").encode(),
    )
    profile = parse_red_goal_context_profile(payloads["profile"])
    world = StrategicScenarioRouteWorld.from_rom(payloads["rom"])
    maximum_actions = plan["maximum_actions"]
    maximum_frames = plan["maximum_frames"]
    provenance = {
        "plan_sha256": hashlib.sha256(plan_bytes).hexdigest(),
        "source_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "source_bundle_sha256": committed_source_bundle_sha256(ROOT),
        "source_dirty": bool(status),
        "rom_sha256": plan["rom"]["sha256"],
        "parent_state_sha256": original_capture.state_sha256,
        "model_file_sha256": model.file_sha256,
        "maximum_actions": maximum_actions,
        "maximum_frames": maximum_frames,
        "initial_profile_sha256": profile.profile_sha256,
        "reserve_origin_state_sha256": (
            plan["reserve_origin"]["sha256"] if "reserve_origin" in plan
            else plan["state"]["sha256"]
        ),
        "goal_authority": "model_or_declared_equivalent_exploration",
        "capture_destination_authority": "model_over_up_to_eight_observed_routes",
        "evolution_target_authority": "model_for_contrasts_uniform_for_equivalent_targets",
        "battle_move_authority": "existing_heuristic_controller",
    }
    with PyBoyAdapter(Path(plan["rom"]["path"]), watch=False, speed=None) as emulator:
        original_reserves = None
        if "reserve_origin" in payloads:
            emulator.load_state_bytes(payloads["reserve_origin"])
            original_reserves = Counter(
                red_species_ref(red_internal_species_number(member.species_id))
                for member in PokemonRedPartyReader(emulator).read().members
            )
        emulator.load_state_bytes(payloads["state"])
        capture = original_capture
        if assisted_money is not None:
            prior_money, injected_money = _apply_assisted_training_money(
                emulator, assisted_money
            )
            assisted_state = emulator.save_state_bytes()
            assisted_sha256 = hashlib.sha256(assisted_state).hexdigest()
            assisted_envelope = dict(envelope, state_sha256=assisted_sha256)
            capture = parse_goal_manager_context_capture(
                assisted_state,
                (
                    json.dumps(assisted_envelope, sort_keys=True, separators=(",", ":"))
                    + "\n"
                ).encode(),
            )
            provenance["parent_state_sha256"] = assisted_sha256
            provenance["training_assistance"] = {
                "kind": "money_override",
                "source_state_sha256": original_capture.state_sha256,
                "assisted_state_sha256": assisted_sha256,
                "money_before": prior_money,
                "money_after": injected_money,
                "learning_admission": "mechanics_only_no_goal_value_fit",
                "final_run_eligible": False,
            }
        initial_frame = emulator.frame_count
        budget = WindowedFrameBudgetController(
            emulator,
            maximum_frames_per_window=maximum_frames,
            maximum_total_frames=maximum_frames,
        )
        controller = ReadOnlyController(budget) if args.inspect else budget
        reader = PokemonRedStateReader(controller)
        limiter = HardCompositionActionLimiter(
            FrameSafeExecutor(controller, DEFAULT_NEW_GAME_TIMING.controller_timing()),
            maximum_actions_per_decision=maximum_actions,
            maximum_episode_actions=maximum_actions,
        )
        actions = CountingExecutor(limiter)
        runtime = build_red_goal_context_runtime(
            profile=profile,
            capture=capture,
            emulator=controller,
            reader=reader,
        )
        initial = runtime.adapter.observe().collection_observation
        registration = observation_from_collection(
            initial,
            seen_species=initial.owned_species,
            national_ids={red_species_ref(n): n for n in range(1, 152)},
            run_id=plan["run_id"],
            game_id=RED_COLLECTION_GAME_ID,
            adapter_id="red-autonomous-collection-v1",
            cartridge_sha256=plan["rom"]["sha256"],
            snapshot_sha256=capture.state_sha256,
            sequence=0,
        )
        protected = (
            original_reserves if original_reserves is not None
            else Counter(s.species_ref for s in initial.specimens if s.location.value == "party")
        )
        policy = RedRegistrationPolicy(
            RegistrationSnapshot((registration,)),
            plan["run_id"],
            capture.state_sha256,
            initial,
            protected,
            completion_scope="local_red",
        )
        runtime = replace(runtime, registration_policy=policy)

        def snapshot():
            state = emulator.save_state_bytes()
            facts = {
                "actions": limiter.attempted_actions,
                "completed_actions": actions.actions_executed,
                "frames": emulator.frame_count - initial_frame,
            }
            try:
                current = runtime.adapter.observe()
                collection = current.collection_observation
                policy.registered(collection)
                counts = Counter(s.species_ref for s in collection.specimens)
                safe = (
                    not current.raw.battle_state
                    and current.input_ready
                    and not emulator.pressed_buttons
                    and all(counts[s] >= count for s, count in protected.items())
                )
                facts.update(
                    {
                        "party_training": [
                            [member.slot, member.species_id, member.experience]
                            for member in PokemonRedPartyReader(emulator).read().members
                        ],
                        "cash": current.raw.player_money,
                        "registered_species": len(collection.owned_species),
                        "owned_species": sorted(collection.owned_species),
                        "specimen_counts": dict(counts),
                        "living_species": len(counts),
                        "specimens": len(collection.specimens),
                        "map_id": int(current.raw.map_id),
                        "position_yx": [current.raw.player_y, current.raw.player_x],
                        "battle_state": current.raw.battle_state,
                        "input_ready": current.input_ready,
                        "bag_items": current.raw.bag_items,
                    }
                )
            except Exception as error:
                safe = False
                facts.update({"observation_error": str(error), "error_type": type(error).__name__})
            return AutonomousSnapshot(state, facts, safe)

        def observe(ordinal):
            limiter.begin_decision_window()
            budget.begin_window()
            return autonomous_collection_options(
                runtime,
                actions,
                world,
                model_feature_version=model.model.feature_version,
                ordering_seed_sha256=canonical_sha256(
                    {
                        "schema": "pokemon.red.autonomous-option-ordering.v1",
                        "run_id": plan["run_id"],
                        "ordinal": ordinal,
                        "state_sha256": snapshot().sha256,
                    }
                ),
                maximum_actions=maximum_actions,
                maximum_frames=maximum_frames,
                maximum_evolution_quanta=(
                    plan.get("maximum_evolution_quanta", 128)
                    if continuation_ref is not None else 128
                ),
            )

        def observe_targeted():
            limiter.begin_decision_window()
            budget.begin_window()
            return autonomous_evolution_continuation_bindings(
                runtime, actions, world,
                maximum_actions=maximum_actions,
                maximum_frames=maximum_frames,
                maximum_quanta=plan["maximum_evolution_quanta"],
            )

        if args.inspect:
            before = snapshot()
            if not before.safe:
                raise ValueError(f"unsafe inspection origin: {before.facts}")
            if continuation_ref is not None and plan.get("targeted_rebinding") is True:
                bindings = observe_targeted()
                after = snapshot()
                if before != after:
                    raise ValueError("targeted evolution inspection changed the game")
                selected = continuation_binding(bindings, continuation_ref)
                print(json.dumps({
                    "status": "verified_action_free",
                    "binding_scope": "targeted_evolution",
                    "facts": before.facts,
                    "private_binding_refs": [binding.binding_ref for binding in bindings],
                    "matching_ref": selected.binding_ref,
                    "model_queries": 0,
                }, indent=2, sort_keys=True))
                return
            options = observe(0)
            after = snapshot()
            if before != after:
                raise ValueError("autonomous inspection changed the game")
            print(
                json.dumps(
                    {
                        "status": "verified_action_free",
                        "training_assistance": provenance.get("training_assistance"),
                        "facts": before.facts,
                        "menu": options.public_dict(),
                        "private_binding_kinds": [b.kind.value for b in options.bindings],
                        "private_binding_refs": [b.binding_ref for b in options.bindings],
                        "distinct_semantic_candidates": len(
                            {
                                options.menu.candidate_vector(
                                    i, feature_version=model.model.feature_version
                                )
                                for i in options.menu.available_indices
                            }
                        ),
                        "model_queries": 0,
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return
        # Seed is generated once before any score is queried and persisted by
        # the runner. It is not searched for a preferred outcome.
        if continuation_ref is not None:
            result = run_autonomous_goal_continuation(
                output=output,
                snapshot=snapshot,
                observe=observe,
                prior_binding_ref=continuation_ref,
                prior_outcome_sha256=plan["prior_outcome"]["sha256"],
                provenance=provenance,
                targeted_observe=(
                    observe_targeted if plan.get("targeted_rebinding") is True else None
                ),
            )
        else:
            result = run_autonomous_options(
                model=model.model,
                output=output,
                snapshot=snapshot,
                observe=observe,
                seed=secrets.randbits(64),
                maximum_decisions=plan["maximum_decisions"],
                maximum_seconds=plan["maximum_seconds"],
                provenance=provenance,
            )
        print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
