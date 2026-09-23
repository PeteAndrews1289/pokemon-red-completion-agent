"""Run bounded collection choices from an authenticated, private development plan."""

from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import subprocess
from collections import Counter
from dataclasses import asdict, replace
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
    _record,
    continuation_binding,
    run_assisted_safari_probe,
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
from pokemon_red_completion.red_learned_trainer import (
    FrozenTrainerBattler,
    load_frozen_trainer_model,
)
from pokemon_red_completion.red_native_boxed_evolution import validate_native_evolution_quanta
from pokemon_red_completion.red_paid_safari_departure import (
    EXIT_SCHEMA,
    bind_paid_safari_departure,
    run_paid_safari_departure,
    verify_departure_parent,
)
from pokemon_red_completion.red_paid_safari_lineage import (
    PAID_RECORDS,
    verify_paid_safari_lineage,
    verify_paid_safari_live_facts,
)
from pokemon_red_completion.red_party import PokemonRedPartyReader
from pokemon_red_completion.red_player_model import (
    RedPlayerModelRecord,
    load_player_goal_model_record,
)
from pokemon_red_completion.red_registration_policy import RedRegistrationPolicy
from pokemon_red_completion.red_safari_lineage import (
    EXACT_PLAN,
    load_safari_lineage,
    verify_completed_safari,
    verify_safari_terminal_facts,
)
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
    before = sum(
        ((byte >> 4) * 10 + (byte & 15)) * 100 ** (2 - index) for index, byte in enumerate(previous)
    )
    digits = f"{amount:06d}"
    encoded = tuple(int(digits[index : index + 2], 10) for index in (0, 2, 4))
    bcd = tuple((value // 10 << 4) | value % 10 for value in encoded)
    memory = cast(
        _TrainingWritableMemory, emulator._require_backend().memory
    )  # Training-only trust boundary.
    for offset, value in enumerate(bcd):
        memory[address + offset] = value
    if tuple(emulator.read_u8(address + offset) for offset in range(3)) != bcd:
        raise ValueError("assisted money write did not read back exactly")
    return before, amount


def _verified_battle_settlement_state(
    plan: dict[str, object], payloads: dict[str, bytes],
) -> str | None:
    """Join a defensive escape to the unchanged original model-goal receipt."""
    keys = {"settlement_plan", "settlement_outcome"}
    if not keys.intersection(plan):
        return None
    if not keys <= payloads.keys() or plan.get("mode") != "continue_selected_goal":
        raise ValueError("battle settlement requires a complete selected-goal chain")
    settled_plan = json.loads(payloads["settlement_plan"])
    settled = json.loads(payloads["settlement_outcome"])
    original = json.loads(payloads["prior_outcome"])
    started = json.loads(payloads["prior_execution_started"])
    result = json.loads(payloads["prior_result"])
    state = plan["state"]
    assert isinstance(state, dict)
    if (
        settled_plan.get("schema") != "pokemon.red.evolution-battle-settlement.v1"
        or settled_plan.get("prior_outcome_sha256")
        != hashlib.sha256(payloads["prior_outcome"]).hexdigest()
        or settled_plan.get("parent_state_sha256") != original.get("terminal_state_sha256")
        or settled_plan.get("prior_binding_ref") != started.get("selected_binding_ref")
        or result.get("schema") != "pokemon.red.autonomous-option-result.v1"
        or result.get("stop_reason") != "execution_failed"
        or result.get("model_sha256") != original.get("choice", {}).get("model_sha256")
        or not result.get("outcomes") or result["outcomes"][-1] != original
        or original.get("selected_kind") != "evolve_species"
        or original.get("safe_terminal") is not False
        or original.get("error_type") not in {
            "CompositionActionBudgetExhausted", "ControllerFrameBudgetExhausted",
        }
        or original.get("after", {}).get("battle_state") != 1
        or settled.get("before_state_sha256") != original.get("terminal_state_sha256")
        or settled.get("terminal_state_sha256") != state.get("sha256")
        or settled.get("safe_terminal") is not True
        or settled.get("verification") != "defensive_escape"
        or settled.get("error") is not None
        or settled.get("model_queries") != 0 or type(settled.get("model_queries")) is not int
        or settled.get("learning_eligible") is not False
        or settled.get("after", {}).get("battle_state") != 0
        or settled.get("after", {}).get("input_ready") is not True
    ):
        raise ValueError("battle settlement differs from the retained evolution chain")
    for cost, cap, ceiling in (("actions", "maximum_actions", 1000),
                               ("frames", "maximum_frames", 120000)):
        if (type(settled.get(cost)) is not int or type(settled_plan.get(cap)) is not int
                or not 0 <= settled[cost] <= settled_plan[cap] <= ceiling):
            raise ValueError("battle settlement cost is invalid")
    for key in ("owned_species", "specimen_counts", "cash", "bag_items", "map_id"):
        if (key not in settled.get("before", {})
                or settled["before"][key] != original["after"].get(key)
                or settled["before"][key] != settled.get("after", {}).get(key)):
            raise ValueError("battle settlement changed protected resources")
    return str(settled["terminal_state_sha256"])


def _verify_reserve_lineage(
    plan: dict[str, object], payloads: dict[str, bytes], *, field_settlement: bool = False
) -> None:
    """Tie inherited party reserves to the exact earned parent outcome."""
    if any(key in plan for key in PAID_RECORDS):
        if field_settlement or plan.get("mode") not in {None, "exit_paid_safari"}:
            raise ValueError("paid Safari admission requires ordinary collection")
        verify_paid_safari_lineage(plan, payloads)
        original = json.loads(payloads["prior_outcome"])
        parent_plan = {key: value for key, value in plan.items() if key not in PAID_RECORDS}
        parent_plan["state"] = {"sha256": original["terminal_state_sha256"]}
        _verify_reserve_lineage(parent_plan, payloads)
        if "reserve_origin" not in parent_plan:
            raise ValueError("paid Safari requires inherited reserves")
        return
    if "reserve_origin" not in plan:
        if "prior_plan" in plan or "prior_outcome" in plan:
            raise ValueError("prior outcome requires a reserve origin")
        return
    if "prior_plan" not in payloads or "prior_outcome" not in payloads:
        raise ValueError("inherited reserves require authenticated parent evidence")
    parent = json.loads(payloads["prior_plan"])
    outcome = json.loads(payloads["prior_outcome"])
    if parent.get("schema") == EXIT_SCHEMA:
        verify_departure_parent(parent, outcome, payloads)
    if parent.get("schema") == EXACT_PLAN:
        if field_settlement or "safari_lineage" not in payloads:
            raise ValueError("completed Safari requires authenticated lineage, not settlement")
        verify_completed_safari(plan, payloads, load_safari_lineage(payloads["safari_lineage"]))
        return
    provenance = parent["provenance"]
    battle_settled_state = _verified_battle_settlement_state(plan, payloads)
    reserve = plan["reserve_origin"]
    state = plan["state"]
    assert isinstance(reserve, dict) and isinstance(state, dict)
    settlement_source = (
        field_settlement
        and outcome.get("error_type") == "ControllerFrameBudgetExhausted"
        and outcome.get("safe_terminal") is False
        and outcome.get("after", {}).get("battle_state") == 0
        and outcome.get("after", {}).get("input_ready") is False
    )
    failed_settlement = (
        field_settlement
        and parent["schema"] == "pokemon.red.field-settlement.v1"
        and outcome.get("safe_terminal") is False
        and outcome.get("model_queries") == 0
        and 0 <= outcome.get("neutral_frames", -1) <= 64
        and isinstance(outcome.get("error"), dict)
    )
    settlement_source = settlement_source or failed_settlement or battle_settled_state is not None
    parent_state = provenance["parent_state_sha256"]
    connected = parent_state == outcome["before_state_sha256"]
    if not connected and "prior_result" in payloads:
        result = json.loads(payloads["prior_result"])
        rows = result.get("outcomes", [])
        # Later decisions inherit the original reserve only through the exact,
        # authenticated result chain. Never skip an intervening failed state.
        if (
            parent["schema"] == "pokemon.red.autonomous-option-run.v1"
            and result.get("schema") == "pokemon.red.autonomous-option-result.v1"
            and result.get("model_sha256") == parent.get("model_sha256")
            and rows
            and rows[-1] == outcome
        ):
            connected = True
            for ordinal, row in enumerate(rows):
                if (
                    row.get("ordinal") != ordinal
                    or row.get("before_state_sha256") != parent_state
                    or (
                        row.get("safe_terminal") is not True
                        and not (row == outcome and settlement_source)
                    )
                ):
                    connected = False
                    break
                parent_state = row.get("terminal_state_sha256")
    if (
        parent["schema"]
        not in {
            "pokemon.red.autonomous-option-run.v1",
            "pokemon.red.autonomous-goal-continuation.v1",
            "pokemon.red.field-settlement.v1",
            EXIT_SCHEMA,
        }
        or not connected
        or (battle_settled_state or outcome["terminal_state_sha256"]) != state["sha256"]
        or (outcome["safe_terminal"] is not True and not settlement_source)
        or provenance.get("reserve_origin_state_sha256", provenance["parent_state_sha256"])
        != reserve["sha256"]
    ):
        raise ValueError("inherited reserves do not match the earned parent lineage")
    if (
        parent["schema"] == "pokemon.red.field-settlement.v1"
        and not failed_settlement
        and (
            outcome.get("verification") != "field_ready"
            or outcome.get("model_queries") != 0
            or not 0 <= outcome.get("neutral_frames", -1) <= 64
            or outcome.get("preserved_resources") is not True
        )
    ):
        raise ValueError("inherited reserves do not match verified field settlement")


def _verify_goal_continuation(plan: dict[str, object], payloads: dict[str, bytes]) -> str:
    """Authenticate the consumed model choice before carrying its goal forward."""
    if "prior_execution_started" not in payloads:
        raise ValueError("continuation requires authenticated selected-goal evidence")
    _verify_reserve_lineage(plan, payloads)
    started = json.loads(payloads["prior_execution_started"])
    outcome = json.loads(payloads["prior_outcome"])
    parent = json.loads(payloads["prior_plan"])
    battle_settled_state = _verified_battle_settlement_state(plan, payloads)
    binding_ref = started["selected_binding_ref"]
    state = plan["state"]
    assert isinstance(state, dict)
    common = (
        started["selected_kind"] == "evolve_species"
        and started["state_sha256"] == outcome["before_state_sha256"]
        and (outcome["safe_terminal"] is True or battle_settled_state is not None)
        and (battle_settled_state or outcome["terminal_state_sha256"]) == state["sha256"]
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
            and binding_ref.rsplit(":", 1)[-1] == parent["prior_binding_ref"].rsplit(":", 1)[-1]
        )
    if not common or not authorized:
        raise ValueError("continuation does not match the consumed model goal")
    return binding_ref


def _validate_paid_exit_budget(plan, payloads):
    if "assisted_training_money" in plan:
        raise ValueError("paid exit cannot receive training assistance")
    if any(key in payloads for key in PAID_RECORDS):
        if not all(key in payloads for key in PAID_RECORDS):
            raise ValueError("paid exit requires the authenticated retained search")
        paid = json.loads(payloads["paid_safari_plan"])
        spent = json.loads(payloads["paid_safari_result"])["after"]
        remaining = {
            "actions": paid["remaining_original_actions"] - spent["macros"],
            "frames": paid["remaining_original_frames"] - spent["frames"],
        }
    else:
        parent = json.loads(payloads["prior_plan"])
        outcome = json.loads(payloads["prior_outcome"])
        result = json.loads(payloads["prior_result"])
        if (parent["schema"] != "pokemon.red.autonomous-option-run.v1"
                or parent["provenance"].get("training_assistance")
                or result.get("outcomes", [None])[-1] != outcome
                or outcome["selected_kind"] != "acquire_species"
                or outcome["choice"]["model_sha256"] != plan["model_sha256"]
                or outcome["choice"]["mode"] != "model_exploration"
                or outcome["choice"]["teacher_labels"] != 0
                or outcome["safe_terminal"] is not True
                or outcome["after"]["session"]["in_safari_zone"] is not True):
            raise ValueError("paid exit requires an earned model-selected Safari endpoint")
        remaining = {key: parent["provenance"]["maximum_" + key] - outcome["after"][key]
                     for key in ("actions", "frames")}
    for cap, cost, ceiling in (
        ("maximum_actions", "actions", 2000),
        ("maximum_frames", "frames", 240000),
    ):
        value = plan.get(cap)
        if (type(value) is not int or not 0 < value <= ceiling
                or value > remaining[cost]):
            raise ValueError("paid exit exceeds remaining original budget")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--inspect", action="store_true")
    args = parser.parse_args()
    plan_bytes = args.plan.read_bytes()
    plan = json.loads(plan_bytes)
    maximum_evolution_quanta = validate_native_evolution_quanta(
        plan.get("maximum_evolution_quanta", 128)
    )
    complete_paid_session = plan.get("safari_complete_paid_session", False)
    if type(complete_paid_session) is not bool:
        raise ValueError("Safari lifecycle scope must be an explicit boolean")
    scripted_gifts = plan.get("scripted_gifts", False)
    if type(scripted_gifts) is not bool:
        raise ValueError("scripted gift scope must be an explicit boolean")
    npc_trades = plan.get("npc_trades", False)
    if type(npc_trades) is not bool:
        raise ValueError("NPC trade scope must be an explicit boolean")
    integrated_play = plan.get("integrated_play", False)
    maximum_cash_spent = plan.get("maximum_cash_spent", 0)
    if type(integrated_play) is not bool or type(maximum_cash_spent) is not int or (
        maximum_cash_spent < 0 or (not integrated_play and maximum_cash_spent != 0)
    ):
        raise ValueError("integrated play requires explicit scope and cash bound")
    if integrated_play and (
        not complete_paid_session or plan.get("include_league_funding", True)
        or plan.get("mode") is not None or "assisted_training_money" in plan
    ):
        raise ValueError("integrated play requires ordinary closed paid sessions without League")
    if plan.get("mode") == "collection_continuation":
        raise ValueError(
            "automatic collection continuation is not qualified; use the existing player"
        )
    include_league_funding = plan.get("include_league_funding", True)
    if type(include_league_funding) is not bool:
        raise ValueError("League funding scope must be an explicit boolean")
    trainer_model = None
    trainer_qualification_sha256 = None
    if "trainer_battler" in plan:
        binding = plan["trainer_battler"]
        qualification = None
        if "qualification" in binding:
            qualification = Path(binding["qualification"]["path"]).read_bytes()
            trainer_qualification_sha256 = hashlib.sha256(qualification).hexdigest()
            if trainer_qualification_sha256 != binding["qualification"]["sha256"]:
                raise ValueError("trainer qualification authentication failed")
        trainer_model = load_frozen_trainer_model(
            Path(binding["path"]).read_bytes(),
            binding["sha256"],
            qualification=qualification,
        )
        if not isinstance(binding.get("root_lineage_id"), str):
            raise ValueError("learned trainer needs the actual development root lineage")
    assisted_money = plan.get("assisted_training_money")
    if assisted_money is not None and plan.get("mode") == "continue_selected_goal":
        raise ValueError("assisted money cannot rewrite a previously selected goal")
    if plan.get("mode") == "assisted_safari_probe" and assisted_money is None:
        raise ValueError("Safari training probe requires assisted money")
    payloads = {}
    for key in (
        "rom",
        "state",
        "checkpoint",
        "profile",
        "model",
        "reserve_origin",
        "prior_plan",
        "prior_outcome",
        "prior_execution_started",
        "prior_result",
        "settlement_plan",
        "settlement_outcome",
        "safari_lineage",
        *PAID_RECORDS,
    ):
        if (
            key
            in {
                "reserve_origin",
                "prior_plan",
                "prior_outcome",
                "prior_execution_started",
                "prior_result",
                "settlement_plan",
                "settlement_outcome",
                "safari_lineage",
                *PAID_RECORDS,
            }
            and key not in plan
        ):
            continue
        content = Path(plan[key]["path"]).read_bytes()
        if hashlib.sha256(content).hexdigest() != plan[key]["sha256"]:
            raise ValueError(f"autonomous {key} authentication failed")
        payloads[key] = content
    _verify_reserve_lineage(plan, payloads)
    paid_exit = plan.get("mode") == "exit_paid_safari"
    if paid_exit:
        _validate_paid_exit_budget(plan, payloads)
    continuation_ref = (
        _verify_goal_continuation(plan, payloads)
        if plan.get("mode") == "continue_selected_goal"
        else None
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
            plan["reserve_origin"]["sha256"]
            if "reserve_origin" in plan
            else plan["state"]["sha256"]
        ),
        "goal_authority": "model_or_declared_equivalent_exploration",
        "include_league_funding": include_league_funding,
        "capture_destination_authority": "model_over_up_to_eight_observed_routes",
        "evolution_target_authority": "model_for_contrasts_uniform_for_equivalent_targets",
        "battle_move_authority": "existing_heuristic_controller",
        "ordinary_trainer_battle_authority": (
            "frozen-qualified" if trainer_model is not None else "existing_heuristic_controller"
        ),
        "trainer_battle_model_sha256": (
            plan["trainer_battler"]["sha256"] if trainer_model is not None else None
        ),
        "trainer_battle_qualification_sha256": trainer_qualification_sha256,
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
            prior_money, injected_money = _apply_assisted_training_money(emulator, assisted_money)
            assisted_state = emulator.save_state_bytes()
            assisted_sha256 = hashlib.sha256(assisted_state).hexdigest()
            assisted_envelope = dict(envelope, state_sha256=assisted_sha256)
            capture = parse_goal_manager_context_capture(
                assisted_state,
                (
                    json.dumps(assisted_envelope, sort_keys=True, separators=(",", ":")) + "\n"
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
        runtime.trainer_funding_ledges = plan.get("trainer_funding_ledges") is True
        # Soft admission only: never widen/reset the hard controller limits.
        # Checked between encounters; the remaining allowance settles an active
        # battle. An unexpectedly long battle may still exhaust the hard cap.
        runtime.evolution_stop_requested = lambda: (
            limiter.remaining_actions <= 1_000 or budget.remaining_frames <= 120_000
        )
        runtime.safari_indoor_departure = plan.get("safari_indoor_departure") is True
        runtime.safari_departure_surf = plan.get("safari_departure_surf") is True
        runtime.safari_complete_paid_session = complete_paid_session
        runtime.scripted_gifts = scripted_gifts
        runtime.npc_trades = npc_trades
        runtime.trainer_funding_roster_preparation = (
            plan.get("trainer_funding_roster_preparation") is True
        )
        runtime.trainer_funding_indoor_departure = (
            plan.get("trainer_funding_indoor_departure") is True
        )
        funding_event_count = 0

        def record_funding_event(event):
            nonlocal funding_event_count
            if args.inspect:
                raise AssertionError("inspection must not execute a funding route")
            funding_event_count += 1
            _record(
                output / f"funding-route-{funding_event_count:04d}.json",
                {
                    **event,
                    "state_sha256": hashlib.sha256(emulator.save_state_bytes()).hexdigest(),
                    "frames": emulator.frame_count - initial_frame,
                    "actions": actions.actions_executed,
                },
            )

        runtime.trainer_funding_event_sink = record_funding_event
        if trainer_model is not None:
            from pokemon_red_completion.red_battle_practice_cartridge import RedPracticeCartridge

            battler = FrozenTrainerBattler(
                session=controller,
                model=trainer_model,
                output=output / "trainer-battles",
                source_commit=provenance["source_commit"],
                root_lineage_id=plan["trainer_battler"]["root_lineage_id"],
                source_state_sha256=capture.state_sha256,
                public_species_base_stats=RedPracticeCartridge(payloads["rom"]).public_base_stats,
                model_sha256=plan["trainer_battler"]["sha256"],
                qualification_sha256=trainer_qualification_sha256,
            )
            runtime.trainer_battle_runner = battler.run
            runtime.trainer_battle_model_sha256 = plan["trainer_battler"]["sha256"]
            runtime.trainer_battle_qualification_sha256 = trainer_qualification_sha256
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
            original_reserves
            if original_reserves is not None
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
                        "buttons_released": not emulator.pressed_buttons,
                        "bag_items": current.raw.bag_items,
                        "party_hp": current.raw.party_hp,
                        "party_pp": current.raw.party_pp,
                        "party_status": current.raw.party_status,
                        "session": asdict(reader.read_safari_session_state()),
                    }
                )
            except Exception as error:
                safe = False
                facts.update({"observation_error": str(error), "error_type": type(error).__name__})
            return AutonomousSnapshot(state, facts, safe)

        if "safari_lineage" in payloads:
            if assisted_money is not None:
                raise ValueError("earned Safari terminal cannot receive training assistance")
            verify_safari_terminal_facts(json.loads(payloads["prior_outcome"]), snapshot().facts)
        if any(key in payloads for key in PAID_RECORDS):
            verify_paid_safari_live_facts(
                verify_paid_safari_lineage(plan, payloads), snapshot().facts,
            )

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
                include_league_funding=include_league_funding,
                maximum_evolution_quanta=maximum_evolution_quanta,
            )

        def observe_targeted():
            limiter.begin_decision_window()
            budget.begin_window()
            return autonomous_evolution_continuation_bindings(
                runtime,
                actions,
                world,
                maximum_actions=maximum_actions,
                maximum_frames=maximum_frames,
                maximum_quanta=maximum_evolution_quanta,
            )

        if paid_exit:
            before = snapshot()
            if not before.safe:
                raise ValueError("unsafe paid Safari exit origin")
            if "paid_safari_result" not in payloads:
                verify_safari_terminal_facts(json.loads(payloads["prior_outcome"]), before.facts)
            binding, route = bind_paid_safari_departure(controller, actions, reader, world)
            if snapshot() != before:
                raise ValueError("paid exit binding changed the game")
            if args.inspect:
                print(json.dumps({"status": "verified_action_free", "model_queries": 0,
                                  "route": route, "facts": before.facts}, indent=2))
            else:
                provenance["paid_search_result_sha256"] = plan.get(
                    "paid_safari_result", plan["prior_result"]
                )["sha256"]
                print(json.dumps(run_paid_safari_departure(
                    output=output, snapshot=snapshot, binding=binding, route=route,
                    provenance=provenance,
                ), indent=2))
            return

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
                print(
                    json.dumps(
                        {
                            "status": "verified_action_free",
                            "binding_scope": "targeted_evolution",
                            "facts": before.facts,
                            "private_binding_refs": [binding.binding_ref for binding in bindings],
                            "matching_ref": selected.binding_ref,
                            "model_queries": 0,
                        },
                        indent=2,
                        sort_keys=True,
                    )
                )
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
        if plan.get("mode") == "assisted_safari_probe":
            result = run_assisted_safari_probe(
                output=output,
                snapshot=snapshot,
                observe=observe,
                provenance=provenance,
            )
        elif continuation_ref is not None:
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
                integrated_play=integrated_play,
                maximum_cash_spent=maximum_cash_spent,
            )
        print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
