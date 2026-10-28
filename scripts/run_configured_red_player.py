#!/usr/bin/env python3
"""Inspect/resume the existing native player from one durable private plan.

The plan supplies authenticated paths, model/configuration identities and one
aggregate allowance. No date, chapter dispatcher or personal path lives here.
Legacy private assembly dependencies remain explicit rather than migrated.
"""

import argparse
import importlib
import json
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from pokemon_red_completion.emulation_batch import verify_pins
from pokemon_red_completion.executor import CountingExecutor, FrameSafeExecutor, ReadOnlyController
from pokemon_red_completion.goal_manager import GoalFailureReason, GoalKind
from pokemon_red_completion.goal_manager_runtime import GoalBindingSet
from pokemon_red_completion.goal_search_memory import GoalSearchMemory
from pokemon_red_completion.living_dex_option_value import upgrade_option_value_model_for_matchup
from pokemon_red_completion.player_challenge_consequence import ChallengeConsequenceHead
from pokemon_red_completion.private_artifacts import (
    gitless_fast_path_worktree_probe,
    initialize_private_root,
    open_private_root,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_autonomous_player import _exception_chain, _record, _write
from pokemon_red_completion.red_consequence_choice import (
    branch_recovery_objectives,
    branch_recovery_scope_ref,
    select_branch_recovery_live_option,
)
from pokemon_red_completion.red_goal_skills import _raw_party_fully_restored
from pokemon_red_completion.red_integrated_play import menu_with_search_history, objective_key
from pokemon_red_completion.red_live_option_menu import RedLiveOptionSet, select_red_live_option
from pokemon_red_completion.red_native_player import (
    NativeExecutionIdentity,
    NativePlayerLimits,
    NativePlayerSession,
    run_native_continuous_player,
)
from pokemon_red_completion.red_player_configuration import (
    RedPlayerConfiguration,
    assemble_configured_player,
    checkpoint_quiescent,
    player_lifecycle_fields,
    declared_native_evolution_venue_model,
)
from pokemon_red_completion.red_player_continuation import (
    SCHEMA as PLAYER_CONTINUATION_SCHEMA,
    _costs as continuation_costs,
    accumulate_player_costs,
    capture_player_continuation,
)
from pokemon_red_completion.red_player_curriculum import (
    NativePlayerCurriculum,
    NativeResourceCurriculum,
)
from pokemon_red_completion.red_player_field_goals import _field_ready
from pokemon_red_completion.red_player_lesson_runtime import observe_native_player_options
from pokemon_red_completion.red_player_model import load_player_goal_model_record_bytes
from pokemon_red_completion.red_player_owned_machines import owned_machine_options
from pokemon_red_completion.red_player_party_guard import RedPlayerPartyGuard
from pokemon_red_completion.red_spectator_feed import RunFrameFeed, declared_spectator


def requires_compulsory_settlement(runtime):
    """Start cancellation is ordinary control support, not a battle preface.

    Keep a scoped head attached for the normal loop; no strategic query is
    allowed until that loop has recovered field control.
    """
    return (
        not _field_ready(runtime)
        and not getattr(
            runtime.reader,
            "read_overworld_start_menu_visible",
            lambda: False,
        )()
    )


def declared_owned_machine_options(plan):
    spec = plan.get("owned_machine_options")
    if spec is None:
        return False
    if (
        plan.get("partition") != "development"
        or not isinstance(spec, dict)
        or set(spec) != {"mode", "reason"}
        or type(spec["mode"]) is not str
        or spec["mode"] not in {"direct_attack_capacity_v1", "boxed_frontier_attack_capacity_v2",
                                "boxed_frontier_evolution_bundles_v3"}
        or not isinstance(spec["reason"], str)
        or not spec["reason"].strip()
    ):
        raise ValueError("owned machine options require an ordinary DEVELOPMENT declaration")
    return True


def declared_goal_model_observation_compatibility(plan):
    """Validate an explicit codec extension; never replace a stored model silently."""
    spec = plan.get("goal_model_observation_compatibility")
    if spec is None:
        return None
    if (
        plan.get("partition") != "development"
        or plan.get("goal_model_record") is None
        or not isinstance(spec, dict)
        or set(spec) != {"schema", "mode", "source_model_sha256", "target_model_sha256", "reason"}
        or spec["schema"] != "pokemon.red.goal-model-observation-compatibility.v1"
        or spec["mode"] != "v9_to_v15_zero_extension_v1"
        or not isinstance(spec["reason"], str)
        or not spec["reason"].strip()
        or any(type(spec[key]) is not str or len(spec[key]) != 64
               or any(c not in "0123456789abcdef" for c in spec[key])
               for key in ("source_model_sha256", "target_model_sha256"))
    ):
        raise ValueError("goal observation compatibility requires an explicit pinned DEVELOPMENT V9-to-V15 declaration")
    return dict(spec)


def declared_goal_model(plan, configuration, backend):
    """Load the pinned stored child, or retain the original default exactly.

    This is a prospective DEVELOPMENT artifact choice. It cannot silently swap
    a model in a continuation or bypass the existing model/corpus record reader.
    """
    compatibility = declared_goal_model_observation_compatibility(plan)
    spec = plan.get("goal_model_record")
    if spec is None:
        model, _ = backend.d.prior.models()
    else:
        if (
            plan.get("partition") != "development"
            or not isinstance(spec, dict)
            or set(spec) != {"path", "content_sha256", "reason"}
            or not isinstance(spec["path"], str)
            or not spec["path"].strip()
            or not isinstance(spec["reason"], str)
            or not spec["reason"].strip()
            or not isinstance(spec["content_sha256"], str)
            or len(spec["content_sha256"]) != 64
            or any(c not in "0123456789abcdef" for c in spec["content_sha256"])
        ):
            raise ValueError("stored goal model requires a pinned DEVELOPMENT declaration")
        payload = Path(spec["path"]).read_bytes()
        if sha256(payload).hexdigest() != spec["content_sha256"]:
            raise ValueError("stored goal model content differs")
        record = load_player_goal_model_record_bytes(
            payload, expected_model_sha256=configuration.goal_model_sha256
        )
        model = record.model
    if model.model_sha256 != configuration.goal_model_sha256:
        raise ValueError("configured goal model differs")
    if compatibility is not None:
        if (model.feature_version != 9
                or model.model_sha256 != compatibility["source_model_sha256"]):
            raise ValueError("goal observation compatibility source differs from authenticated V9 record")
        model = upgrade_option_value_model_for_matchup(model)
        if (model.feature_version != 15
                or model.model_sha256 != compatibility["target_model_sha256"]):
            raise ValueError("goal observation compatibility target differs from zero extension")
    return model


def connect_owned_machine_options(menu, *, rom, include_boxed_frontier=False, boxed_world=None,
                                  include_prepared_evolution=False, admits=None):
    """Extend the existing ports; preserve ordinary choices and exclusions."""
    if type(include_boxed_frontier) is not bool or (
        include_boxed_frontier and not callable(boxed_world)
    ):
        raise ValueError("boxed-machine options require their declared route binding")
    if (type(include_prepared_evolution) is not bool or include_prepared_evolution and (
            not include_boxed_frontier or not callable(admits)
            or not callable(getattr(menu, "enumerate_collection", None)))):
        raise ValueError("prepared evolution requires the existing admitted collection observer")
    previous = menu.enumerate_owned_machines

    def world_now():
        world = boxed_world()
        if world is None:
            raise ValueError("boxed-machine route binding is unavailable")
        return world

    def observe(runtime, actions, observation):
        rows = () if previous is None else previous(runtime, actions, observation)
        if runtime.reader.read().badge_bits != 255:
            return rows
        rows += owned_machine_options(runtime, actions, rom=rom)
        if include_boxed_frontier:
            from pokemon_red_completion.red_boxed_machine_options import boxed_frontier_machine_options

            rows += boxed_frontier_machine_options(runtime, actions, observation,
                rom=rom, world=world_now())
        return rows

    menu.enumerate_owned_machines = observe
    if include_prepared_evolution:
        collection = menu.enumerate_collection

        def observe_collection(runtime, actions, observation):
            rows = collection(runtime, actions, observation)
            if runtime.reader.read().badge_bits != 255:
                return rows
            from pokemon_red_completion.red_boxed_machine_options import quoted_boxed_frontier_machine_options
            from pokemon_red_completion.red_prepared_evolution_options import prepared_evolution_options

            choices = quoted_boxed_frontier_machine_options(runtime, actions, observation,
                rom=rom, world=world_now())
            return rows + prepared_evolution_options(runtime, actions, observation,
                machine_choices=choices, evolution_options=rows,
                enumerate_collection=collection, admits=admits)

        menu.enumerate_collection = observe_collection


def connect_declared_machine_options(menu, plan, *, rom, holder, configuration):
    if not declared_owned_machine_options(plan):
        return
    mode = plan["owned_machine_options"]["mode"]
    connect_owned_machine_options(menu, rom=rom,
        include_boxed_frontier=mode in {
            "boxed_frontier_attack_capacity_v2", "boxed_frontier_evolution_bundles_v3"},
        boxed_world=lambda: holder["configured_route"].route_world,
        include_prepared_evolution=mode == "boxed_frontier_evolution_bundles_v3",
        admits=configuration.admits if mode == "boxed_frontier_evolution_bundles_v3" else None)


def doc(path):
    return json.loads(Path(path).read_bytes())


def declared_backend_sources(plan):
    """Pin the existing private assembly before import, without migrating it.

    Old plans remain unchanged. New declarations bind a conservative import
    closure. Loaded-module checks use paths so legacy aliases of the same source
    do not create false missing dependencies.
    """
    sources = plan.get("backend_sources")
    if sources is None:
        return {}
    if plan.get("partition") != "development" or type(sources) is not dict or not sources:
        raise ValueError("backend sources require a nonempty DEVELOPMENT declaration")
    root = Path(plan["helpers_root"]).resolve()
    for name, digest in sources.items():
        if type(name) is not str or type(digest) is not str:
            raise ValueError("backend source path and digest must be strings")
        path = Path(name)
        if (
            not path.is_absolute()
            or str(path.resolve()) != name
            or path.suffix != ".py"
            or not path.is_relative_to(root)
            or len(digest) != 64
            or any(c not in "0123456789abcdef" for c in digest)
        ):
            raise ValueError("backend source must be a canonical private Python file and SHA256")
    backend = root.joinpath(*plan["backend_module"].split(".")).with_suffix(".py").resolve()
    if str(backend) not in sources:
        raise ValueError("backend source declaration omits the assembly entrypoint")
    verify_pins(sources)
    return dict(sources)


def verify_loaded_backend_sources(sources, helpers_root):
    if not sources:
        return
    root = Path(helpers_root).resolve()
    for module in tuple(sys.modules.values()):
        name = getattr(module, "__file__", None)
        if name is None:
            continue
        path = Path(name).resolve()
        if path.is_relative_to(root) and str(path) not in sources:
            raise ValueError(f"loaded private backend source was not declared: {path.name}")
    verify_pins(sources)


class InspectionExecutor(CountingExecutor):
    """Retain the existing action-free diagnostics, not a second gameplay logger."""

    def __init__(self, delegate):
        super().__init__(delegate)
        self.diagnostics = []

    def record_diagnostic_event(self, kind, payload):
        self.diagnostics.append(dict(kind=kind, payload=dict(payload)))
        super().record_diagnostic_event(kind, payload)

    def execute_restoration(self, binding):
        """Expose the live quote-time port, but never execute inspection inputs."""
        raise RuntimeError("zero-input inspection cannot execute restoration")


def authenticate_parent(parent, digest):
    context, result = doc(parent / "CONTEXT.json"), doc(parent / "RESULT.json")
    if (
        not checkpoint_quiescent(result)
        or digest(parent / "terminal.state") != context["state_sha256"]
        or context["state_sha256"] != result["state_sha256"]
        or digest(parent / "CONTEXT.json") != result["context_sha256"]
        or context["spent"] != result["spent"]
    ):
        raise ValueError("configured resume requires an authenticated stopped checkpoint")
    return context


def configured_run_nodes(root):
    """Keep failed pre-emulator identities, without treating them as saves."""
    candidates = sorted((root / "runs").glob("segment-*"))
    completed = []
    for node in candidates:
        error = node / "PRELAUNCH-ERROR.json"
        if error.exists():
            row = doc(error)
            if (
                row.get("phase") != "before_emulator"
                or (not checkpoint_quiescent(row) if "checkpoint_lifecycle" in row
                    else row.get("worker_stopped") is not True)
                or row.get("state_loads") != 0
                or row.get("inputs") != 0
                or row.get("frames") != 0
                or row.get("passed") is not False
                or {p.name for p in node.iterdir()} != {"PLAN.json", "PRELAUNCH-ERROR.json"}
            ):
                raise ValueError("prelaunch failure cannot hide an executed or unretained segment")
        else:
            completed.append(node)
    next_ordinal = max((int(p.name.split("-")[-1]) for p in candidates), default=0) + 1
    return completed, next_ordinal


def remaining_allowance(current, baseline, allowance, *, inspection=False):
    remaining = {key: allowance[key] - (current[key] - baseline[key]) for key in allowance}
    if any(current[key] < baseline[key] for key in allowance) or (
        not inspection and min(remaining.values()) <= 0
    ):
        raise ValueError("configured continuation lost costs or exhausted its allowance")
    return remaining


def native_cash_deltas(meter, outcomes):
    """Prefer observed input debits; net goal income must not erase purchases/losses."""
    if "observed_cash_debits" in meter:
        debit = meter["observed_cash_debits"]
        if type(debit) is not int or debit < 0:
            raise ValueError("native observed cash debit is invalid")
        return (debit,)
    return tuple(o["before"]["cash"] - o["after"]["cash"] for o in outcomes) + (
        meter.get("control_recovery_cash_debits", 0),
    )


def copied_native_cash_costs(actions):
    """Copy wrappers retain the same observed gross cash meter as normal play."""
    if not callable(actions.observe_cash):
        raise ValueError("copied native costs require live cash observation")
    result = {key: getattr(actions, key) for key in (
        "observed_cash_debits", "observed_cash_rewards", "observed_cash_changes")}
    if any(type(value) is not int or value < 0 for value in result.values()):
        raise ValueError("copied native cash counter is invalid")
    return result


def configured_execution_limits(args, left, wall_left):
    """Explicit finite chunks, always clipped to the retained aggregate guard.

    Defaults are unchanged. Long native evolutions can prospectively request
    a larger chunk without resetting an earlier loss, cost or checkpoint.
    """
    requested = dict(
        decisions=args.decisions,
        actions=getattr(args, "actions", 30000),
        frames=getattr(args, "frames", 2500000),
        seconds=args.seconds,
    )
    if any(type(v) is not int or v <= 0 for v in requested.values()):
        raise ValueError("configured chunks require positive integer limits")
    return NativePlayerLimits(
        **{
            k: min(v, int(left[k]), wall_left) if k == "seconds" else min(v, int(left[k]))
            for k, v in requested.items()
        },
        heals=int(left["heals"]),
        cash_debits=None,
    )


def diagnostic_spending(root):
    """Copy costs consume the block allowance but never enter the player's save."""
    totals = dict(decisions=0, actions=0, frames=0, seconds=0.0, heals=0)
    for node in sorted((root / "diagnostics").glob("*")):
        if not node.is_dir():
            continue
        path = node / "RESULT.json"
        if not path.is_file():
            raise ValueError("diagnostic copy has no retained result; reconcile before resuming")
        row = doc(path)
        if not checkpoint_quiescent(row) or row["copy_back"]:
            raise ValueError("diagnostic copy is not a stopped separate retained result")
        decisions = row.get("decisions", 1)
        if type(decisions) is not int or decisions < 0:
            raise ValueError("diagnostic copy has invalid retained decision costs")
        totals["decisions"] += decisions
        for key in ("actions", "frames", "seconds", "heals"):
            value = row.get(key, 0) if key == "heals" else row[key]
            if type(value) not in (int, float) or value < 0:
                raise ValueError("diagnostic copy has invalid retained costs")
            totals[key] += value
    return totals


def native_checkpoint_facts(runtime):
    """Read native rewards/readiness independently of the episode's success label."""
    raw = runtime.reader.read()
    return dict(
        badge_bits=raw.badge_bits,
        badges=int(raw.badge_bits or 0).bit_count(),
        event_flags_hex=raw.event_flags.hex(),
        bag_stock=raw.bag_items,
        registrations=len(runtime.reader.read_pokedex_state().owned_species),
        cash=raw.player_money,
        party_levels=raw.party_levels,
        whole_party_restored=_raw_party_fully_restored(raw),
    )


def declared_player_curriculum(plan, combat_ref):
    """Reuse native objective, registration and physical-stock completion proofs."""
    objectives = tuple(plan["objectives"])
    levels = ((combat_ref, 1),)
    if "required_species" not in plan and "required_stock" not in plan:
        return NativePlayerCurriculum(objectives, levels)
    species = plan.get("required_species", [])
    if "required_species" in plan and (type(species) is not list or not species):
        raise ValueError("save completion requires explicit local species targets")
    stock = plan.get("required_stock", [])
    if "required_stock" in plan and (
        type(stock) is not list
        or not stock
        or any(type(row) is not list or len(row) != 2 for row in stock)
    ):
        raise ValueError("resource completion requires explicit physical stock targets")
    return NativeResourceCurriculum(
        objectives,
        levels,
        required_species=tuple(species),
        required_stock=tuple(tuple(row) for row in stock),
    )


def declared_greedy_selection(plan):
    """Default to the old policy; declare existing exploration only in DEVELOPMENT."""
    spec = plan.get("goal_selection")
    if spec is None:
        return True
    if (
        not isinstance(spec, dict)
        or not {"mode", "reason"} <= set(spec) <= {"mode", "reason", "exploration_mix"}
        or type(spec["mode"]) is not str
        or spec["mode"] not in {"greedy", "exploration"}
        or type(spec["reason"]) is not str
        or not spec["reason"].strip()
        or plan.get("partition") != "development"
    ):
        raise ValueError("goal selection requires an explicit ordinary DEVELOPMENT declaration")
    if "exploration_mix" in spec:
        mix = spec["exploration_mix"]
        if (spec["mode"] != "exploration" or isinstance(mix, bool)
                or not isinstance(mix, (int, float)) or not 0 <= mix <= 1
                or plan.get("readiness_refinement") is not None):
            raise ValueError("custom exploration requires separate ordinary DEVELOPMENT selection")
    return spec["mode"] == "greedy"


def declared_exploration_mix(plan):
    """Forward the existing sampler knob; keep the historical default unchanged."""
    declared_greedy_selection(plan)
    return float((plan.get("goal_selection") or {}).get("exploration_mix", 0.25))


def declared_input_recording(plan):
    """Declare existing isolation and lossless recording representation, not less evidence."""
    spec = plan.get("input_recording")
    if spec is None:
        return {}
    if (
        not isinstance(spec, dict)
        or not {"git_worktree_probe", "reason"} <= set(spec)
        <= {"git_worktree_probe", "reason", "native_input_storage", "isolation_report"}
        or spec["git_worktree_probe"] != "gitless_fast_path_v1"
        or type(spec["reason"]) is not str
        or not spec["reason"].strip()
        or plan.get("partition") != "development"
        or ("native_input_storage" in spec and spec["native_input_storage"] != "flat_sealed_v1")
        or ("isolation_report" in spec and spec["isolation_report"] != "gzip_json_v1")
    ):
        raise ValueError("input recording requires an explicit ordinary DEVELOPMENT declaration")
    result = dict(git_worktree_probe=gitless_fast_path_worktree_probe)
    if "native_input_storage" in spec:
        result["native_input_storage"] = spec["native_input_storage"]
    return result


def declared_readiness_refinement(plan):
    """Opt in to the existing trained child for declared combat branches.

    This changes neither the base model nor available actions. A private plan
    must explicitly pin the retained native-TRAIN head and its reuse reason.
    """
    spec = plan.get("readiness_refinement")
    if spec is None:
        return {}
    if not isinstance(spec, dict) or (
        ("objective_ref" in spec) == ("objective_refs" in spec)
    ):
        raise ValueError("readiness refinement requires one explicit branch scope")
    plural = "objective_refs" in spec
    scope_key = "objective_refs" if plural else "objective_ref"
    if plural and type(spec[scope_key]) is not list:
        raise ValueError("readiness branch set requires a declared JSON list")
    objective_ref = tuple(spec[scope_key]) if plural else spec[scope_key]
    scope = branch_recovery_objectives(objective_ref)
    if plural and (
        plan.get("partition") != "development" or not declared_greedy_selection(plan)
    ):
        raise ValueError("readiness branch set requires explicit greedy DEVELOPMENT scope")
    if (
        not {scope_key, "head_path", "head_sha256", "content_sha256", "reason"}
        <= set(spec)
        <= {scope_key, "head_path", "head_sha256", "content_sha256", "reason",
            "refine_preparation", "defer_unbound_preparation", "allow_singleton_parent_support"}
        or any(ref not in plan["objectives"] for ref in scope)
        or not isinstance(spec["reason"], str)
        or not spec["reason"].strip()
    ):
        raise ValueError("readiness refinement requires one declared objective and reuse reason")
    refine_preparation = spec.get("refine_preparation", False)
    if type(refine_preparation) is not bool or refine_preparation and (
        plan.get("partition") != "development" or not declared_greedy_selection(plan)
    ):
        raise ValueError("preparation refinement requires declared greedy DEVELOPMENT scope")
    defer_unbound_preparation = spec.get("defer_unbound_preparation", False)
    allow_singleton_parent_support = spec.get("allow_singleton_parent_support", False)
    if (type(defer_unbound_preparation) is not bool
        or type(allow_singleton_parent_support) is not bool
        or (defer_unbound_preparation or allow_singleton_parent_support) and (
            plan.get("partition") != "development" or not declared_greedy_selection(plan))
        or allow_singleton_parent_support and not defer_unbound_preparation):
        raise ValueError("parent-bound preparation requires explicit greedy DEVELOPMENT scope")
    payload = Path(spec["head_path"]).read_bytes()
    if sha256(payload).hexdigest() != spec["content_sha256"]:
        raise ValueError("readiness refinement head bytes differ")
    head = ChallengeConsequenceHead.from_document(
        json.loads(payload), expected_sha256=spec["head_sha256"]
    )
    if head.provenance != "native_train" or head.feedback_version != 2:
        raise ValueError("readiness refinement requires the existing native-TRAIN V2 head")
    return dict(
        consequence_head=head,
        consequence_objective_ref=objective_ref,
        consequence_challenge_ref=branch_recovery_scope_ref(objective_ref),
        allow_greedy_branch_recovery=declared_greedy_selection(plan),
        **({"refine_preparation": True} if refine_preparation else {}),
        **({"defer_unbound_preparation": True} if defer_unbound_preparation else {}),
        **({"allow_singleton_parent_support": True} if allow_singleton_parent_support else {}),
    )


def declared_preparation_component(plan):
    """Carry an explicitly pinned provisional wild battler into each segment."""
    spec = plan.get("preparation_battle_component")
    if spec is None:
        return None
    if (
        not isinstance(spec, dict)
        or set(spec) != {"path", "sha256", "reason"}
        or not isinstance(spec["path"], str)
        or not isinstance(spec["sha256"], str)
        or not isinstance(spec["reason"], str)
        or not spec["reason"].strip()
    ):
        raise ValueError("preparation battler requires an exact reuse declaration")
    if sha256(Path(spec["path"]).read_bytes()).hexdigest() != spec["sha256"]:
        raise ValueError("declared preparation battler changed")
    return dict(spec)


PLAYER_WIRING_FIELDS = (
    "goal_model_record",
    "readiness_refinement",
    "goal_selection",
    "preparation_battle_component",
    "input_recording",
    "owned_machine_options",
    "bird_capture_loan",
    "snorlax_capture_loan",
    "league_first_collection_scope",
    "owned_stock_income_bootstrap",
    "conserved_owned_medicine_income",
)
CHECKPOINT_ERRORS = {
    "ControllerWallTimeBudgetExhausted",
    "ControllerFrameBudgetExhausted",
    "ControllerFrameBudgetError",
    "ControllerActionBudgetExhausted",
    "BattleRuntimeError",
    "BattleRuntimeTimeoutError",
    "ProtectedRecoveryError",
    "KeyboardInterrupt",
}
CHUNK_BUDGET_ERRORS = CHECKPOINT_ERRORS - {
    "BattleRuntimeError",
    "BattleRuntimeTimeoutError",
    "ProtectedRecoveryError",
    "KeyboardInterrupt",
}


def declared_automatic_renewal(plan):
    spec = plan.get("automatic_runtime_renewal")
    if spec is None:
        return False
    if (
        plan.get("partition") != "development"
        or type(spec) is not dict
        or set(spec) != {"mode", "reason"}
        or spec["mode"] != "live_chunks_v1"
        or type(spec["reason"]) is not str
        or not spec["reason"].strip()
    ):
        raise ValueError("automatic renewal requires a declared DEVELOPMENT live loop")
    return True


def declared_league_first_collection_scope(plan):
    """An explicit DEVELOPMENT task scope must survive the actual launch boundary."""
    spec = plan.get("league_first_collection_scope")
    if spec is None:
        return None
    if (plan.get("partition") != "development" or type(spec) is not dict
            or set(spec) != {"mode","reason"}
            or spec["mode"] != "defer_eight_badge_collection_until_hof_v1"
            or type(spec["reason"]) is not str or not spec["reason"].strip()):
        raise ValueError(
            "League-first scope requires an explicit supported DEVELOPMENT declaration"
        )
    return dict(spec)


def player_wiring_declaration(plan):
    """Validate and retain the same optional actor wiring in both entry points."""
    from pokemon_red_completion.red_player_party_guard import (
        validate_bird_capture_loan_declaration,
        validate_snorlax_capture_loan_declaration,
    )

    declared_greedy_selection(plan)
    compatibility = declared_goal_model_observation_compatibility(plan)
    declared_readiness_refinement(plan)
    declared_preparation_component(plan)
    venue_model = declared_native_evolution_venue_model(plan)
    declared_input_recording(plan)
    declared_owned_machine_options(plan)
    validate_bird_capture_loan_declaration(plan.get("bird_capture_loan"))
    validate_snorlax_capture_loan_declaration(plan.get("snorlax_capture_loan"))
    declared_league_first_collection_scope(plan)
    bootstrap = plan.get("owned_stock_income_bootstrap", False)
    if type(bootstrap) is not bool or bootstrap and plan.get("partition") != "development":
        raise ValueError("owned-stock income bootstrap requires explicit DEVELOPMENT permission")
    conserved = plan.get("conserved_owned_medicine_income", False)
    if (type(conserved) is not bool
            or conserved and (plan.get("partition") != "development" or not bootstrap)):
        raise ValueError("conserved income requires explicit DEVELOPMENT owned-stock permission")
    wiring = {
        key: bootstrap if key == "owned_stock_income_bootstrap" else
        conserved if key == "conserved_owned_medicine_income" else plan.get(key)
        for key in PLAYER_WIRING_FIELDS
    }
    if venue_model is not None:
        wiring["native_evolution_venue_model"] = dict(plan["native_evolution_venue_model"])
    if compatibility is not None:
        wiring["goal_model_observation_compatibility"] = compatibility
    return wiring


def native_player_options(plan, runtime, roles, menu, *, refinement=None):
    """Keep strategy learned; settle only already-engaged compulsory control."""
    unsettled = requires_compulsory_settlement(runtime)
    refinement = declared_readiness_refinement(plan) if refinement is None else refinement
    return dict(
        greedy_selection=declared_greedy_selection(plan),
        exploration_mix=declared_exploration_mix(plan),
        force_resource_safety=False,
        include_live_pp_readiness=True,
        allow_collection_restoration=True,
        settle_existing_trainer=unsettled,
        settle_existing_wild=unsettled,
        settle_existing_blackout=unsettled,
        settle_existing_motion=unsettled,
        resume_branch_refinement_after_settlement=bool(refinement) and unsettled,
        curriculum=declared_player_curriculum(plan, roles[0]),
        **refinement,
        **menu.native_callbacks(),
    )


def execute_player_chunk(
    *,
    plan,
    configuration,
    c,
    emulator,
    factory,
    menu,
    holder,
    source,
    output,
    model,
    limits,
    memory,
    store,
    ordinal,
):
    """One shared native call and durable export, with no state restoration."""
    roles = tuple(m.specimen_ref for m in holder["plan"].roster if m.purpose.value == "combat")
    options = native_player_options(plan, holder["runtime"], roles, menu)
    _record(
        output / "EXECUTION.json",
        dict(
            configuration_sha256=configuration.sha256,
            limits=asdict(limits),
            goal_model_sha256=model.model_sha256,
            supplied_strategic_order=plan.get("league_first_collection_scope") is not None,
            automatic_fit=False,
            greedy_selection=options["greedy_selection"],
            **player_wiring_declaration(plan),
            refinement_suspended_for_compulsory_settlement=False,
            refinement_deferred_until_verified_settlement=options[
                "resume_branch_refinement_after_settlement"
            ],
        ),
    )
    frame_start = emulator.frame_count
    result = dict(
        passed=False,
        error=None,
        training=0,
        fits=0,
        new_origin=False,
        configuration_sha256=configuration.sha256,
    )
    try:
        result["episode"] = run_native_continuous_player(
            store=store,
            emulator=emulator,
            runtime_factory=factory,
            source=source,
            output=output / "native",
            model=model,
            seed=plan["seed"] + ordinal,
            run_id=output.parent.parent.name,
            arm_id=output.name,
            limits=limits,
            combat_specimen_refs=roles,
            battle_observer=holder["observe_history"],
            target_cash=0,
            initial_search_memory=memory,
            **options,
        )
        admission = result["episode"].get("admission_failure")
        if admission:
            result.update(
                passed=False, error_type=admission["error_type"], error=admission["error"],
                admission_failure=admission, error_chain=admission.get("error_chain"),
            )
        else:
            result["passed"] = True
    except BaseException as error:
        result.update(error_type=type(error).__name__, error=str(error),
                          error_chain=_exception_chain(error))
    finally:
        _write(output / "terminal.state", emulator.save_state_bytes())
        cost_path = output / "native/native-costs.json"
        meter = doc(cost_path) if cost_path.exists() else {}
        outcomes = result.get("episode", {}).get("outcomes", [])
        if not outcomes:
            outcomes = [
                doc(p) for p in sorted((output / "native/episode").glob("step-*/outcome.json"))
            ]
        spent = accumulate_player_costs(
            holder["prior_spent"],
            decisions=meter.get("goal_attempts", 0),
            actions=meter.get("actions_attempted", 0),
            frames=meter.get("frames", emulator.frame_count - frame_start),
            seconds=meter.get("seconds", 0),
            heals=meter.get("restore_attempts", 0),
            cash_deltas=native_cash_deltas(meter, outcomes),
        )
        error_type = result.get("error_type") or (
            outcomes[-1].get("error_type") if outcomes else None
        )
        error_message = (
            result.get("error") if result.get("error_type")
            else outcomes[-1].get("error") if outcomes else None
        )
        primary_error_chain = result.get("error_chain") or (
            outcomes[-1].get("error_chain") if outcomes else None
        )
        if primary_error_chain is not None:
            result["error_chain"] = primary_error_chain
        checkpoint_type = error_type if error_type in CHECKPOINT_ERRORS else None
        if error_type == "ControllerFrameBudgetError":
            checkpoint_type = (
                error_type if error_message == "controller exhausted its hard frame budget"
                else None
            )
        checkpoint_kwargs = (
            {"checkpoint_error": error_message}
            if checkpoint_type == "ControllerFrameBudgetError" else {}
        )
        exported = None
        try:
            history = holder["observe_history"](
                checkpoint_error_type=checkpoint_type, **checkpoint_kwargs,
            )
            censored = holder.get("censored_battle_checkpoint")
            exported = capture_player_continuation(
                holder["runtime"],
                preparation=holder["plan"],
                battle=None if censored is not None else history,
                spent=spent,
                search_memory=memory,
            )
            _record(output / "CONTEXT.json", exported)
        except Exception as export_error:
            # Export diagnostics must not replace a native failure or erase its
            # charged tail. An unpaired terminal remains evidence, never a
            # fabricated continuation or permission to renew the live player.
            exported = None
            export_failure = dict(
                error_type=type(export_error).__name__, error=str(export_error),
                error_chain=_exception_chain(export_error),
                primary_error_type=error_type, primary_error=error_message,
                primary_error_chain=primary_error_chain,
                resume_authorized=False,
            )
            _record(output / "CHECKPOINT-EXPORT-ERROR.json", export_failure)
            result.update(
                passed=False, checkpoint_export_error=export_failure,
                error_type=error_type or type(export_error).__name__,
                error=error_message if error_type else str(export_error),
                error_chain=primary_error_chain if error_type else _exception_chain(export_error),
            )
        censored = holder.get("censored_battle_checkpoint")
        raw = holder["runtime"].reader.read()
        result.update(
            **player_lifecycle_fields(scope="live_chunk", released=not emulator.pressed_buttons,
                guest_backend_closed=(emulator._backend is None) if hasattr(emulator,"_backend") else None),
            released=not emulator.pressed_buttons,
            state_sha256=c.digest(output / "terminal.state"),
            context_sha256=c.digest(output / "CONTEXT.json") if exported is not None else None,
            field_ready=_field_ready(holder["runtime"]),
            spent=spent,
            cash=raw.player_money,
            map_id=raw.map_id,
            at=(raw.player_y, raw.player_x),
            levels=raw.party_levels,
            completed=(exported["lesson"]["completed_objectives"] if exported is not None
                       else outcomes[-1].get("after", {}).get("completed_objectives", [])
                       if outcomes else []),
            native_facts=native_checkpoint_facts(holder["runtime"]),
            censored_battle_checkpoint=censored,
            chunk_costs=meter,
        )
    saved_export = doc(output / "CONTEXT.json") if exported is not None else None
    required_export = {"schema", "state_sha256", "lesson", "cash", "bag", "preparation",
                       "battle", "spent", "grants_new_budget", "fit_allowed"}
    result["paired_context_authenticated"] = bool(
        type(exported) is dict and type(saved_export) is dict
        and set(exported) - {"search_memory"} == required_export
        and set(saved_export) - {"search_memory"} == required_export
        and exported.get("schema") == PLAYER_CONTINUATION_SCHEMA
        and canonical_sha256(exported) == canonical_sha256(saved_export)
        and exported.get("state_sha256") == result["state_sha256"]
        and exported.get("spent") == spent
        and exported.get("grants_new_budget") is False
        and exported.get("fit_allowed") is False
        and result["context_sha256"]
        and not result.get("checkpoint_export_error")
    )
    result["native_status"] = native_result_status(result, limits=limits)
    return result, exported


def qualified_route_setback_receipt(row):
    """Recognize the native strict guard's retained failed-walk certificate."""
    proof = row.get("recoverable_route_setback")
    if not isinstance(proof, dict) or row.get("error_type") != "RouteExecutionError":
        return False
    chain, cost = row.get("error_chain"), row.get("observed_cost")
    before, after = row.get("before", {}), row.get("after", {})
    walk, route = proof.get("failed_walk"), proof.get("route_terminal")
    if (proof.get("reason") != "step_acknowledgement_exhausted"
            or not isinstance(chain, list) or len(chain) != 1
            or not isinstance(chain[0], dict)
            or chain[0].get("reason_code") != proof["reason"]
            or row.get("verification") is not None or row.get("safe_terminal") is not True
            or not isinstance(cost, dict) or proof.get("cost") != cost
            or not isinstance(walk, dict) or not isinstance(route, dict)):
        return False
    if (any(type(cost.get(k)) is not int for k in ("actions", "completed_actions", "frames", "cash_spent"))
            or cost["actions"] <= 0 or cost["frames"] <= 0
            or cost["completed_actions"] != cost["actions"] or cost["cash_spent"] != 0):
        return False
    keys = ("player_lesson", "owned_species", "specimen_counts", "completed_objectives", "bag_items", "coins", "cash")
    if (not isinstance(before, dict) or not isinstance(after, dict)
            or any(k not in before or k not in after or before[k] != after[k] for k in keys)):
        return False
    for facts in (before, after):
        if (facts.get("party_guard_verified") is not True or facts.get("input_ready") is not True
                or facts.get("buttons_released") is not True or facts.get("battle_state") != 0):
            return False
    return (after.get("route_boundary") == route
            and route == dict(map_id=walk.get("source_map"), at=walk.get("source_at"),
                              ready=True, interruption=None, mode="land")
            and walk.get("source_map") == walk.get("expected_map")
            and walk.get("action") in {"up", "down", "left", "right"})


def qualified_restoration_budget_censor(result, *, limits=None):
    """Recognize one paid, safely exported finite terminal; never goal success."""
    if type(limits) is not NativePlayerLimits:
        return False
    episode, meter = result.get("episode") or {}, result.get("chunk_costs") or {}
    rows = episode.get("outcomes") or ()
    if (episode.get("stop_reason") != "restoration_budget" or not rows
            or result.get("error_type") or result.get("error")
            or result.get("checkpoint_export_error")
            or episode.get("admission_failure") or result.get("admission_failure")
            or result.get("released") is not True or result.get("field_ready") is not True
            or result.get("paired_context_authenticated") is not True
            or not checkpoint_quiescent(result)
            or result.get("cost_lower_bound") is True
            or result.get("context_costs_complete") is False
            or result.get("unknown_cost_fields")):
        return False
    for key in ("state_sha256", "context_sha256"):
        value = result.get(key)
        if (type(value) is not str or len(value) != 64
                or any(c not in "0123456789abcdef" for c in value)):
            return False
    row = rows[-1]
    message = "native player restoration budget exhausted"
    chain = [dict(error_type="RestorationBudgetExhausted", error=message)]
    if (row.get("error_type") != "RestorationBudgetExhausted" or row.get("error") != message
            or row.get("error_chain") != chain
            or result.get("error_chain") not in (None, chain)
            or row.get("failure_phase") != "execution"
            or row.get("failure_reason") != "execution_budget_exhausted"
            or row.get("verification") != "failed"
            or row.get("ordinary_setback") is not False
            or row.get("safe_terminal") is not True
            or row.get("terminal_state_sha256") != result["state_sha256"]
            or any(r.get("error_type") or r.get("error") or r.get("error_chain")
                   for r in rows[:-1])
            or any(r.get("verification") == "failed" and r.get("ordinary_setback") is not True
                   for r in rows[:-1])):
        return False
    integer_costs = ("actions_attempted", "actions_completed", "frames", "goal_attempts",
        "restore_attempts", "nested_restore_attempts", "training_healing_attempts",
        "observed_cash_debits", "observed_cash_rewards", "observed_cash_changes",
        "control_recovery_cash_debits")
    if (meter.get("schema") != "pokemon.red.native-player-costs.v1"
            or meter.get("automatic_fit") is not False
            or any(type(meter.get(k)) is not int or meter[k] < 0 for k in integer_costs)
            or type(meter.get("seconds")) not in (int, float)
            or not 0 <= meter["seconds"] < float("inf")
            or meter.get("buttons_released") is not True
            or meter["restore_attempts"] != limits.heals
            or (limits.cash_debits is not None
                and meter["observed_cash_debits"] > limits.cash_debits)
            or meter["actions_completed"] != meter["actions_attempted"]
            or meter["actions_attempted"] > limits.actions or meter["frames"] > limits.frames
            or meter["seconds"] > limits.seconds or meter["goal_attempts"] > limits.decisions
            or meter["goal_attempts"] != episode.get("executed_decisions")
            or meter["goal_attempts"] != len(rows)):
        return False
    try:
        spent = continuation_costs(result.get("spent"))
    except (TypeError, ValueError):
        return False
    for key, charged in {"decisions": "goal_attempts", "actions": "actions_attempted",
                         "frames": "frames", "heals": "restore_attempts",
                         "cash_debits": "observed_cash_debits"}.items():
        if type(spent.get(key)) is not int or spent[key] < meter[charged]:
            return False
    if (type(spent.get("seconds")) not in (int, float)
            or not meter["seconds"] <= spent["seconds"] < float("inf")):
        return False
    before, after, cost = row.get("before"), row.get("after"), row.get("observed_cost")
    if not all(type(v) is dict for v in (before, after, cost)):
        return False
    snapshots = {"actions": "actions_attempted", "completed_actions": "actions_completed",
        "frames": "frames", "restoration_attempts": "restore_attempts",
        "nested_restoration_attempts": "nested_restore_attempts",
        "training_healing_attempts": "training_healing_attempts"}
    for key, metered in snapshots.items():
        if (type(before.get(key)) is not int or type(after.get(key)) is not int
                or not 0 <= before[key] <= after[key] or after[key] != meter[metered]):
            return False
    for key in ("actions", "completed_actions", "frames"):
        if type(cost.get(key)) is not int or cost[key] != after[key] - before[key]:
            return False
    if (type(before.get("cash")) is not int or type(after.get("cash")) is not int
            or type(cost.get("cash_spent")) is not int
            or cost["cash_spent"] != max(0, before["cash"] - after["cash"])
            or after.get("battle_state") != 0 or type(after.get("battle_state")) is not int
            or after.get("input_ready") is not True or after.get("buttons_released") is not True
            or after.get("party_guard_verified") is not True):
        return False
    return True


def native_result_status(result, *, limits=None):
    """Separate a returned/exported chunk from its native gameplay outcome.

    Additive reporting only: existing receipts, errors, budgets and continuation
    decisions retain their meaning. A reported curriculum end is not independent
    completion-contract verification.
    """
    episode = result.get("episode") or {}
    outcomes = episode.get("outcomes") or ()
    errors = sum(bool(row.get("error_type") or row.get("error")) for row in outcomes)
    recovered_routes = sum(qualified_route_setback_receipt(row) for row in outcomes)
    root_error = bool(result.get("error_type") or result.get("error")
                      or result.get("checkpoint_export_error"))
    admission = bool(episode.get("admission_failure") or result.get("admission_failure"))
    setbacks = sum(row.get("ordinary_setback") is True for row in outcomes)
    verification_failures = sum(row.get("verification") == "failed"
                                and row.get("ordinary_setback") is not True for row in outcomes)
    budget_censors = int(qualified_restoration_budget_censor(result, limits=limits))
    if admission:
        status = "admission_error"
    elif root_error or errors > recovered_routes + budget_censors:
        status = "execution_error"
    elif verification_failures > budget_censors:
        status = "verification_failure"
    elif budget_censors:
        status = "restoration_budget_censor"
    elif result.get("released") is not True:
        status = "controls_unreleased_or_unknown"
    elif result.get("field_ready") is not True:
        status = "control_recovery_required"
    elif recovered_routes:
        status = "recovered_route_setback"
    elif setbacks:
        status = "ordinary_setback"
    elif episode.get("stop_reason") == "curriculum_complete":
        status = "curriculum_completion_reported"
    elif result.get("passed") is True:
        status = "settled_chunk"
    else:
        status = "unverified"
    return dict(
        schema="pokemon.red.native-result-status.v1", scope="current_chunk",
        status=status, wrapper_returned=result.get("passed") is True,
        native_outcome_error_count=errors, wrapper_or_export_error=root_error,
        recovered_route_error_count=recovered_routes,
        unrecovered_native_error_count=errors - recovered_routes,
        qualified_budget_censor_count=budget_censors,
        finite_censor=bool(budget_censors),
        effective_unrecovered_native_error_count=errors - recovered_routes - budget_censors,
        effective_nonordinary_verification_failures=verification_failures - budget_censors,
        admission_error=admission, ordinary_setbacks=setbacks,
        nonordinary_verification_failures=verification_failures,
        field_ready=result.get("field_ready") is True,
        controls_released=result.get("released") is True,
        independent_completion_verification=False,
    )


def chunk_continuation_reason(result, *, source_sha256, limits=None):
    """Renew finite chunks, never retry unknown failures or a stationary loop."""
    if result.get("episode", {}).get("admission_failure"):
        return "native_admission_error"
    if result.get("checkpoint_export_error"):
        return "native_execution_error"
    episode, meter = result.get("episode", {}), result.get("chunk_costs", {})
    if episode.get("stop_reason") == "curriculum_complete":
        return "curriculum_complete"
    if (
        not result.get("released")
        or result.get("state_sha256") == source_sha256
        or meter.get("actions_attempted", 0) <= 0
        or meter.get("frames", 0) <= 0
    ):
        return "no_executable_progress"
    if qualified_restoration_budget_censor(result, limits=limits):
        # The caller must still debit the original cumulative allowance before
        # constructing a new segment. This classification grants no new heals.
        return "automatic_budget_recovery"
    errors = [(result.get("error_type"), result.get("error"))]
    for outcome in episode.get("outcomes", ()):
        if not qualified_route_setback_receipt(outcome):
            errors.append((outcome.get("error_type"), outcome.get("error")))
    errors = [(kind, message) for kind, message in errors if kind]
    if errors:
        return (
            "automatic_budget_recovery"
            if all(
                kind in CHUNK_BUDGET_ERRORS and (
                    kind != "ControllerFrameBudgetError"
                    or message == "controller exhausted its hard frame budget"
                )
                for kind, message in errors
            )
            else "native_execution_error"
        )
    if episode.get("stop_reason") in {
        "decision_budget",
        "wall_time_budget",
        "settlement_budget",
    }:
        return "automatic_chunk_renewal"
    if episode.get("stop_reason") == "unsafe_terminal":
        return "automatic_control_recovery"
    return episode.get("stop_reason") or "native_execution_error"


def qualified_native_control_handoff(result, *, runtime, inspect_bindings):
    """Recognize one retained native introduction, never waive an unknown error.

    The trusted live inventory must contain one exact retained recovery and no
    alternative. Interrupted trainer/static transport or declared evolution-loan
    settlement stays failed, with all error/costs retained. No new encounter or
    strategic goal is selected.
    """
    episode = result.get("episode", {})
    outcomes = episode.get("outcomes", ())
    if not outcomes:
        return None
    last = outcomes[-1]
    known_trainer_error = (
        last.get("error_type") == "RouteExecutionError"
        and last.get("error") in {
            "field dialogue lacks a newly poisoned member faint",
            "field dialogue is not an admitted native faint",
            "Gen I route cannot dismiss 'trainer_engagement'",
        }
    )
    known_loan_wild_error = (
        last.get("selected_kind") == GoalKind.EVOLVE_SPECIES.value
        and last.get("error_type") == "RedGoalContextError"
        and last.get("error") == "PC loan settlement requires settled field control"
    )
    known_static_settlement = (
        last.get("selected_kind") == GoalKind.ACQUIRE_SPECIES.value
        and last.get("error_type") == "RouteExecutionError"
        and last.get("error")
        == "selected static transport requires ordinary player settlement"
    )
    known_story_decision_budget = (
        last.get("selected_kind") == GoalKind.ADVANCE_STORY.value
        and last.get("error_type") == "StoryBattleDecisionBudgetReached"
        and last.get("error") == "story battle reached its bounded decision limit"
        and any(
            isinstance(item, dict)
            and item.get("error_type") == "StoryBattleDecisionBudgetReached"
            and item.get("reason_code") == "story_battle_decision_budget"
            for item in (last.get("error_chain") or ())
        )
    )
    if (
        result.get("error_type")
        or not result.get("released")
        or result.get("field_ready") is not False
        or episode.get("stop_reason") != "execution_failed"
        or last.get("selected_kind") not in {kind.value for kind in GoalKind}
        or last.get("failure_phase") != "execution"
        or (last.get("safe_terminal") is not True
            and not ((known_loan_wild_error or known_story_decision_budget)
                     and last.get("safe_terminal") is False))
        or not (known_trainer_error or known_loan_wild_error or known_static_settlement
                or known_story_decision_budget)
        or last.get("terminal_state_sha256") != result.get("state_sha256")
        or any(outcome.get("error_type") for outcome in outcomes[:-1])
        or runtime.emulator.pressed_buttons
        or _field_ready(runtime)
    ):
        return None
    before, frames = runtime.emulator.save_state_bytes(), runtime.emulator.frame_count
    if sha256(before).hexdigest() != result["state_sha256"]:
        return None
    if known_static_settlement:
        from pokemon_red_completion.red_player_party_guard import RedPlayerPartyGuard

        guard = getattr(runtime.adapter, "party_guard", None)
        raw = runtime.reader.read()
        if (not isinstance(guard, RedPlayerPartyGuard) or raw.battle_state != 0
                or not raw.party_hp or not any(raw.party_hp)
                or not runtime.reader.read_bottom_dialogue_box_visible()
                or runtime.reader.read_overworld_start_menu_visible()):
            return None
        guard.verify_active_roster_restored()
    if known_loan_wild_error:
        from pokemon_red_completion.red_player_party_guard import RedPlayerPartyGuard

        guard = getattr(runtime.adapter, "party_guard", None)
        if (not isinstance(guard, RedPlayerPartyGuard)
                or len(guard.loanable_refs) != 1
                or runtime.reader.read().battle_state != 1):
            return None
        guard.verify()
        if set(guard.refs) - set(guard.reader.preparation_specimen_refs()) != set(
            guard.loanable_refs
        ):
            return None
    bindings = inspect_bindings()
    if (runtime.emulator.save_state_bytes() != before
            or runtime.emulator.frame_count != frames):
        raise ValueError("native control handoff inspection changed state")
    expected_ref = (
        ("pokemon.red:interrupted-wild:" if known_loan_wild_error else
         "pokemon.red:retained-engagement:") + result["state_sha256"]
    )
    if (
        type(bindings) is not GoalBindingSet
        or len(bindings.bindings) != 1
        or bindings.bindings[0].kind is not GoalKind.RECOVER_CONTROL
        or bindings.bindings[0].binding_ref
        != expected_ref
    ):
        return None
    return dict(
        schema="pokemon.red.qualified-native-control-handoff.v1",
        state_sha256=result["state_sha256"],
        binding_ref=bindings.bindings[0].binding_ref,
        qualified=True, inputs=0, frames=0, model_queries=0,
        failed_transport_preserved=True, strategic_substitution=False,
        **({"retained_declared_loan": True, "wild_exit_before_pc_return": True}
           if known_loan_wild_error else {}),
        **({"original_terminal_safe": False, "compulsory_settlement_required": True}
           if known_loan_wild_error and last.get("safe_terminal") is False else {}),
        **({"retained_native_introduction": True, "retained_roster_restored": True}
           if known_static_settlement else {}),
        **({"censored_story_battle": True, "original_terminal_safe": False,
            "local_decision_limit_unchanged": True, "aggregate_budget_reset": False}
           if known_story_decision_budget else {}),
    )


AUTOMATIC_CONTINUATIONS = {
    "automatic_budget_recovery",
    "automatic_chunk_renewal",
    "automatic_control_recovery",
}


def qualified_menu_control_handoff(result, *, runtime, menu):
    """One action-free qualification shared by fresh and continuation entry.

    This delegates to the existing exact retained-source/unique-recovery guard;
    it neither supplies a strategic goal nor turns an unknown error into success.
    """
    def inspect_control_bindings():
        actions = InspectionExecutor(FrameSafeExecutor(ReadOnlyController(runtime.emulator)))
        return menu.enumerate_base(runtime, actions, runtime.adapter.observe())

    return qualified_native_control_handoff(
        result, runtime=runtime, inspect_bindings=inspect_control_bindings
    )


def verify_loan_copy(args, plan, root, backend, configuration):
    """Test a retained loan on a copy without returning its state to play."""
    from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING
    from pokemon_red_completion.executor import (
        MonotonicWallTimeBudgetController,
        NativeLessonController,
    )
    from pokemon_red_completion.red_native_boxed_evolution import settle_native_evolution
    from pokemon_red_completion.red_player_lesson_runtime import _RecordedActions
    from pokemon_red_completion.red_player_party_loan import _stock

    c = backend.c
    guard_parent, loan_parent = Path(args.guard_source), Path(args.loan_copy_source)
    original, retained = (
        authenticate_parent(guard_parent, c.digest),
        authenticate_parent(loan_parent, c.digest),
    )
    output = root / f"diagnostics/loan-{datetime.now(UTC).strftime('%H%M%S%f')}"
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    declaration = dict(
        diagnostic_id=output.name,
        partition="development",
        correlated_copy=True,
        copy_back=False,
        goal_model_queries=0,
        **player_wiring_declaration(plan),
        fit_allowed=False,
        support_only=True,
        source=str(loan_parent),
        source_sha256=retained["state_sha256"],
        guard_source=str(guard_parent),
        guard_state_sha256=original["state_sha256"],
        configuration_sha256=configuration.sha256,
        configuration=configuration.to_dict(),
        native_seconds_limit=300,
        actions_limit=10000,
        frames_limit=1000000,
        inherited_spent=retained["spent"],
    )
    _record(output / "PLAN.json", declaration)
    payload, factory, _, _, _ = assemble_configured_player(
        backend, configuration, guard_parent, output, plan_path=output / "PLAN.json"
    )
    with c.PyBoyAdapter(c.ROM) as em:
        em.load_state_bytes(payload)
        wall = MonotonicWallTimeBudgetController(em, maximum_wall_seconds=300)
        ctrl = NativeLessonController(wall, maximum_frames=1000000)
        runtime = factory(ctrl)
        # Explicit copy setup before input: retain the original identity baseline
        # while loading the actual failed-loan terminal, not an invented party.
        em.load_state_bytes((loan_parent / "terminal.state").read_bytes())
        guard = runtime.adapter.party_guard
        guard.verify()
        if em.frame_count != 0 or em.pressed_buttons:
            raise ValueError("loan-copy setup spent input before its port")
        store = c.open_private_root(
            c.BASE / "goal-manager-v1", repository_root=c.REPO, allow_same_device=True
        )
        rec = _RecordedActions(
            ctrl,
            store,
            canonical_sha256(declaration),
            10000,
            timing=DEFAULT_NEW_GAME_TIMING.controller_timing(),
        )
        actions, before = CountingExecutor(rec), _stock(runtime)
        result = dict(passed=False, error=None)
        try:
            rec.enabled = True
            evidence = settle_native_evolution(runtime, actions)
            result.update(passed=True, evidence=evidence, stock_preserved=before == _stock(runtime))
        except BaseException as error:
            result.update(error_type=type(error).__name__, error=str(error),
                          error_chain=_exception_chain(error))
        finally:
            rec.enabled = False
            ctrl.input_enabled = False
            _write(output / "terminal.state", ctrl.save_state_bytes())
            result.update(
                actions=len(rec.trace),
                frames=ctrl.frames_executed,
                seconds=wall.elapsed_seconds,
                released=not ctrl.pressed_buttons,
                **player_lifecycle_fields(scope="diagnostic_chunk", released=not ctrl.pressed_buttons,
                    guest_backend_closed=(em._backend is None) if hasattr(em,"_backend") else None),
                model_queries=0,
                fits=0,
                copy_back=False,
                original_roles_restored=set(guard.refs)
                <= set(guard.reader.preparation_specimen_refs()),
                state_sha256=c.digest(output / "terminal.state"),
                source_sha256=retained["state_sha256"],
                configuration_sha256=configuration.sha256,
            )
            _record(output / "RESULT.json", result)
    result.update(player_lifecycle_fields(scope="driver_terminal", released=result["released"],
        guest_backend_closed=(em._backend is None) if hasattr(em,"_backend") else None))
    _record(output / "FINAL-RESULT.json", result)
    authenticate_parent(guard_parent, c.digest)
    authenticate_parent(loan_parent, c.digest)
    verify_pins(plan["protected"])
    print(json.dumps(dict(result, output=str(output)), default=str), flush=True)


def evolution_copy_choice(options, observation, configuration):
    """Prefer a real boxed precursor; never invent a loan for this diagnostic."""
    from pokemon_red_completion.collection import CollectionLocation
    from pokemon_red_completion.goal_manager import GoalKind

    boxed = {
        s.species_ref
        for s in observation.collection_observation.specimens
        if s.location is CollectionLocation.BOX
    }
    candidates = []
    for option in options:
        spec = next(s for s in option.profile.providers if s.kind is GoalKind.EVOLVE_SPECIES)
        if configuration.admits(option.binding):
            candidates.append((option, spec))
    if not candidates:
        raise ValueError("copy has no admitted level-evolution alternative")
    return max(
        candidates,
        key=lambda row: (
            row[1].parameters["source_species_ref"] in boxed,
            row[0].execution_effort or 0,
            row[0].binding.binding_ref,
        ),
    )


def declared_evolution_copy_experiment(plan):
    """Bounded copy-only measurement; never an actual player's venue override."""
    spec = plan.get("evolution_copy_experiment")
    if spec is None:
        return None
    if (
        plan.get("partition") != "development"
        or plan.get("diagnostic_only") is not True
        or plan.get("actual_gameplay_resume_authorized") is not False
        or plan.get("copy_back") is not False
        or plan.get("fit_allowed") is not False
        or type(spec) is not dict
        or set(spec) != {"venue", "maximum_quanta", "maximum_wall_seconds"}
        or type(spec["venue"]) is not str
        or spec["venue"] not in {"cave", "mansion"}
        or type(spec["maximum_quanta"]) is not int
        or not 1 <= spec["maximum_quanta"] <= 128
        or type(spec["maximum_wall_seconds"]) is not int
        or not 1 <= spec["maximum_wall_seconds"] <= 600
    ):
        raise ValueError("evolution experiment requires bounded non-copy-back DEVELOPMENT diagnostic")
    return dict(spec)


def evolution_recovery_accounting(session, evidence):
    """Reconcile all charged attempts; skill trips are a narrower counter."""
    charged = session.heals
    training = session.training_healing_trips
    restores = session.support_restorations
    overlaps = session.training_restoration_overlaps
    reported = evidence.get("healing_trips")
    valid = all(type(v) is int and v >= 0
                for v in (charged, training, restores, overlaps, reported))
    exact = valid and overlaps <= min(training, restores) and charged == training + restores - overlaps
    funded = valid and reported <= charged
    return dict(passed=bool(exact and funded), charged_recovery_attempts=charged,
        training_trip_attempts=training, restoration_attempts=restores,
        verified_overlap_credits=overlaps, reported_skill_healing_trips=reported,
        counters_have_different_scope=True)


def evolution_copy_limits(args, left, seconds, *, experiment):
    """Explicit measurements reuse the same finite aggregate clipping as play."""
    if experiment is not None:
        request = argparse.Namespace(decisions=1, seconds=seconds,
            actions=getattr(args, "actions", 20000),
            frames=getattr(args, "frames", 2000000))
        return configured_execution_limits(request, left, seconds)
    return NativePlayerLimits(decisions=1,
        actions=min(20000, int(left["actions"])),
        frames=min(2000000, int(left["frames"])),
        seconds=seconds, heals=int(left["heals"]), cash_debits=None)


def verify_evolution_copy(args, plan, root, backend, configuration, parent, context, left):
    """Exercise production reserve/nursing hooks on a real, non-copyback loan."""
    from pokemon_red_completion.goal_manager import GoalKind
    from pokemon_red_completion.red_level_evolution_options import enumerate_red_level_evolutions
    from pokemon_red_completion.red_player_party_loan import _stock

    c = backend.c
    experiment = declared_evolution_copy_experiment(plan)
    output = root / f"diagnostics/evolution-{datetime.now(UTC).strftime('%H%M%S%f')}"
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    seconds = min(
        args.seconds,
        int(left["seconds"]),
        int((datetime.fromisoformat(plan["cutoff_utc"]) - datetime.now(UTC)).total_seconds()),
    )
    limits = evolution_copy_limits(args, left, seconds, experiment=experiment)
    declaration = dict(
        partition="development",
        correlated_copy=True,
        copy_back=False,
        goal_model_queries=0,
        operator_diagnostic_choice=True,
        **player_wiring_declaration(plan),
        diagnostic_only=True,
        actual_gameplay_resume_authorized=False,
        evolution_copy_experiment=experiment,
        fit_allowed=False,
        source=str(parent),
        source_sha256=context["state_sha256"],
        configuration_sha256=configuration.sha256,
        configuration=configuration.to_dict(),
        limits=asdict(limits),
        inherited_spent=context["spent"],
        launcher_sha256=c.digest(Path(__file__)),
    )
    _record(output / "PLAN.json", declaration)
    _write(output / "executed-launcher.py", Path(__file__).read_bytes())
    payload, factory, _, holder, source = assemble_configured_player(
        backend, configuration, parent, output, plan_path=output / "PLAN.json"
    )
    result = dict(passed=False, error=None, copy_back=False, model_queries=0, fits=0)
    with c.PyBoyAdapter(c.ROM) as em:
        em.load_state_bytes(payload)
        journal = output / "journal"
        journal.mkdir(mode=0o700)
        store = initialize_private_root(
            journal, repository_root=c.REPO, allow_same_device=True,
            **declared_input_recording(plan),
        )
        factory(ReadOnlyController(em))
        roles = tuple(m.specimen_ref for m in holder["plan"].roster if m.purpose.value == "combat")
        session = NativePlayerSession(
            store=store,
            emulator=em,
            runtime_factory=factory,
            source=source,
            execution=NativeExecutionIdentity(
                root.name, output.name, configuration.goal_model_sha256, plan["seed"]
            ),
            output=output / "native",
            limits=limits,
            combat_specimen_refs=roles,
            battle_observer=holder["observe_history"],
            target_cash=0,
            model_feature_version=7,
            allow_collection_restoration=True,
            force_resource_safety=False,
            include_live_pp_readiness=True,
        )
        runtime, guard = session.runtime, session.runtime.adapter.party_guard
        before = _stock(runtime)
        try:
            world = backend.shared.RedVermilionGroundTransition.from_rom(c.ROM.read_bytes())
            from dataclasses import replace

            world = replace(world, full_event_offsets=True, observe_terrain=True).route_world
            options = {}
            if experiment is not None:
                provider = getattr(backend, "diagnostic_evolution_venue", None)
                if not callable(provider):
                    raise ValueError("declared native evolution venue adapter is unavailable")
                state = em.save_state_bytes()
                action_count, frames = session.actions.actions_executed, em.frame_count
                world, venues = provider(runtime, holder["configured_route"].route_world,
                                         experiment["venue"])
                if (em.save_state_bytes() != state or em.frame_count != frames
                        or session.actions.actions_executed != action_count):
                    raise ValueError("evolution venue discovery changed the game")
                options = dict(training_venues=venues, prefer_highest_supported_venue=True,
                    allow_guarded_venue_escapes=True,
                    maximum_quanta=experiment["maximum_quanta"],
                    maximum_wall_seconds=min(experiment["maximum_wall_seconds"],
                                             max(1, limits.seconds - 20)))
            observation = runtime.adapter.observe()
            alternatives = enumerate_red_level_evolutions(
                runtime,
                observation,
                session.actions,
                world,
                maximum_actions=limits.actions,
                maximum_frames=limits.frames,
                **options,
            )
            choice, spec = evolution_copy_choice(alternatives, observation, configuration)
            from pokemon_red_completion.collection import CollectionLocation

            loan_available = any(
                s.species_ref == spec.parameters["source_species_ref"]
                and s.location is CollectionLocation.BOX
                for s in observation.collection_observation.specimens
            )
            _record(
                output / "CHOICE.json",
                dict(
                    binding_ref=choice.binding.binding_ref,
                    parameters=dict(spec.parameters),
                    execution_effort=choice.execution_effort,
                    operator_choice=True,
                    model_queries=0,
                    boxed_precursor_available=loan_available,
                ),
            )
            session.active_kind, session.recorder.enabled = GoalKind.EVOLVE_SPECIES, True
            report = choice.binding.execute()
            session.recorder.enabled = False
            verdict = choice.binding.verify(report)
            after = _stock(runtime)
            preserved = {row[0] for row in before} == {row[0] for row in after}
            prior_xp = {row[0]: row[3] for row in before}
            xp_retained = all(row[3] >= prior_xp[row[0]] for row in after) if preserved else False
            guard.verify_active_roster_restored()
            result.update(
                evidence=dict(report.evidence),
                recovery_accounting=evolution_recovery_accounting(session, report.evidence),
                identities_preserved=preserved,
                earned_xp_retained=xp_retained,
                boxed_precursor_available=loan_available,
                verification=verdict.status.value,
                failure_reason=None
                if verdict.failure_reason is None
                else verdict.failure_reason.value,
                before_stock=list(before.elements()),
                after_stock=list(after.elements()),
                passed=report.evidence.get("settlement_reserve_reached") is True
                and preserved
                and xp_retained
                and session.training_healing_trips > 0
                and evolution_recovery_accounting(session, report.evidence)["passed"]
                and _field_ready(runtime),
            )
            if experiment is not None:
                from pokemon_red_completion.red_collection import red_internal_species_id
                source_number = int(spec.parameters["source_species_ref"].rsplit(":", 1)[1])
                source_id = red_internal_species_id(source_number)
                trainees = [row for row in before if row[1] == source_id]
                prior = trainees[0] if len(trainees) == 1 else None
                final = next((row for row in after if prior is not None
                              and row[0] == prior[0]), None)
                gain = None if prior is None or final is None else final[3] - prior[3]
                bounded_partial = (verdict.status.value == "failed"
                    and verdict.failure_reason is GoalFailureReason.OUTCOME_NOT_VERIFIED
                    and report.evidence.get("evolution_partial") is True
                    and any(report.evidence.get(k) is True for k in (
                        "settlement_reserve_reached", "wall_limit_reached", "quantum_limit_reached")))
                result.update(experiment=experiment, trainee_ref=None if prior is None else prior[0],
                    trainee_experience_before=None if prior is None else prior[3],
                    trainee_experience_after=None if final is None else final[3],
                    useful_trainee_xp_gain=gain, native_evolution_succeeded=verdict.status.value == "succeeded",
                    productive_bounded_partial=bounded_partial,
                    passed=preserved and xp_retained and type(gain) is int and gain > 0
                    and (bounded_partial or verdict.status.value == "succeeded")
                    and evolution_recovery_accounting(session, report.evidence)["passed"] and _field_ready(runtime))
        except BaseException as error:
            result.update(error_type=type(error).__name__, error=str(error),
                          error_chain=_exception_chain(error))
        finally:
            session.recorder.enabled = False
            session.controller.input_enabled = False
            _write(output / "terminal.state", em.save_state_bytes())
            result.update(
                actions=len(session.recorder.trace),
                frames=session.controller.frames_executed,
                seconds=session.wall.elapsed_seconds,
                heals=session.heals,
                inner_healing_attempts=session.training_healing_trips,
                nested_restoration_attempts=session.support_restorations,
                original_roles_restored=set(guard.refs)
                <= set(guard.reader.preparation_specimen_refs()),
                field_ready=_field_ready(runtime),
                released=not em.pressed_buttons,
                **player_lifecycle_fields(scope="diagnostic_chunk", released=not em.pressed_buttons,
                    guest_backend_closed=(em._backend is None) if hasattr(em,"_backend") else None),
                state_sha256=c.digest(output / "terminal.state"),
                configuration_sha256=configuration.sha256,
            )
            if result["field_ready"] and result["original_roles_restored"]:
                try:
                    result.update(copied_native_cash_costs(session.actions))
                    spent = accumulate_player_costs(
                        context["spent"],
                        decisions=1,
                        actions=result["actions"],
                        frames=result["frames"],
                        seconds=result["seconds"],
                        heals=result["heals"],
                        cash_deltas=native_cash_deltas(result, ()),
                    )
                    exported = capture_player_continuation(
                        runtime,
                        preparation=holder["plan"],
                        battle=None,
                        spent=spent,
                    )
                    _record(output / "CONTEXT.json", exported)
                    result.update(spent=spent, context_sha256=c.digest(output / "CONTEXT.json"))
                except BaseException as error:
                    result.update(passed=False, context_error=str(error),
                                  context_error_type=type(error).__name__,
                                  context_error_chain=_exception_chain(error))
            _record(output / "RESULT.json", result)
    result.update(player_lifecycle_fields(scope="driver_terminal", released=result["released"],
        guest_backend_closed=(em._backend is None) if hasattr(em,"_backend") else None))
    if result["passed"]:
        try:
            proof = verify_diagnostic_reload(c, factory, payload, output, after, result["spent"])
            result["reload_passed"] = proof["passed"]
            result["passed"] = bool(result["passed"] and proof["passed"])
        except BaseException as error:
            result.update(passed=False, reload_error=str(error),
                reload_error_type=type(error).__name__, reload_error_chain=_exception_chain(error))
    _record(output / "FINAL-RESULT.json", result)
    authenticate_parent(parent, c.digest)
    verify_pins(plan["protected"])
    print(json.dumps(dict(result, output=str(output)), default=str), flush=True)


def verify_diagnostic_reload(c, factory, payload, output, after_stock, spent):
    """Use the existing continuation restorer on an exact zero-input reload."""
    from pokemon_red_completion.red_player_continuation import restore_player_continuation
    from pokemon_red_completion.red_player_party_loan import _stock

    with c.PyBoyAdapter(c.ROM) as fresh:
        fresh.load_state_bytes(payload)
        reloaded = factory(ReadOnlyController(fresh))
        terminal = (output / "terminal.state").read_bytes()
        fresh.load_state_bytes(terminal)
        carried = restore_player_continuation(reloaded, doc(output / "CONTEXT.json"),
            expected_sha256=canonical_sha256(doc(output / "CONTEXT.json")),
            evolution_rom=c.ROM.read_bytes())
        proof = dict(passed=fresh.save_state_bytes() == terminal
            and fresh.frame_count == 0 and not fresh.pressed_buttons
            and _stock(reloaded) == after_stock and carried.spent == spent
            and _field_ready(reloaded), inputs=0, frames=fresh.frame_count, model_queries=0,
            state_sha256=c.digest(output / "terminal.state"),
            context_sha256=c.digest(output / "CONTEXT.json"),copy_back=False,
            inherited_spent=carried.spent)
        _record(output / "RELOAD.json", proof)
        return proof


def verify_boxed_machine_copy(args, plan, root, backend, configuration, parent, context, left,
                              *, prepared_evolution=False):
    """One explicit operator diagnostic; ordinary gameplay still uses the model."""
    from pokemon_red_completion.red_boxed_machine_options import boxed_frontier_machine_options
    from pokemon_red_completion.red_player_party_loan import _stock

    expected_mode = ("boxed_frontier_evolution_bundles_v3" if prepared_evolution
                     else "boxed_frontier_attack_capacity_v2")
    if (type(prepared_evolution) is not bool or plan.get("diagnostic_only") is not True
            or plan.get("actual_gameplay_resume_authorized") is not False
            or plan.get("copy_back") is not False or plan.get("fit_allowed") is not False
            or not declared_owned_machine_options(plan)
            or plan["owned_machine_options"]["mode"] != expected_mode):
        raise ValueError("boxed-machine copy requires explicit non-copy-back diagnostic authority")
    c = backend.c
    seconds = min(args.seconds,int(left["seconds"]),
        int((datetime.fromisoformat(plan["cutoff_utc"])-datetime.now(UTC)).total_seconds()))
    request = argparse.Namespace(decisions=1,actions=args.actions,frames=args.frames,seconds=seconds)
    limits = configured_execution_limits(request,left,seconds)
    prefix = "prepared-evolution" if prepared_evolution else "boxed-machine"
    output = root / f"diagnostics/{prefix}-{datetime.now(UTC).strftime('%H%M%S%f')}"
    output.mkdir(mode=0o700,parents=True,exist_ok=False)
    declaration = dict(partition="development",correlated_copy=True,copy_back=False,
        operator_diagnostic_choice=True,goal_model_queries=0,
        **player_wiring_declaration(plan),diagnostic_only=True,
        actual_gameplay_resume_authorized=False,fit_allowed=False,source=str(parent),
        source_sha256=context["state_sha256"],configuration_sha256=configuration.sha256,
        configuration=configuration.to_dict(),limits=asdict(limits),
        inherited_spent=context["spent"],launcher_sha256=c.digest(Path(__file__)))
    _record(output/"PLAN.json",declaration)
    _write(output/"executed-launcher.py",Path(__file__).read_bytes())
    payload,factory,menu,holder,source = assemble_configured_player(
        backend,configuration,parent,output,plan_path=output/"PLAN.json")
    if prepared_evolution:
        connect_declared_machine_options(menu,plan,rom=c.ROM.read_bytes(),
            holder=holder,configuration=configuration)
    result = dict(passed=False,error=None,copy_back=False,model_queries=0,fits=0,decisions=1,
        prepared_evolution=prepared_evolution)
    after = None
    with c.PyBoyAdapter(c.ROM) as em:
        em.load_state_bytes(payload)
        factory(ReadOnlyController(em))
        journal=output/"journal";journal.mkdir(mode=0o700)
        store=initialize_private_root(journal,repository_root=c.REPO,allow_same_device=True,
            **declared_input_recording(plan))
        session=NativePlayerSession(store=store,emulator=em,runtime_factory=factory,
            source=source,execution=NativeExecutionIdentity(root.name,output.name,
                configuration.goal_model_sha256,plan["seed"]),output=output/"native",
            limits=limits,combat_specimen_refs=tuple(m.specimen_ref for m in holder["plan"].roster
                if m.purpose.value=="combat"),battle_observer=holder["observe_history"],
            target_cash=0,model_feature_version=7,curriculum=declared_player_curriculum(
                plan,next(m.specimen_ref for m in holder["plan"].roster
                    if m.purpose.value=="combat")),
            allow_collection_restoration=True,force_resource_safety=False,include_live_pp_readiness=True)
        runtime=session.runtime;before=_stock(runtime)
        try:
            if prepared_evolution:
                choices=tuple(row for row in menu.enumerate_collection(runtime,session.actions,
                    runtime.adapter.observe()) if row.binding.binding_ref.startswith(
                        "pokemon.red:prepared-evolution:"))
            else:
                choices=boxed_frontier_machine_options(runtime,session.actions,
                    runtime.adapter.observe(),rom=c.ROM.read_bytes(),
                    world=holder["configured_route"].route_world)
            if not choices:
                raise ValueError("no observed boxed-frontier machine bundle is available")
            choice=max(choices,key=lambda row:row.candidate.features.dependency_unlock_gain)
            _record(output/"CHOICE.json",dict(binding_ref=choice.binding.binding_ref,
                operator_choice=True,selector="highest_declared_capacity_gain",
                available_bundles=len(choices),model_queries=0))
            session.active_kind=GoalKind.EVOLVE_SPECIES if prepared_evolution else GoalKind.DEVELOP_TEAM
            session.recorder.enabled=True
            report=choice.binding.execute();session.recorder.enabled=False
            verdict=choice.binding.verify(report);after=_stock(runtime)
            runtime.adapter.party_guard.verify_active_roster_restored()
            if prepared_evolution:
                from pokemon_red_completion.red_prepared_evolution_options import prepared_stock_progress

                progress=prepared_stock_progress(before,after)
                result.update(progress)
                result["recovery_accounting"]=evolution_recovery_accounting(session,report.evidence)
                stock_ok=all(progress.values()) and result["recovery_accounting"]["passed"]
            else:
                stock_ok=before==after
            result.update(passed=verdict.status.value=="succeeded" and stock_ok
                and _field_ready(runtime),evidence=dict(report.evidence),
                verification=verdict.status.value,stock_xp_preserved=stock_ok)
        except BaseException as error:
            result.update(error_type=type(error).__name__,error=str(error),
                error_chain=_exception_chain(error))
        finally:
            session.recorder.enabled=False;session.controller.input_enabled=False
            _write(output/"terminal.state",em.save_state_bytes())
            result.update(actions=len(session.recorder.trace),frames=session.controller.frames_executed,
                seconds=session.wall.elapsed_seconds,heals=session.heals,
                inner_healing_attempts=session.training_healing_trips,
                nested_restoration_attempts=session.support_restorations,
                original_roles_restored=set(runtime.adapter.party_guard.refs)
                    <=set(runtime.adapter.party_guard.reader.preparation_specimen_refs()),
                field_ready=_field_ready(runtime),released=not em.pressed_buttons,
                **player_lifecycle_fields(scope="diagnostic_chunk", released=not em.pressed_buttons,
                    guest_backend_closed=(em._backend is None) if hasattr(em,"_backend") else None),
                state_sha256=c.digest(output/"terminal.state"),configuration_sha256=configuration.sha256)
            if result["field_ready"] and result["original_roles_restored"]:
                try:
                    result.update(copied_native_cash_costs(session.actions))
                    spent=accumulate_player_costs(context["spent"],decisions=1,
                        actions=result["actions"],frames=result["frames"],seconds=result["seconds"],
                        heals=result["heals"],cash_deltas=native_cash_deltas(result, ()))
                    exported=capture_player_continuation(runtime,preparation=holder["plan"],
                        battle=None,spent=spent)
                    _record(output/"CONTEXT.json",exported)
                    result.update(spent=spent,context_sha256=c.digest(output/"CONTEXT.json"))
                except BaseException as error:
                    result.update(passed=False,context_error=str(error),
                        context_error_type=type(error).__name__,context_error_chain=_exception_chain(error))
            _record(output/"RESULT.json",result)
    result.update(player_lifecycle_fields(scope="driver_terminal", released=result["released"],
        guest_backend_closed=(em._backend is None) if hasattr(em,"_backend") else None))
    if result["passed"]:
        try:
            proof=verify_diagnostic_reload(c,factory,payload,output,after,result["spent"])
            result["reload_passed"]=proof["passed"]
            result["passed"]=bool(result["passed"] and proof["passed"])
        except BaseException as error:
            result.update(passed=False,reload_error=str(error),
                reload_error_type=type(error).__name__,reload_error_chain=_exception_chain(error))
        # Native RESULT is already immutable. Keep final reload status separately.
    _record(output/"FINAL-RESULT.json",result)
    authenticate_parent(parent,c.digest);verify_pins(plan["protected"])
    print(json.dumps(dict(result,output=str(output)),default=str),flush=True)


def run(args):
    path = Path(args.plan).resolve()
    plan, root = doc(path), path.parent
    declared_spectator(plan)
    if plan["partition"] != "development" or plan["fit_allowed"] or plan["copy_back"]:
        raise ValueError("configured launcher currently supports ordinary DEVELOPMENT only")
    experiment = declared_evolution_copy_experiment(plan)
    if experiment is not None and not (args.evolution_copy or args.inspect):
        raise ValueError("evolution experiment is restricted to the copy diagnostic entry")
    configuration = RedPlayerConfiguration.from_dict(plan["configuration"])
    if configuration.sha256 != plan["configuration_sha256"]:
        raise ValueError("durable player configuration differs from its declaration")
    verify_pins(plan["protected"])
    backend_sources = declared_backend_sources(plan)
    sys.path.insert(0, str(Path(plan["helpers_root"]).resolve()))
    backend = importlib.import_module(plan["backend_module"])
    verify_loaded_backend_sources(backend_sources, plan["helpers_root"])
    c = backend.c
    if "runtime_package" in plan:
        from pokemon_red_completion.red_player_package import bind_player_package

        package = plan["runtime_package"]
        manifest = bind_player_package(package["path"], package["sha256"], history_output=root)
        c.FROZEN_SOURCE_COMMIT = manifest["source_commit"]
    origin = Path(plan["parent"])
    original = authenticate_parent(origin, c.digest)
    if (
        original["state_sha256"] != plan["source_sha256"]
        or c.digest(origin / "CONTEXT.json") != plan["context_sha256"]
        or original["spent"] != plan["inherited_spent"]
    ):
        raise ValueError("original configured checkpoint differs")
    if args.loan_copy_source:
        if not args.guard_source or args.inspect:
            raise ValueError("loan diagnostic requires its declared original roster source")
        verify_loan_copy(args, plan, root, backend, configuration)
        return
    nodes, ordinal = configured_run_nodes(root)
    parent = nodes[-1] if nodes else origin
    context = authenticate_parent(parent, c.digest)
    search_memory = (
        GoalSearchMemory.from_private_dict(context["search_memory"])
        if "search_memory" in context
        else GoalSearchMemory()
    )
    if nodes and doc(parent / "PLAN.json")["configuration_sha256"] != configuration.sha256:
        raise ValueError("cannot silently change configuration across a continuation")
    left = remaining_allowance(
        context["spent"], plan["inherited_spent"], plan["allowance"], inspection=args.inspect
    )
    copies = diagnostic_spending(root)
    left = {key: value - copies[key] for key, value in left.items()}
    if min(left.values()) <= 0 and not args.inspect:
        raise ValueError("configured block exhausted its separate diagnostic-inclusive allowance")
    prepared_copy = getattr(args, "prepared_evolution_copy", False)
    boxed_copy = getattr(args, "boxed_machine_copy", False)
    if prepared_copy or boxed_copy:
        if args.inspect or args.evolution_copy or prepared_copy and boxed_copy:
            raise ValueError("machine copies require one separate diagnostic mode")
        verify_boxed_machine_copy(args, plan, root, backend, configuration, parent, context, left,
            prepared_evolution=prepared_copy)
        return
    if args.evolution_copy:
        if args.inspect:
            raise ValueError("evolution copy and zero-input inspection are separate modes")
        verify_evolution_copy(args, plan, root, backend, configuration, parent, context, left)
        return
    model = declared_goal_model(plan, configuration, backend)
    refinement = declared_readiness_refinement(plan)
    greedy = declared_greedy_selection(plan)
    preparation_component = declared_preparation_component(plan)
    input_recording = declared_input_recording(plan)
    machine_options = declared_owned_machine_options(plan)
    declared_automatic_renewal(plan)
    wiring = player_wiring_declaration(plan)
    output = root / (
        f"inspections/inspect-{datetime.now(UTC).strftime('%H%M%S%f')}"
        if args.inspect
        else f"runs/segment-{ordinal:03d}"
    )
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    declaration = dict(
        partition="development",
        actual_parent=str(parent),
        source_sha256=context["state_sha256"],
        context_sha256=c.digest(parent / "CONTEXT.json"),
        inherited_spent=context["spent"],
        configuration_sha256=configuration.sha256,
        configuration=configuration.to_dict(),
        **wiring,
        **({"goal_model_observation_identity": dict(
            stored_model_sha256=configuration.goal_model_sha256,
            effective_model_sha256=model.model_sha256,
        )} if "goal_model_observation_compatibility" in wiring else {}),
        fit_allowed=False,
        new_origin=False,
        copy_back=False,
        source_identity=c.source_code_identity(c.REPO),
        backend_sha256=c.digest(Path(backend.__file__)),
        backend_sources_sha256=canonical_sha256(backend_sources) if backend_sources else None,
        backend_sources_count=len(backend_sources),
        launcher_sha256=c.digest(Path(__file__)),
        exploratory=True,
        separate_diagnostic_costs=copies,
        automatic_runtime_renewal=plan.get("automatic_runtime_renewal"),
        same_live_emulator=True,
        state_restoration=False,
    )
    _record(output / "PLAN.json", declaration)
    try:
        payload, factory, menu, holder, source = assemble_configured_player(
            backend, configuration, parent, output, plan_path=output / "PLAN.json",
            model_feature_version=model.feature_version,
            **({"include_preparation_party_context": True} if refinement.get("consequence_head") is not None
               and refinement["consequence_head"].context_projection=="prospective_preparation_party_context_v1" else {}),
        )
    except BaseException as error:
        _record(
            output / "PRELAUNCH-ERROR.json",
            dict(
                phase="before_emulator",
                released=True,
                **player_lifecycle_fields(scope="prelaunch_failure", released=True,
                    guest_backend_closed=None),
                state_loads=0,
                inputs=0,
                frames=0,
                passed=False,
                error_type=type(error).__name__,
                error=str(error),
            ),
        )
        raise
    if machine_options:
        rom = c.ROM.read_bytes()
        connect_declared_machine_options(menu,plan,rom=rom,holder=holder,
            configuration=configuration)
    with RunFrameFeed(plan, root, enabled=not args.inspect) as feed, c.PyBoyAdapter(
        c.ROM, **feed.adapter_options
    ) as em:
        em.load_state_bytes(payload)
        runtime = factory(ReadOnlyController(em))
        verify_loaded_backend_sources(backend_sources, plan["helpers_root"])
        roles = tuple(m.specimen_ref for m in holder["plan"].roster if m.purpose.value == "combat")
        if args.inspect:
            actions = InspectionExecutor(FrameSafeExecutor(ReadOnlyController(em)))
            bird_loan_inspection = None
            if plan.get("bird_capture_loan") is not None:
                from red_mixed_bird_collection_20261009 import bird_loan_guard

                loan_guard = bird_loan_guard(runtime, plan["bird_capture_loan"])
                bird_loan_inspection = dict(
                    available=loan_guard is not None,
                    loanable_refs=[] if loan_guard is None else sorted(loan_guard.loanable_refs),
                    original_refs=[] if loan_guard is None else list(loan_guard.refs),
                    eligibility_only=True,
                    capture_executed=False,
                )
            options = observe_native_player_options(
                runtime,
                actions,
                battle=holder["observe_history"](),
                combat_specimen_refs=roles,
                remaining_budget=(1.0,) * 5,
                target_cash=0,
                ordering_seed_sha256=canonical_sha256({"ordinal": ordinal}),
                allow_support=True,
                model_feature_version=model.feature_version,
                force_resource_safety=False,
                include_live_pp_readiness=True,
                **menu.native_callbacks(),
            )
            choice = None
            if isinstance(options, RedLiveOptionSet):
                if any(b.kind is GoalKind.ACQUIRE_SPECIES for b in options.bindings):
                    options = menu_with_search_history(
                        options,
                        search_memory,
                        objective_key(
                            {
                                "owned_species": sorted(
                                    runtime.adapter.observe().collection_observation.owned_species
                                ),
                            }
                        ),
                    )
                choice = (
                    select_branch_recovery_live_option(
                        model,
                        options,
                        refinement["consequence_head"],
                        objective_ref=refinement["consequence_objective_ref"],
                        seed=plan["seed"] + ordinal,
                        greedy_selection=greedy,
                        refine_preparation=refinement.get("refine_preparation", False),
                        defer_unbound_preparation=refinement.get("defer_unbound_preparation", False),
                        allow_singleton_parent_support=refinement.get("allow_singleton_parent_support", False),
                    )
                    if refinement
                    else select_red_live_option(
                        model, options, seed=plan["seed"] + ordinal, greedy_selection=greedy,
                        exploration_mix=declared_exploration_mix(plan),
                    )
                )
            bindings = (
                options.bindings if isinstance(options, RedLiveOptionSet) else (options.binding,)
            )
            result = dict(
                passed=em.save_state_bytes() == payload
                and em.frame_count == 0
                and not em.pressed_buttons
                and actions.actions_executed == 0,
                state_sha256=context["state_sha256"],
                inputs=0,
                frames=0,
                configuration_sha256=configuration.sha256,
                goal_model_sha256=model.model_sha256,
                goal_model_record=plan.get("goal_model_record"),
                inherited_spent=context["spent"],
                party_guard_present=isinstance(runtime.adapter.party_guard, RedPlayerPartyGuard),
                settlement_present=callable(runtime.evolution_settlement),
                native_facts=native_checkpoint_facts(runtime),
                inventory=[
                    dict(
                        kind=b.kind.value,
                        objective=b.story_objective_ref,
                        binding_ref=b.binding_ref,
                    )
                    for b in bindings
                ],
                selected=None
                if choice is None
                else dict(
                    kind=choice.selected_binding.kind.value,
                    objective=choice.selected_binding.story_objective_ref,
                ),
                model_queries=(
                    0
                    if choice is None
                    else 1
                    if choice.branch_recovery is None
                    else choice.branch_recovery.document()["model_queries"]
                ),
                readiness_refinement=plan.get("readiness_refinement"),
                goal_selection=plan.get("goal_selection"),
                league_first_collection_scope=declared_league_first_collection_scope(plan),
                bird_loan_eligibility=bird_loan_inspection,
            )
            result.update(
                backend_sources_count=len(backend_sources),
                backend_sources_sha256=(
                    canonical_sha256(backend_sources) if backend_sources else None
                ),
                search_memory_sha256=canonical_sha256(search_memory.private_dict()),
                quote_capture_route_work=configuration.quote_capture_route_work,
                route_work_quotes=[
                    event["payload"]
                    for event in actions.diagnostics
                    if event["kind"] == "capture_route_work_quote"
                ],
            )
            if choice is not None:
                _record(output / "MENU.json", options.menu.policy_dict())
                _record(output / "CHOICE.json", choice.public_dict())
            _record(output / "DIAGNOSTICS.json", actions.diagnostics)
            verify_loaded_backend_sources(backend_sources, plan["helpers_root"])
            verify_pins(plan["protected"])
            _record(output / "RESULT.json", result)
            print(json.dumps(result), flush=True)
            return
        automatic = declared_automatic_renewal(plan)
        if automatic or "runtime_package" in plan:
            journal = root / "journal"
            if journal.exists():
                store = open_private_root(
                    journal, repository_root=c.REPO, allow_same_device=True, **input_recording
                )
            else:
                journal.mkdir(mode=0o700)
                store = initialize_private_root(
                    journal, repository_root=c.REPO, allow_same_device=True, **input_recording
                )
        else:
            store = c.open_private_root(
                c.BASE / "goal-manager-v1",
                repository_root=c.REPO,
                allow_same_device=True,
                **input_recording,
            )
        renewed = 0
        driver_terminal_reason = None
        while True:
            wall_left = int(
                (datetime.fromisoformat(plan["cutoff_utc"]) - datetime.now(UTC)).total_seconds()
            )
            if wall_left <= 0:
                raise ValueError("configured work block ended; no inputs authorized by this plan")
            limits = configured_execution_limits(args, left, wall_left)
            _write(output / "executed-launcher.py", Path(__file__).read_bytes())
            _write(output / "executed-backend.py", Path(backend.__file__).read_bytes())
            result, exported = execute_player_chunk(
                plan=plan,
                configuration=configuration,
                c=c,
                emulator=em,
                factory=factory,
                menu=menu,
                holder=holder,
                source=source,
                output=output,
                model=model,
                limits=limits,
                memory=search_memory,
                store=store,
                ordinal=ordinal,
            )
            reason = chunk_continuation_reason(
                result, source_sha256=context["state_sha256"], limits=limits
            )
            if automatic and reason == "native_execution_error":
                handoff = qualified_menu_control_handoff(
                    result, runtime=holder["runtime"], menu=menu,
                )
                if handoff is not None:
                    result["qualified_native_control_handoff"] = handoff
                    reason = "automatic_control_recovery"
            result.update(continuation_reason=reason, automatic_renewals=renewed)
            _record(output / "RESULT.json", result)
            print(
                json.dumps(
                    dict(
                        segment=ordinal,
                        continuation_reason=reason,
                        native_facts=result["native_facts"],
                        spent=result["spent"],
                    )
                ),
                flush=True,
            )
            if not automatic or reason not in AUTOMATIC_CONTINUATIONS:
                driver_terminal_reason = reason
                break
            try:
                left = remaining_allowance(
                    exported["spent"], plan["inherited_spent"], plan["allowance"]
                )
                left = {key: value - copies[key] for key, value in left.items()}
                if min(left.values()) <= 0:
                    driver_terminal_reason = "declared_budget_exhausted"
                    break
            except ValueError:
                driver_terminal_reason = "declared_budget_exhausted"
                break
            if (datetime.fromisoformat(plan["cutoff_utc"]) - datetime.now(UTC)).total_seconds() < 1:
                driver_terminal_reason = "declared_cutoff_reached"
                break
            if (
                requires_compulsory_settlement(holder["runtime"])
                and min(args.decisions, int(left["decisions"])) < 2
            ):
                driver_terminal_reason = "insufficient_settlement_allowance"
                break
            parent, context = output, exported
            ordinal, renewed = ordinal + 1, renewed + 1
            output = root / f"runs/segment-{ordinal:03d}"
            output.mkdir(mode=0o700, parents=True, exist_ok=False)
            declaration = dict(
                declaration,
                actual_parent=str(parent),
                source_sha256=context["state_sha256"],
                context_sha256=c.digest(parent / "CONTEXT.json"),
                inherited_spent=context["spent"],
                same_live_emulator=True,
                state_restoration=False,
                automatic_runtime_renewal=plan["automatic_runtime_renewal"],
            )
            _record(output / "PLAN.json", declaration)
            payload, factory, menu, holder, source = assemble_configured_player(
                backend, configuration, parent, output, plan_path=output / "PLAN.json",
                model_feature_version=model.feature_version,
                **({"include_preparation_party_context": True} if refinement.get("consequence_head") is not None
                   and refinement["consequence_head"].context_projection=="prospective_preparation_party_context_v1" else {}),
            )
            if payload != em.save_state_bytes():
                raise ValueError("automatic renewal changed the retained native state")
            if machine_options:
                connect_declared_machine_options(menu,plan,rom=c.ROM.read_bytes(),
                    holder=holder,configuration=configuration)
            factory(ReadOnlyController(em))
    result = dict(
        result,
        **player_lifecycle_fields(scope="driver_terminal", released=result.get("released") is True,
            guest_backend_closed=em._backend is None),
        driver_terminal_reason=driver_terminal_reason,
    )
    driver_path = root / f"DRIVER-RESULT-{ordinal:03d}.json"
    _record(driver_path, result)
    verify_pins(plan["protected"])
    authenticate_parent(origin, c.digest)
    verify_loaded_backend_sources(backend_sources, plan["helpers_root"])
    print(json.dumps({k: v for k, v in result.items() if k != "episode"}, default=str), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--inspect", action="store_true")
    parser.add_argument("--loan-copy-source")
    parser.add_argument("--guard-source")
    parser.add_argument("--evolution-copy", action="store_true")
    parser.add_argument("--boxed-machine-copy", action="store_true")
    parser.add_argument("--prepared-evolution-copy", action="store_true")
    parser.add_argument("--decisions", type=int, default=48)
    parser.add_argument("--actions", type=int, default=30000)
    parser.add_argument("--frames", type=int, default=2500000)
    parser.add_argument("--seconds", type=int, default=600)
    run(parser.parse_args())
