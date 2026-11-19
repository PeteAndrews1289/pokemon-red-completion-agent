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
from pokemon_red_completion.living_dex_option_value import (
    upgrade_option_value_model_for_matchup,
    upgrade_option_value_model_for_story_unit,
)
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
    declared_evolution_recipient_yield,
    declared_native_evolution_venue_model,
    player_lifecycle_fields,
)
from pokemon_red_completion.red_player_continuation import (
    SCHEMA as PLAYER_CONTINUATION_SCHEMA,
)
from pokemon_red_completion.red_player_continuation import (
    _costs as continuation_costs,
)
from pokemon_red_completion.red_player_continuation import (
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
        or spec["mode"]
        not in {
            "direct_attack_capacity_v1",
            "boxed_frontier_attack_capacity_v2",
            "boxed_frontier_evolution_bundles_v3",
        }
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
        or spec["mode"] not in {"v9_to_v15_zero_extension_v1", "v9_to_v16_zero_extension_v1"}
        or not isinstance(spec["reason"], str)
        or not spec["reason"].strip()
        or any(
            type(spec[key]) is not str
            or len(spec[key]) != 64
            or any(c not in "0123456789abcdef" for c in spec[key])
            for key in ("source_model_sha256", "target_model_sha256")
        )
    ):
        raise ValueError(
            "goal observation compatibility requires an explicit pinned "
            "DEVELOPMENT V9-to-V15 declaration"
        )
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
        if model.feature_version != 9 or model.model_sha256 != compatibility["source_model_sha256"]:
            raise ValueError(
                "goal observation compatibility source differs from authenticated V9 record"
            )
        target_version = 16 if compatibility["mode"] == "v9_to_v16_zero_extension_v1" else 15
        model = (
            upgrade_option_value_model_for_story_unit(model)
            if target_version == 16
            else upgrade_option_value_model_for_matchup(model)
        )
        if (
            model.feature_version != target_version
            or model.model_sha256 != compatibility["target_model_sha256"]
        ):
            raise ValueError("goal observation compatibility target differs from zero extension")
    return model



def declared_sequence_options(plan, model=None):
    """Load one pinned DEVELOPMENT policy with its explicit inference task contract.

    This path never invents task-terminal markers or changes training admission.
    Full horizons remain observed; unfinished tails remain censored.
    """
    spec = plan.get("sequence_policy")
    if spec is None:
        return {}
    from pokemon_red_completion.player_sequence_policy import SequencePolicy
    from pokemon_red_completion.player_sequence_targets import TASK_TERMINAL_TARGET_CONTRACT, RESOURCE_TASK_TARGET_CONTRACT, registration_task_catalog
    required = {"path", "content_sha256", "policy_sha256", "target_contract",
                "task_sha256", "task_catalog", "window_stride", "reason"}
    if (plan.get("partition") != "development" or type(spec) is not dict
        or set(spec) != required or any(type(spec[k]) is not str or not spec[k].strip()
            for k in ("path", "reason"))
        or any(type(spec[k]) is not str or len(spec[k]) != 64
               or any(c not in "0123456789abcdef" for c in spec[k])
               for k in ("content_sha256", "policy_sha256", "task_sha256"))
        or spec["target_contract"] not in (TASK_TERMINAL_TARGET_CONTRACT, RESOURCE_TASK_TARGET_CONTRACT)
        or declared_greedy_selection(plan) or plan.get("readiness_refinement") is not None):
        raise ValueError("sequence policy requires pinned exploratory DEVELOPMENT task wiring")
    catalog = spec["task_catalog"]
    if (type(catalog) is not dict or set(catalog) != {"path", "content_sha256"}
        or type(catalog["path"]) is not str or not catalog["path"].strip()
        or type(catalog["content_sha256"]) is not str or len(catalog["content_sha256"]) != 64
        or any(c not in "0123456789abcdef" for c in catalog["content_sha256"])):
        raise ValueError("sequence task requires a pinned catalog")
    catalog_payload = Path(catalog["path"]).read_bytes()
    if sha256(catalog_payload).hexdigest() != catalog["content_sha256"]:
        raise ValueError("sequence task catalog content differs")
    task = json.loads(catalog_payload)
    from pokemon_red_completion.constants import POKEMON_RED_US_REV_0
    registration_task = task.get("schema") == "pokemon.red.next-native-registration-task.v1"
    if ((registration_task and task != registration_task_catalog(POKEMON_RED_US_REV_0.sha256))
        or (not registration_task and task.get("schema") != "pokemon.red.pure-parent-prospective-state-catalog.v1")
        or task.get("task_sha256") != spec["task_sha256"]):
        raise ValueError("sequence task identity differs from pinned catalog")
    payload = Path(spec["path"]).read_bytes()
    if sha256(payload).hexdigest() != spec["content_sha256"]:
        raise ValueError("sequence policy content differs")
    policy = SequencePolicy.from_document(json.loads(payload), expected_sha256=spec["policy_sha256"])
    if (policy.task_return_scope is not None and not registration_task
        or policy.head.target_contract != spec["target_contract"]
        or policy.exploration_mix != declared_exploration_mix(plan)
        or policy.selection_mode in {"stable_recurrence", "stable_costly_recurrence"} and plan.get("movement_revisit_saturation") is not True
        or policy.head.feature_version == 16 and plan.get("include_preparation_party_context") is not True
        or type(spec["window_stride"]) is not int
        or not 1 <= spec["window_stride"] <= policy.head.horizon
        or model is not None and (policy.baseline_sha256 != model.model_sha256
                                  or policy.head.feature_version != model.feature_version)):
        raise ValueError("sequence policy model, target contract or sampler differs")
    return dict(sequence_policy=policy, sequence_horizon=policy.head.horizon,
                sequence_window_stride=spec["window_stride"],
                sequence_target_contract=spec["target_contract"],
                sequence_task_sha256=spec["task_sha256"],
                **({"sequence_task_kind": "next_registration"} if registration_task else {}))


def declared_preparation_context(plan):
    for key in ("include_preparation_party_context", "retain_story_preparation_opposition"):
        if key in plan and (type(plan[key]) is not bool or plan.get("partition") != "development"):
            raise ValueError("preparation observations require explicit DEVELOPMENT booleans")
    return plan.get("include_preparation_party_context", False)


def declared_resource_safety(plan):
    value = plan.get("force_resource_safety", False)
    if type(value) is not bool or "force_resource_safety" in plan and plan.get("partition") != "development":
        raise ValueError("resource safety requires an explicit DEVELOPMENT boolean")
    return value


def validate_sequence_runner_mode(plan, args):
    """Unsupported diagnostic selectors fail before backend or emulator creation."""
    if plan.get("sequence_policy") is not None and any(
        getattr(args, name, False) for name in
        ("inspect", "loan_copy_source", "evolution_copy", "boxed_machine_copy", "prepared_evolution_copy")
    ):
        raise ValueError("sequence policy requires the ordinary shared execution path; diagnostic selector unsupported")


def validate_continued_sequence_wiring(plan, previous):
    if plan.get("compare_evolution_recipient_yield", False) != previous.get("compare_evolution_recipient_yield", False):
        raise ValueError("continued evolution venue comparison differs")
    if plan.get("regional_coverage", False) != previous.get("regional_coverage", False):
        raise ValueError("continued regional coverage mode differs")
    if plan.get("collection_cost_frame_horizon") != previous.get("collection_cost_frame_horizon"):
        raise ValueError("continued collection cost horizon differs")
    if any(plan.get(key) != previous.get(key) for key in ("sequence_policy", "force_resource_safety", "include_preparation_party_context", "retain_story_preparation_opposition", "native_owned_stock_income", "registration_task_continuation")):
        raise ValueError("cannot silently change sequence policy/task or resource safety across a continuation")

def connect_owned_machine_options(
    menu,
    *,
    rom,
    include_boxed_frontier=False,
    boxed_world=None,
    include_prepared_evolution=False,
    admits=None,
):
    """Extend the existing ports; preserve ordinary choices and exclusions."""
    if type(include_boxed_frontier) is not bool or (
        include_boxed_frontier and not callable(boxed_world)
    ):
        raise ValueError("boxed-machine options require their declared route binding")
    if (
        type(include_prepared_evolution) is not bool
        or include_prepared_evolution
        and (
            not include_boxed_frontier
            or not callable(admits)
            or not callable(getattr(menu, "enumerate_collection", None))
        )
    ):
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
            from pokemon_red_completion.red_boxed_machine_options import (
                boxed_frontier_machine_options,
            )

            rows += boxed_frontier_machine_options(
                runtime, actions, observation, rom=rom, world=world_now()
            )
        return rows

    menu.enumerate_owned_machines = observe
    if include_prepared_evolution:
        collection = menu.enumerate_collection

        def observe_collection(runtime, actions, observation):
            rows = collection(runtime, actions, observation)
            if runtime.reader.read().badge_bits != 255:
                return rows
            from pokemon_red_completion.red_boxed_machine_options import (
                quoted_boxed_frontier_machine_options,
            )
            from pokemon_red_completion.red_prepared_evolution_options import (
                prepared_evolution_options,
            )

            choices = quoted_boxed_frontier_machine_options(
                runtime, actions, observation, rom=rom, world=world_now()
            )
            return rows + prepared_evolution_options(
                runtime,
                actions,
                observation,
                machine_choices=choices,
                evolution_options=rows,
                enumerate_collection=collection,
                admits=admits,
            )

        menu.enumerate_collection = observe_collection


def connect_declared_machine_options(menu, plan, *, rom, holder, configuration):
    if not declared_owned_machine_options(plan):
        return
    mode = plan["owned_machine_options"]["mode"]
    connect_owned_machine_options(
        menu,
        rom=rom,
        include_boxed_frontier=mode
        in {"boxed_frontier_attack_capacity_v2", "boxed_frontier_evolution_bundles_v3"},
        boxed_world=lambda: holder["configured_route"].route_world,
        include_prepared_evolution=mode == "boxed_frontier_evolution_bundles_v3",
        admits=configuration.admits if mode == "boxed_frontier_evolution_bundles_v3" else None,
    )


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
                or (
                    not checkpoint_quiescent(row)
                    if "checkpoint_lifecycle" in row
                    else row.get("worker_stopped") is not True
                )
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
    result = {
        key: getattr(actions, key)
        for key in ("observed_cash_debits", "observed_cash_rewards", "observed_cash_changes")
    }
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


def configured_renewal_stop_reason(args, left, wall_left, *, compulsory_settlement):
    """Do not turn a return reserve into a fresh goal's setup allowance.

    Derive reserves from the requested chunk, before aggregate/cutoff clipping.
    A fresh goal needs a productive allowance plus its settlement reserve.
    Recomputing either allowance after clipping would admit a late chunk with
    too little headroom. This matches the within-chunk admission margin; it is
    not a bound on arbitrary route costs. Existing compulsory recovery may use
    the remaining allowance, and every hard limit remains unchanged.
    """
    if type(compulsory_settlement) is not bool:
        raise TypeError("renewal settlement state must be boolean")
    if wall_left < 1:
        return "declared_cutoff_reached"
    # Native limits use whole positive units; a floating remainder must stop,
    # never be rounded up or converted into an invalid zero-second recovery.
    if any(int(left[axis]) < 1 for axis in ("decisions", "actions", "frames", "seconds")):
        return "declared_budget_exhausted"
    limits = configured_execution_limits(args, left, wall_left)
    if compulsory_settlement:
        return "insufficient_settlement_allowance" if limits.decisions < 2 else None
    requested = dict(
        actions=getattr(args, "actions", 30000),
        frames=getattr(args, "frames", 2500000),
        seconds=args.seconds,
    )
    reserves = {
        axis: min(cap, max(1, requested[axis] // 4))
        for axis, cap in (("actions", 3000), ("frames", 250000), ("seconds", 60))
    }
    if any(getattr(limits, axis) <= 2 * reserve for axis, reserve in reserves.items()):
        return "insufficient_settlement_allowance"
    return None


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


def _paired_context_authenticated(exported, saved_export, result, spent):
    """Compare capture/export facts; full native/custody validation stays in restore.

    Optional fields match the already supported continuation reader contract.
    They remain part of canonical equality, never fields to discard or trust.
    """
    required_export = {
        "schema", "state_sha256", "lesson", "cash", "bag", "preparation",
        "battle", "spent", "grants_new_budget", "fit_allowed",
    }
    optional_export = {
        "search_memory", "field_carrier", "story_kind_commitment", "preparation_story_loss",
    }
    return bool(
        type(exported) is dict
        and type(saved_export) is dict
        and set(exported) - optional_export == required_export
        and set(saved_export) - optional_export == required_export
        and exported.get("schema") == PLAYER_CONTINUATION_SCHEMA
        and canonical_sha256(exported) == canonical_sha256(saved_export)
        and exported.get("state_sha256") == result["state_sha256"]
        and exported.get("spent") == spent
        and exported.get("grants_new_budget") is False
        and exported.get("fit_allowed") is False
        and result["context_sha256"]
        and not result.get("checkpoint_export_error")
    )


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
        or not {"mode", "reason"} <= set(spec)
        <= {"mode", "reason", "exploration_mix", "story_milestone_commitment", "story_kind_commitment", "respect_combat_preparation_choice"}
        or type(spec["mode"]) is not str
        or spec["mode"] not in {"greedy", "exploration"}
        or type(spec["reason"]) is not str
        or not spec["reason"].strip()
        or plan.get("partition") != "development"
    ):
        raise ValueError("goal selection requires an explicit ordinary DEVELOPMENT declaration")
    if "exploration_mix" in spec:
        mix = spec["exploration_mix"]
        if (
            spec["mode"] != "exploration"
            or isinstance(mix, bool)
            or not isinstance(mix, (int, float))
            or not 0 <= mix <= 1
            or plan.get("readiness_refinement") is not None
        ):
            raise ValueError("custom exploration requires separate ordinary DEVELOPMENT selection")
    respect = spec.get("respect_combat_preparation_choice", False)
    if type(respect) is not bool or (respect and (
        spec.get("story_kind_commitment") is not True or spec.get("story_milestone_commitment") is not True
    )):
        raise ValueError("combat preparation choice requires declared story commitment")
    return spec["mode"] == "greedy"


def declared_story_milestone_commitment(plan):
    """M0 opt-in: keep a selected story objective until it completes or is no longer offered.

    Declared inside the existing DEVELOPMENT goal_selection block; kind-level choices
    (heal, train, catch, evolve, resupply) stay with the goal model.
    """
    declared_greedy_selection(plan)
    value = (plan.get("goal_selection") or {}).get("story_milestone_commitment", False)
    if type(value) is not bool:
        raise ValueError("milestone story commitment must be an explicit boolean")
    return value


def declared_story_kind_commitment(plan):
    """Session-32 opt-in: while a story objective is under way and the party is fit, keep advancing it
    instead of a detour of another goal kind (see red_story_kind_commitment). Requires milestone commitment.
    """
    declared_greedy_selection(plan)
    spec = plan.get("goal_selection") or {}
    value = spec.get("story_kind_commitment", False)
    if type(value) is not bool:
        raise ValueError("kind-level story commitment must be an explicit boolean")
    if value and spec.get("story_milestone_commitment") is not True:
        raise ValueError("kind-level story commitment requires milestone story commitment")
    return value


def _story_kind_commitment_carrier(holder):
    """One carrier per chunk, restored from its authenticated parent continuation."""
    from pokemon_red_completion.red_story_kind_commitment import StoryKindCommitmentCarrier

    carrier = holder.get("story_kind_commitment_carrier")
    if carrier is None:
        carrier = holder["story_kind_commitment_carrier"] = StoryKindCommitmentCarrier()
    return carrier


def declared_exploration_mix(plan):
    """Forward the existing sampler knob; keep the historical default unchanged."""
    declared_greedy_selection(plan)
    return float((plan.get("goal_selection") or {}).get("exploration_mix", 0.25))


def declared_input_recording(plan):
    """Declare existing isolation and lossless recording representation, not less evidence.

    ``packed_sealed_v1`` keeps every sealed native record byte-for-byte in
    hash-chained append-only segments and adds per-press cartridge observations.
    """
    spec = plan.get("input_recording")
    if spec is None:
        return {}
    if (
        not isinstance(spec, dict)
        or not {"git_worktree_probe", "reason"}
        <= set(spec)
        <= {"git_worktree_probe", "reason", "native_input_storage", "isolation_report"}
        or spec["git_worktree_probe"] != "gitless_fast_path_v1"
        or type(spec["reason"]) is not str
        or not spec["reason"].strip()
        or plan.get("partition") != "development"
        or (
            "native_input_storage" in spec
            and spec["native_input_storage"] not in ("flat_sealed_v1", "packed_sealed_v1")
        )
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
    if not isinstance(spec, dict) or (("objective_ref" in spec) == ("objective_refs" in spec)):
        raise ValueError("readiness refinement requires one explicit branch scope")
    plural = "objective_refs" in spec
    scope_key = "objective_refs" if plural else "objective_ref"
    if plural and type(spec[scope_key]) is not list:
        raise ValueError("readiness branch set requires a declared JSON list")
    objective_ref = tuple(spec[scope_key]) if plural else spec[scope_key]
    scope = branch_recovery_objectives(objective_ref)
    if plural and (plan.get("partition") != "development" or not declared_greedy_selection(plan)):
        raise ValueError("readiness branch set requires explicit greedy DEVELOPMENT scope")
    if (
        not {scope_key, "head_path", "head_sha256", "content_sha256", "reason"}
        <= set(spec)
        <= {
            scope_key,
            "head_path",
            "head_sha256",
            "content_sha256",
            "reason",
            "refine_preparation",
            "defer_unbound_preparation",
            "allow_singleton_parent_support",
            "associate_unique_combat",
            "explore_outside_scope",
            "explore_on_movement_recurrence",
        }
        or any(ref not in plan["objectives"] for ref in scope)
        or not isinstance(spec["reason"], str)
        or not spec["reason"].strip()
    ):
        raise ValueError("readiness refinement requires one declared objective and reuse reason")
    refine_preparation = spec.get("refine_preparation", False)
    if (
        type(refine_preparation) is not bool
        or refine_preparation
        and (plan.get("partition") != "development" or not declared_greedy_selection(plan))
    ):
        raise ValueError("preparation refinement requires declared greedy DEVELOPMENT scope")
    defer_unbound_preparation = spec.get("defer_unbound_preparation", False)
    allow_singleton_parent_support = spec.get("allow_singleton_parent_support", False)
    if (
        type(defer_unbound_preparation) is not bool
        or type(allow_singleton_parent_support) is not bool
        or (defer_unbound_preparation or allow_singleton_parent_support)
        and (plan.get("partition") != "development" or not declared_greedy_selection(plan))
        or allow_singleton_parent_support
        and not defer_unbound_preparation
    ):
        raise ValueError("parent-bound preparation requires explicit greedy DEVELOPMENT scope")
    associate_unique_combat = spec.get("associate_unique_combat", False)
    if (
        type(associate_unique_combat) is not bool
        or associate_unique_combat
        and (
            not refine_preparation
            or defer_unbound_preparation
            or allow_singleton_parent_support
            or plan.get("partition") != "development"
            or not declared_greedy_selection(plan)
        )
    ):
        raise ValueError(
            "unique combat association requires unmasked DEVELOPMENT preparation refinement"
        )
    explore_outside_scope = spec.get("explore_outside_scope", False)
    if (
        type(explore_outside_scope) is not bool
        or explore_outside_scope and (
            not refine_preparation or defer_unbound_preparation
            or allow_singleton_parent_support
            or plan.get("partition") != "development"
            or not declared_greedy_selection(plan)
        )
    ):
        raise ValueError("out-of-scope exploration requires unmasked DEVELOPMENT refinement")
    explore_on_movement_recurrence = spec.get("explore_on_movement_recurrence", False)
    if (type(explore_on_movement_recurrence) is not bool
            or explore_on_movement_recurrence and (
                not refine_preparation or defer_unbound_preparation
                or allow_singleton_parent_support or explore_outside_scope
                or plan.get("partition") != "development"
                or not declared_greedy_selection(plan)
                or plan.get("movement_revisit_saturation") is not True)):
        raise ValueError("recurrence escape requires observed movement history and greedy DEVELOPMENT refinement")
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
        **({"associate_unique_combat": True} if associate_unique_combat else {}),
        **({"explore_outside_scope": True} if explore_outside_scope else {}),
        **({"explore_on_movement_recurrence": True} if explore_on_movement_recurrence else {}),
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
    "movement_revisit_saturation",
    "owned_field_carrier_exchange",
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


def checkpoint_error_for_export(error_type, error_message, error_chain):
    """Keep the primary failure; pass only an authenticated budget cause to export.

    League funding wraps the controller stop. The history provider separately
    checks the actual failed battle log and terminal; this does not label a win,
    admit fresh inference, erase the wrapper, or authorize another runtime.
    """
    kind, message = error_type, error_message
    if kind == "RedLeagueFundingExecutionError":
        if (
            type(error_chain) is not list or len(error_chain) != 2
            or any(type(row) is not dict for row in error_chain)
            or error_chain[0].get("error_type") != error_type
            or error_chain[0].get("error") != error_message
            or error_chain[1].get("error_type") not in CHUNK_BUDGET_ERRORS
        ):
            return None, None
        kind, message = error_chain[1]["error_type"], error_chain[1].get("error")
    if kind not in CHECKPOINT_ERRORS or (
        kind == "ControllerFrameBudgetError"
        and message != "controller exhausted its hard frame budget"
    ):
        return None, None
    return kind, message


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


def declared_registration_task_continuation(plan):
    """Opt in to the existing live loop across completed collection tasks."""
    spec = plan.get("registration_task_continuation")
    if spec is None:
        return False
    if spec != "live_next_registration_v1" or not declared_automatic_renewal(plan):
        raise ValueError("registration task continuation needs its declared live loop")
    from pokemon_red_completion.red_player_curriculum import validate_full_red_curriculum_plan
    validate_full_red_curriculum_plan(plan)
    if declared_sequence_options(plan).get("sequence_task_kind") != "next_registration":
        raise ValueError("registration task continuation needs the matching numerical task")
    return True


def qualified_registration_task_handoff(result, *, plan, runtime, output):
    """Continue only an authenticated successful task; never retry a failure.

    Native target admission stays with the independent referee. This read-only
    guard grants no inputs, choice, fit label or budget. Existing live renewal
    carries the exact context, costs, memory and guest to the next ordinary menu.
    """
    if not declared_registration_task_continuation(plan):
        return None
    try:
        episode, meter = result.get("episode") or {}, result.get("chunk_costs") or {}
        rows = episode.get("outcomes") or ()
        if (episode.get("stop_reason") != "declared_consequence_complete"
                or not rows or result.get("passed") is not True
                or result.get("released") is not True
                or result.get("field_ready") is not True
                or result.get("paired_context_authenticated") is not True
                or result.get("error_type") or result.get("error")
                or result.get("checkpoint_export_error") or result.get("admission_failure")
                or episode.get("admission_failure") or result.get("cost_lower_bound")
                or result.get("context_costs_complete") is False
                or result.get("unknown_cost_fields")
                or any(row.get("error_type") or row.get("error") for row in rows)
                or rows[-1].get("verification") != "succeeded"
                or rows[-1].get("safe_terminal") is not True
                or any(type(meter.get(k)) is not int or meter[k] <= 0
                       for k in ("actions_attempted", "frames"))
                or runtime.emulator.pressed_buttons):
            return None
        root = Path(output) / "native" / "episode"
        actor_plan, actor_result = doc(root / "plan.json"), doc(root / "result.json")
        claim = doc(root / "sequence" / "task-terminal.json")
        receipts = sorted((root / "sequence").glob("receipt-*.json"))
        source = sha256((Path(output) / "native" / "source.state").read_bytes()).hexdigest()
        from pokemon_red_completion.provenance import canonical_sha256
        if (canonical_sha256(actor_result) != canonical_sha256(episode) or not receipts
                or claim != dict(schema="pokemon.player.task-terminal-claim.v1",
                    task_sha256=plan["sequence_policy"]["task_sha256"],
                    source_sha256=source,
                    behavior_plan_sha256=canonical_sha256(actor_plan),
                    terminal_sha256=result["state_sha256"],
                    last_outcome_sha256=canonical_sha256(rows[-1]),
                    native_verification_required=True, training_eligible=False)
                or doc(receipts[-1]).get("outcome_sha256") != claim["last_outcome_sha256"]
                or rows[0].get("before_state_sha256") != source
                or rows[-1].get("terminal_state_sha256") != result["state_sha256"]
                or any(canonical_sha256(doc(root / f"step-{i:03d}" / "outcome.json"))
                       != canonical_sha256(row)
                       for i, row in enumerate(rows))):
            return None
        emulator = runtime.emulator
        frame, state = emulator.frame_count, emulator.save_state_bytes()
        if sha256(state).hexdigest() != result["state_sha256"]:
            return None
        owned = frozenset(f"pokemon:national:{n:03d}"
                          for n in runtime.reader.read_pokedex_state().owned_species)
        before = frozenset(rows[0]["before"]["owned_species"])
        after = frozenset(rows[-1]["after"]["owned_species"])
        gained = owned - before
        if (owned != after or not before <= owned
                or not gained.intersection(plan["required_species"])
                or emulator.frame_count != frame or emulator.save_state_bytes() != state
                or emulator.pressed_buttons):
            return None
        return dict(schema="pokemon.red.registration-task-handoff.v1",
                    task_sha256=claim["task_sha256"], source_sha256=source,
                    terminal_sha256=result["state_sha256"],
                    task_terminal_sha256=canonical_sha256(claim),
                    new_registrations=sorted(gained), raw_stop_reason=episode["stop_reason"],
                    inputs=0, frames=0, model_queries=0, fit_calls=0,
                    aggregate_budget_reset=False, same_live_guest=True)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None


SAFE_STOP_CONTINUATION_SCHEMA = "pokemon.red.safe-stop-continuation.v1"


def declared_safe_stop_continuation(plan):
    """Explicit DEVELOPMENT opt-in: a qualified safe failure is a setback, not a stop.

    Returns None when absent. Bounds are finite and declared up front; they never
    reset aggregate budgets and never apply to an official acceptance attempt.
    """
    spec = plan.get("safe_stop_continuation")
    if spec is None:
        return None
    if (
        plan.get("partition") != "development"
        or plan.get("official_acceptance", False) is not False
        or type(spec) is not dict
        or set(spec) != {"schema", "reason", "maximum_total", "maximum_repeats", "hold_menus"}
        or spec["schema"] != SAFE_STOP_CONTINUATION_SCHEMA
        or type(spec["reason"]) is not str
        or not spec["reason"].strip()
        or any(type(spec[k]) is not int for k in ("maximum_total", "maximum_repeats", "hold_menus"))
        or not 1 <= spec["maximum_total"] <= 64
        or not 1 <= spec["maximum_repeats"] <= spec["maximum_total"]
        or not 1 <= spec["hold_menus"] <= 16
    ):
        raise ValueError("safe-stop continuation requires a bounded DEVELOPMENT declaration")
    return dict(spec)


def safe_stop_signature(outcome):
    """Coarse repeat key: goal kind plus the observed failure, never a binding."""
    return (
        outcome.get("selected_kind"),
        outcome.get("error_type") or "verification",
        outcome.get("error") or outcome.get("failure_reason"),
    )


def qualified_safe_stop_setback(result, *, runtime, reason):
    """Recognize a goal failure that left a settled, custody-verified field state.

    Only the last outcome may have failed; it must be a typed Exception or failed
    verification, end on the exact retained terminal, and leave released input,
    no battle, field control and the retained party guard intact. Budget, unsafe,
    admission, checkpoint and top-level runner errors stay terminal. Returns the
    failed outcome's signature, or None.
    """
    episode = result.get("episode", {})
    outcomes = episode.get("outcomes") or ()
    if (
        reason not in {"native_execution_error", "verification_failed"}
        or not outcomes
        or result.get("error_type")
        or result.get("checkpoint_export_error")
        or episode.get("admission_failure")
        or not result.get("released")
        or result.get("field_ready") is not True
        or episode.get("stop_reason") not in {"execution_failed", "verification_failed"}
    ):
        return None
    last = outcomes[-1]
    kinds = {kind.value for kind in GoalKind} - {GoalKind.RECOVER_CONTROL.value}
    if (
        last.get("selected_kind") not in kinds
        or last.get("safe_terminal") is not True
        or last.get("terminal_state_sha256") != result.get("state_sha256")
        or last.get("error_type") in CHUNK_BUDGET_ERRORS
        or any(
            outcome.get("error_type") and not qualified_route_setback_receipt(outcome)
            for outcome in outcomes[:-1]
        )
    ):
        return None
    if episode["stop_reason"] == "execution_failed":
        if not last.get("error_type") or last.get("failure_phase") not in {
            "execution",
            "verification",
        }:
            return None
    elif last.get("error_type") or last.get("verification") != "failed":
        return None
    if runtime.emulator.pressed_buttons or not _field_ready(runtime):
        return None
    if sha256(runtime.emulator.save_state_bytes()).hexdigest() != result.get("state_sha256"):
        return None
    raw = runtime.reader.read()
    if raw.battle_state != 0 or not raw.party_hp or not any(raw.party_hp):
        return None
    guard = getattr(runtime.adapter, "party_guard", None)
    if isinstance(guard, RedPlayerPartyGuard):
        if guard.field_carrier is not None:
            return None
        try:
            guard.verify_active_roster_restored()
        except ValueError:
            return None
    return safe_stop_signature(last)


def qualified_movement_stall_setback(result, *, runtime, reason):
    """Recognize the movement-recurrence stop at a settled, custody-verified field state.

    Two equivalent unchanged returns end a chunk with every outcome verified and
    no error. That is circling, not damage: the caller may withhold the circling
    goal kind for a few menus (the same bounded safe-stop hold) so the model
    chooses something else. Returns the coarse repeat signature, or None.
    """
    episode = result.get("episode", {})
    outcomes = episode.get("outcomes") or ()
    if (
        reason != "repeated_movement_without_progress"
        or episode.get("stop_reason") != reason
        or not outcomes
        or result.get("error_type")
        or result.get("checkpoint_export_error")
        or episode.get("admission_failure")
        or not result.get("released")
        or result.get("field_ready") is not True
    ):
        return None
    last = outcomes[-1]
    kinds = {kind.value for kind in GoalKind} - {GoalKind.RECOVER_CONTROL.value}
    if (
        last.get("selected_kind") not in kinds
        or last.get("safe_terminal") is not True
        or last.get("error_type")
        or last.get("verification") != "succeeded"
        or last.get("terminal_state_sha256") != result.get("state_sha256")
        or any(
            outcome.get("error_type") and not qualified_route_setback_receipt(outcome)
            for outcome in outcomes[:-1]
        )
    ):
        return None
    if runtime.emulator.pressed_buttons or not _field_ready(runtime):
        return None
    if sha256(runtime.emulator.save_state_bytes()).hexdigest() != result.get("state_sha256"):
        return None
    raw = runtime.reader.read()
    if raw.battle_state != 0 or not raw.party_hp or not any(raw.party_hp):
        return None
    guard = getattr(runtime.adapter, "party_guard", None)
    if isinstance(guard, RedPlayerPartyGuard):
        if guard.field_carrier is not None:
            return None
        try:
            guard.verify_active_roster_restored()
        except ValueError:
            return None
    return (last.get("selected_kind"), "movement_recurrence", reason)


def declared_league_first_collection_scope(plan):
    """An explicit DEVELOPMENT task scope must survive the actual launch boundary."""
    spec = plan.get("league_first_collection_scope")
    if spec is None:
        return None
    if (
        plan.get("partition") != "development"
        or type(spec) is not dict
        or set(spec) != {"mode", "reason"}
        or spec["mode"] != "defer_eight_badge_collection_until_hof_v1"
        or type(spec["reason"]) is not str
        or not spec["reason"].strip()
    ):
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
    sequence_options = declared_sequence_options(plan)
    declared_resource_safety(plan)
    declared_preparation_context(plan)
    compatibility = declared_goal_model_observation_compatibility(plan)
    declared_readiness_refinement(plan)
    declared_preparation_component(plan)
    venue_model = declared_native_evolution_venue_model(plan)
    compare_yield = declared_evolution_recipient_yield(plan, venue_model)
    from pokemon_red_completion.red_player_configuration import declared_ordinary_preparation_venue_policy
    ordinary_venue_policy = declared_ordinary_preparation_venue_policy(plan)
    declared_input_recording(plan)
    declared_owned_machine_options(plan)
    validate_bird_capture_loan_declaration(plan.get("bird_capture_loan"))
    validate_snorlax_capture_loan_declaration(plan.get("snorlax_capture_loan"))
    declared_league_first_collection_scope(plan)
    from pokemon_red_completion.red_income_preparation import declared_native_owned_stock_income
    declared_native_owned_stock_income(plan)
    bootstrap = plan.get("owned_stock_income_bootstrap", False)
    if type(bootstrap) is not bool or bootstrap and plan.get("partition") != "development":
        raise ValueError("owned-stock income bootstrap requires explicit DEVELOPMENT permission")
    conserved = plan.get("conserved_owned_medicine_income", False)
    if (
        type(conserved) is not bool
        or conserved
        and (plan.get("partition") != "development" or not bootstrap)
    ):
        raise ValueError("conserved income requires explicit DEVELOPMENT owned-stock permission")
    carrier = plan.get("owned_field_carrier_exchange", False)
    if type(carrier) is not bool or (carrier and plan.get("partition") != "development"):
        raise ValueError("owned field-carrier exchange requires explicit DEVELOPMENT boolean")
    recurrence = plan.get("movement_revisit_saturation", False)
    if type(recurrence) is not bool or (recurrence and plan.get("partition") != "development"):
        raise ValueError("movement recurrence requires explicit DEVELOPMENT boolean")
    if "collection_cost_frame_horizon" in plan:
        horizon = plan["collection_cost_frame_horizon"]
        if type(horizon) is not int or horizon < 1 or plan.get("partition") != "development":
            raise ValueError("collection cost quote requires a positive DEVELOPMENT frame horizon")
    if "regional_coverage" in plan and (type(plan["regional_coverage"]) is not bool
            or (plan["regional_coverage"] and plan.get("partition") != "development")):
        raise ValueError("regional coverage mode requires explicit development authority")
    wiring = {
        key: carrier
        if key == "owned_field_carrier_exchange"
        else recurrence
        if key == "movement_revisit_saturation"
        else bootstrap
        if key == "owned_stock_income_bootstrap"
        else conserved
        if key == "conserved_owned_medicine_income"
        else plan.get(key)
        for key in PLAYER_WIRING_FIELDS
    }
    from pokemon_red_completion.red_fishing_survey_history import declared_survey_comparison
    survey = declared_survey_comparison(plan) if "compare_successful_fishing_site_effort" in plan else False
    if compare_yield or survey:
        from pokemon_red_completion.red_collection_campaign_scope import collection_observation_wiring
        wiring.update(collection_observation_wiring(plan))
        if compare_yield:
            wiring["compare_evolution_recipient_yield"] = True
        if survey:
            wiring["compare_successful_fishing_site_effort"] = True
    if venue_model is not None:
        wiring["native_evolution_venue_model"] = dict(plan["native_evolution_venue_model"])
    if ordinary_venue_policy is not None:
        wiring["ordinary_preparation_venue_model"] = dict(plan["ordinary_preparation_venue_model"])
    if compatibility is not None:
        wiring["goal_model_observation_compatibility"] = compatibility
    if "collection_cost_frame_horizon" in plan:
        wiring["collection_cost_frame_horizon"] = plan["collection_cost_frame_horizon"]
    if "regional_coverage" in plan:
        wiring["regional_coverage"] = plan["regional_coverage"]
    for key in ("sequence_policy", "force_resource_safety", "include_preparation_party_context", "retain_story_preparation_opposition", "native_owned_stock_income"):
        if key in plan:
            wiring[key] = plan[key]
    if sequence_options and sequence_options["sequence_policy"].selection_mode != "sample":
        wiring["effective_sequence_selection_mode"] = sequence_options["sequence_policy"].selection_mode
    from pokemon_red_completion.red_observed_component_binding import declared_observed_league_components
    component_recipe=declared_observed_league_components(plan)
    if component_recipe is not None:wiring['observed_league_components']=component_recipe
    if declared_registration_task_continuation(plan):
        wiring["registration_task_continuation"] = plan["registration_task_continuation"]
    return wiring


def native_player_options(plan, runtime, roles, menu, *, refinement=None):
    """Keep strategy learned; settle only already-engaged compulsory control."""
    unsettled = requires_compulsory_settlement(runtime)
    # Keep compulsory entry in the ordinary recorded sequence chain. Its
    # existing inventory supplies only engaged-trainer/wild/control support
    # while unsettled; separate unrecorded prefaces remain forbidden by the
    # native sequence scope guard. No new goal or battle policy is supplied.
    sequence_control = unsettled and plan.get("sequence_policy") is not None
    preface = unsettled and not sequence_control
    refinement = declared_readiness_refinement(plan) if refinement is None else refinement
    return dict(
        greedy_selection=declared_greedy_selection(plan),
        exploration_mix=declared_exploration_mix(plan),
        **({"story_milestone_commitment": True} if declared_story_milestone_commitment(plan) else {}),
        **({"story_kind_commitment": True} if declared_story_kind_commitment(plan) else {}),
        **({"respect_combat_preparation_choice": True} if (plan.get("goal_selection") or {}).get("respect_combat_preparation_choice", False) else {}),
        force_resource_safety=declared_resource_safety(plan),
        include_live_pp_readiness=True,
        allow_collection_restoration=True,
        settle_existing_trainer=preface,
        settle_existing_wild=preface,
        settle_existing_blackout=preface,
        settle_existing_motion=preface,
        resume_branch_refinement_after_settlement=bool(refinement) and preface,
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
    train_selector_authentication=None,
    sequence_horizon=None,
    sequence_window_stride=None,
):
    """One shared native call and durable export, with no state restoration."""
    roles = tuple(m.specimen_ref for m in holder["plan"].roster if m.purpose.value == "combat")
    options = native_player_options(plan, holder["runtime"], roles, menu)
    sequence_options = declared_sequence_options(plan, model)
    if sequence_options and (sequence_horizon is not None or sequence_window_stride is not None):
        raise ValueError("configured sequence policy cannot override its declared collection recipe")
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
    carried_commitment = holder.get("story_kind_commitment_carrier")
    if carried_commitment is not None and not options.get("story_kind_commitment"):
        _record(output / "story-kind-commitment-continuation.json", dict(
            restored=carried_commitment.document(), applied=False,
            reason="story_kind_commitment_not_declared", automatic_fit=False,
        ))
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
            **({"record_milestone_splits": True} if plan.get("record_milestone_splits") is True else {}),
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
            **({"movement_revisit_saturation": plan["movement_revisit_saturation"]}
               if "movement_revisit_saturation" in plan else {}),
            **({"collection_cost_frame_horizon": plan["collection_cost_frame_horizon"]}
               if "collection_cost_frame_horizon" in plan else {}),
            **options,
            **sequence_options,
            **({"train_selector_authentication": train_selector_authentication}
               if train_selector_authentication is not None else {}),
            **({"sequence_horizon": sequence_horizon} if sequence_horizon is not None else {}),
            **({"sequence_window_stride": sequence_window_stride}
               if sequence_window_stride is not None else {}),
            **(
                {"story_kind_commitment_carrier": _story_kind_commitment_carrier(holder)}
                if options.get("story_kind_commitment")
                else {}
            ),
        )
        admission = result["episode"].get("admission_failure")
        if admission:
            result.update(
                passed=False,
                error_type=admission["error_type"],
                error=admission["error"],
                admission_failure=admission,
                error_chain=admission.get("error_chain"),
            )
        else:
            result["passed"] = True
    except BaseException as error:
        result.update(
            error_type=type(error).__name__, error=str(error), error_chain=_exception_chain(error)
        )
    finally:
        _write(output / "terminal.state", emulator.save_state_bytes())
        cost_path = output / "native/native-costs.json"
        meter = doc(cost_path) if cost_path.exists() else {}
        outcomes = result.get("episode", {}).get("outcomes", [])
        if not outcomes:
            outcomes = [
                doc(p) for p in sorted((output / "native/episode").glob("step-*/outcome.json"))
            ]
        if not result.get("episode") and outcomes:
            # A BaseException can leave fully closed native rows while the
            # episode call never returns. Retain them in the aggregate without
            # inventing a completed run or suppressing the original error chain.
            result["episode"] = dict(
                schema="pokemon.red.interrupted-closed-outcome-prefix.v1",
                stop_reason="interrupted_closed_outcome_prefix",
                executed_decisions=len(outcomes),
                outcomes=outcomes,
                closed_outcome_prefix_reconstructed=True,
                complete_episode=False,
                raw_exception_retained=True,
                automatic_fit=False,
            )
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
            result.get("error")
            if result.get("error_type")
            else outcomes[-1].get("error")
            if outcomes
            else None
        )
        primary_error_chain = result.get("error_chain") or (
            outcomes[-1].get("error_chain") if outcomes else None
        )
        if primary_error_chain is not None:
            result["error_chain"] = primary_error_chain
        checkpoint_type, checkpoint_message = checkpoint_error_for_export(
            error_type, error_message, primary_error_chain
        )
        checkpoint_kwargs = (
            {"checkpoint_error": checkpoint_message}
            if checkpoint_type == "ControllerFrameBudgetError"
            else {}
        )
        exported = None
        try:
            history = holder["observe_history"](
                checkpoint_error_type=checkpoint_type,
                **checkpoint_kwargs,
            )
            censored = holder.get("censored_battle_checkpoint")
            preparation_story_history = holder.get("preparation_story_history")
            if preparation_story_history is not None:
                preparation_story_history.refresh(holder)
            exported = capture_player_continuation(
                holder["runtime"],
                **({"preparation_story_history": preparation_story_history}
                   if preparation_story_history is not None else {}),
                preparation=holder["plan"],
                battle=None if censored is not None else history,
                spent=spent,
                search_memory=memory,
                **(
                    {"story_kind_commitment_carrier": _story_kind_commitment_carrier(holder)}
                    if options.get("story_kind_commitment")
                    else {}
                ),
            )
            _record(output / "CONTEXT.json", exported)
        except Exception as export_error:
            # Export diagnostics must not replace a native failure or erase its
            # charged tail. An unpaired terminal remains evidence, never a
            # fabricated continuation or permission to renew the live player.
            exported = None
            export_failure = dict(
                error_type=type(export_error).__name__,
                error=str(export_error),
                error_chain=_exception_chain(export_error),
                primary_error_type=error_type,
                primary_error=error_message,
                primary_error_chain=primary_error_chain,
                resume_authorized=False,
            )
            _record(output / "CHECKPOINT-EXPORT-ERROR.json", export_failure)
            result.update(
                passed=False,
                checkpoint_export_error=export_failure,
                error_type=error_type or type(export_error).__name__,
                error=error_message if error_type else str(export_error),
                error_chain=primary_error_chain if error_type else _exception_chain(export_error),
            )
        censored = holder.get("censored_battle_checkpoint")
        raw = holder["runtime"].reader.read()
        result.update(
            **player_lifecycle_fields(
                scope="live_chunk",
                released=not emulator.pressed_buttons,
                guest_backend_closed=(emulator._backend is None)
                if hasattr(emulator, "_backend")
                else None,
            ),
            released=not emulator.pressed_buttons,
            state_sha256=c.digest(output / "terminal.state"),
            context_sha256=c.digest(output / "CONTEXT.json") if exported is not None else None,
            field_ready=_field_ready(holder["runtime"]),
            spent=spent,
            cash=raw.player_money,
            map_id=raw.map_id,
            at=(raw.player_y, raw.player_x),
            levels=raw.party_levels,
            completed=(
                exported["lesson"]["completed_objectives"]
                if exported is not None
                else outcomes[-1].get("after", {}).get("completed_objectives", [])
                if outcomes
                else []
            ),
            native_facts=native_checkpoint_facts(holder["runtime"]),
            censored_battle_checkpoint=censored,
            chunk_costs=meter,
        )
    saved_export = doc(output / "CONTEXT.json") if exported is not None else None
    result["paired_context_authenticated"] = _paired_context_authenticated(
        exported, saved_export, result, spent,
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
    if (
        proof.get("reason") != "step_acknowledgement_exhausted"
        or not isinstance(chain, list)
        or len(chain) != 1
        or not isinstance(chain[0], dict)
        or chain[0].get("reason_code") != proof["reason"]
        or row.get("verification") is not None
        or row.get("safe_terminal") is not True
        or not isinstance(cost, dict)
        or proof.get("cost") != cost
        or not isinstance(walk, dict)
        or not isinstance(route, dict)
    ):
        return False
    if (
        any(
            type(cost.get(k)) is not int
            for k in ("actions", "completed_actions", "frames", "cash_spent")
        )
        or cost["actions"] <= 0
        or cost["frames"] <= 0
        or cost["completed_actions"] != cost["actions"]
        or cost["cash_spent"] != 0
    ):
        return False
    keys = (
        "player_lesson",
        "owned_species",
        "specimen_counts",
        "completed_objectives",
        "bag_items",
        "coins",
        "cash",
    )
    if (
        not isinstance(before, dict)
        or not isinstance(after, dict)
        or any(k not in before or k not in after or before[k] != after[k] for k in keys)
    ):
        return False
    for facts in (before, after):
        if (
            facts.get("party_guard_verified") is not True
            or facts.get("input_ready") is not True
            or facts.get("buttons_released") is not True
            or facts.get("battle_state") != 0
        ):
            return False
    return (
        after.get("route_boundary") == route
        and route
        == dict(
            map_id=walk.get("source_map"),
            at=walk.get("source_at"),
            ready=True,
            interruption=None,
            mode="land",
        )
        and walk.get("source_map") == walk.get("expected_map")
        and walk.get("action") in {"up", "down", "left", "right"}
    )


def qualified_restoration_budget_censor(result, *, limits=None):
    """Recognize one paid, safely exported finite terminal; never goal success."""
    if type(limits) is not NativePlayerLimits:
        return False
    episode, meter = result.get("episode") or {}, result.get("chunk_costs") or {}
    rows = episode.get("outcomes") or ()
    if (
        episode.get("stop_reason") != "restoration_budget"
        or not rows
        or result.get("error_type")
        or result.get("error")
        or result.get("checkpoint_export_error")
        or episode.get("admission_failure")
        or result.get("admission_failure")
        or result.get("released") is not True
        or result.get("field_ready") is not True
        or result.get("paired_context_authenticated") is not True
        or not checkpoint_quiescent(result)
        or result.get("cost_lower_bound") is True
        or result.get("context_costs_complete") is False
        or result.get("unknown_cost_fields")
    ):
        return False
    for key in ("state_sha256", "context_sha256"):
        value = result.get(key)
        if (
            type(value) is not str
            or len(value) != 64
            or any(c not in "0123456789abcdef" for c in value)
        ):
            return False
    row = rows[-1]
    message = "native player restoration budget exhausted"
    chain = [dict(error_type="RestorationBudgetExhausted", error=message)]
    if (
        row.get("error_type") != "RestorationBudgetExhausted"
        or row.get("error") != message
        or row.get("error_chain") != chain
        or result.get("error_chain") not in (None, chain)
        or row.get("failure_phase") != "execution"
        or row.get("failure_reason") != "execution_budget_exhausted"
        or row.get("verification") != "failed"
        or row.get("ordinary_setback") is not False
        or row.get("safe_terminal") is not True
        or row.get("terminal_state_sha256") != result["state_sha256"]
        or any(r.get("error_type") or r.get("error") or r.get("error_chain") for r in rows[:-1])
        or any(
            r.get("verification") == "failed" and r.get("ordinary_setback") is not True
            for r in rows[:-1]
        )
    ):
        return False
    integer_costs = (
        "actions_attempted",
        "actions_completed",
        "frames",
        "goal_attempts",
        "restore_attempts",
        "nested_restore_attempts",
        "training_healing_attempts",
        "observed_cash_debits",
        "observed_cash_rewards",
        "observed_cash_changes",
        "control_recovery_cash_debits",
    )
    if (
        meter.get("schema") != "pokemon.red.native-player-costs.v1"
        or meter.get("automatic_fit") is not False
        or any(type(meter.get(k)) is not int or meter[k] < 0 for k in integer_costs)
        or type(meter.get("seconds")) not in (int, float)
        or not 0 <= meter["seconds"] < float("inf")
        or meter.get("buttons_released") is not True
        or meter["restore_attempts"] != limits.heals
        or (limits.cash_debits is not None and meter["observed_cash_debits"] > limits.cash_debits)
        or meter["actions_completed"] != meter["actions_attempted"]
        or meter["actions_attempted"] > limits.actions
        or meter["frames"] > limits.frames
        or meter["seconds"] > limits.seconds
        or meter["goal_attempts"] > limits.decisions
        or meter["goal_attempts"] != episode.get("executed_decisions")
        or meter["goal_attempts"] != len(rows)
    ):
        return False
    try:
        spent = continuation_costs(result.get("spent"))
    except (TypeError, ValueError):
        return False
    for key, charged in {
        "decisions": "goal_attempts",
        "actions": "actions_attempted",
        "frames": "frames",
        "heals": "restore_attempts",
        "cash_debits": "observed_cash_debits",
    }.items():
        if type(spent.get(key)) is not int or spent[key] < meter[charged]:
            return False
    if type(spent.get("seconds")) not in (int, float) or not meter["seconds"] <= spent[
        "seconds"
    ] < float("inf"):
        return False
    before, after, cost = row.get("before"), row.get("after"), row.get("observed_cost")
    if not all(type(v) is dict for v in (before, after, cost)):
        return False
    snapshots = {
        "actions": "actions_attempted",
        "completed_actions": "actions_completed",
        "frames": "frames",
        "restoration_attempts": "restore_attempts",
        "nested_restoration_attempts": "nested_restore_attempts",
        "training_healing_attempts": "training_healing_attempts",
    }
    for key, metered in snapshots.items():
        if (
            type(before.get(key)) is not int
            or type(after.get(key)) is not int
            or not 0 <= before[key] <= after[key]
            or after[key] != meter[metered]
        ):
            return False
    for key in ("actions", "completed_actions", "frames"):
        if type(cost.get(key)) is not int or cost[key] != after[key] - before[key]:
            return False
    return not (
        type(before.get("cash")) is not int
        or type(after.get("cash")) is not int
        or type(cost.get("cash_spent")) is not int
        or cost["cash_spent"] != max(0, before["cash"] - after["cash"])
        or after.get("battle_state") != 0
        or type(after.get("battle_state")) is not int
        or after.get("input_ready") is not True
        or after.get("buttons_released") is not True
        or after.get("party_guard_verified") is not True
    )


def qualified_zero_input_wall_budget_censor(result, *, limits=None):
    """Report an unchanged field boundary at the real wall cutoff,not a win.

    The failed attempt,error and costs stay in the raw result. This reporting
    certificate does not authenticate a paired continuation or renew a budget.
    """
    from math import isfinite

    if type(limits) is not NativePlayerLimits:
        return False
    episode,meter=result.get("episode")or{},result.get("chunk_costs")or{}
    rows=episode.get("outcomes")or()
    if (episode.get("stop_reason")!="execution_failed" or not rows
        or any(result.get(k)for k in("error_type","error","checkpoint_export_error","admission_failure","unknown_cost_fields"))
        or episode.get("admission_failure") or result.get("released")is not True
        or result.get("field_ready")is not True or not checkpoint_quiescent(result)
        or result.get("cost_lower_bound")is True or result.get("context_costs_complete")is False):
        return False
    row=rows[-1];message="controller reached its hard monotonic wall-time admission deadline"
    chain=[dict(error_type="ControllerWallTimeBudgetExhausted",error=message)]
    if (row.get("error_type")!="ControllerWallTimeBudgetExhausted" or row.get("error")!=message
        or row.get("error_chain")!=chain or result.get("error_chain")not in(None,chain)
        or row.get("failure_phase")!="execution" or row.get("verification")is not None
        or row.get("ordinary_setback")is not False or row.get("safe_terminal")is not True
        or row.get("before_state_sha256")!=row.get("terminal_state_sha256")
        or row.get("terminal_state_sha256")!=result.get("state_sha256")
        or any(r.get("error_type")or r.get("error")or r.get("error_chain")for r in rows[:-1])
        or any(r.get("verification")=="failed"and r.get("ordinary_setback")is not True for r in rows[:-1])):
        return False
    for key in("state_sha256","context_sha256"):
        h=result.get(key)
        if type(h)is not str or len(h)!=64 or any(c not in "0123456789abcdef"for c in h):return False
    before,after,cost=row.get("before"),row.get("after"),row.get("observed_cost")
    if not all(type(x)is dict for x in(before,after,cost)):return False
    if cost!={"actions":1,"completed_actions":0,"frames":0,"cash_spent":0} or any(type(v)is not int for v in cost.values()):return False
    if (canonical_sha256({k:v for k,v in before.items()if k!="actions"})
        !=canonical_sha256({k:v for k,v in after.items()if k!="actions"})):
        return False
    for key in("actions","completed_actions","frames","restoration_attempts","nested_restoration_attempts","training_healing_attempts","cash","battle_state"):
        if type(before.get(key))is not int or type(after.get(key))is not int or before[key]<0:return False
    if (after["actions"]!=before["actions"]+1 or after["battle_state"]!=0
        or after.get("input_ready")is not True or after.get("buttons_released")is not True
        or before.get("input_ready")is not True or before.get("buttons_released")is not True):return False
    integers=("actions_attempted","actions_completed","frames","goal_attempts","restore_attempts",
              "nested_restore_attempts","training_healing_attempts","observed_cash_debits","observed_cash_rewards","observed_cash_changes","control_recovery_cash_debits")
    if (meter.get("schema")!="pokemon.red.native-player-costs.v1" or meter.get("automatic_fit")is not False
        or meter.get("buttons_released")is not True
        or any(type(meter.get(k))is not int or meter[k]<0 for k in integers)
        or type(meter.get("seconds"))not in(int,float) or not isfinite(meter["seconds"])
        or meter["seconds"]<limits.seconds
        or meter["actions_attempted"]!=after["actions"] or meter["actions_completed"]!=after["completed_actions"]
        or meter["actions_attempted"]!=meter["actions_completed"]+1 or meter["frames"]!=after["frames"]
        or meter["goal_attempts"]!=len(rows) or meter["goal_attempts"]!=episode.get("executed_decisions")
        or meter["actions_attempted"]>limits.actions or meter["frames"]>limits.frames or len(rows)>limits.decisions
        or meter["restore_attempts"]>limits.heals
        or (limits.cash_debits is not None and meter["observed_cash_debits"]>limits.cash_debits)):
        return False
    for k,m in(("restoration_attempts","restore_attempts"),("nested_restoration_attempts","nested_restore_attempts"),("training_healing_attempts","training_healing_attempts")):
        if after[k]!=meter[m]:return False
    try:spent=continuation_costs(result.get("spent"))
    except(TypeError,ValueError):return False
    return all(spent[k]>=meter[m]for k,m in(("decisions","goal_attempts"),("actions","actions_attempted"),("frames","frames"),("heals","restore_attempts"),("cash_debits","observed_cash_debits"),("seconds","seconds")))


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
    root_error = bool(
        result.get("error_type") or result.get("error") or result.get("checkpoint_export_error")
    )
    admission = bool(episode.get("admission_failure") or result.get("admission_failure"))
    setbacks = sum(row.get("ordinary_setback") is True for row in outcomes)
    verification_failures = sum(
        row.get("verification") == "failed" and row.get("ordinary_setback") is not True
        for row in outcomes
    )
    restoration_censors = int(qualified_restoration_budget_censor(result, limits=limits))
    zero_input_wall_censors = int(qualified_zero_input_wall_budget_censor(result, limits=limits))
    budget_censors = restoration_censors + zero_input_wall_censors
    if admission:
        status = "admission_error"
    elif root_error or errors > recovered_routes + budget_censors:
        status = "execution_error"
    elif verification_failures > budget_censors:
        status = "verification_failure"
    elif zero_input_wall_censors:
        status = "zero_input_wall_budget_censor"
    elif restoration_censors:
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
        schema="pokemon.red.native-result-status.v1",
        scope="current_chunk",
        status=status,
        wrapper_returned=result.get("passed") is True,
        native_outcome_error_count=errors,
        wrapper_or_export_error=root_error,
        recovered_route_error_count=recovered_routes,
        unrecovered_native_error_count=errors - recovered_routes,
        qualified_budget_censor_count=budget_censors,
        qualified_zero_input_wall_budget_censor_count=zero_input_wall_censors,
        finite_censor=bool(budget_censors),
        effective_unrecovered_native_error_count=errors - recovered_routes - budget_censors,
        effective_nonordinary_verification_failures=verification_failures - restoration_censors,
        admission_error=admission,
        ordinary_setbacks=setbacks,
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
                kind in CHUNK_BUDGET_ERRORS
                and (
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


def _qualified_retained_budget_handoff(result, *, runtime, inspect_bindings):
    """Authenticate the exact retained preface OR single compulsory outcome.

    A typed row is still a raw failed in-battle outcome. Qualification only
    permits its unique unchanged compulsory successor; it grants no new budget.
    """
    error_type = "RetainedTrainerBattleDecisionBudgetReached"
    message = "retained trainer battle reached its bounded decision limit"
    episode = result.get("episode") or {}
    outcomes = episode.get("outcomes") or ()
    row = None
    if outcomes:
        if (len(outcomes) != 1 or type(outcomes[0]) is not dict
                or result.get("error_type") or result.get("error")
                or result.get("checkpoint_export_error")
                or episode.get("admission_failure") or result.get("admission_failure")
                or episode.get("stop_reason") != "execution_failed"
                or result.get("passed") is not True
                or result.get("paired_context_authenticated") is not True
                or result.get("released") is not True
                or result.get("cost_lower_bound") is True
                or result.get("context_costs_complete") is False
                or result.get("unknown_cost_fields")):
            return None
        row = outcomes[0]
        if (row.get("selected_kind") != GoalKind.RECOVER_CONTROL.value
                or row.get("failure_phase") != "execution"
                or row.get("verification") is not None
                or row.get("ordinary_setback") is True
                or row.get("terminal_state_sha256") != result.get("state_sha256")):
            return None
        for name, value in (("source", row.get("before_state_sha256")),
                            ("context", result.get("context_sha256"))):
            if (type(value) is not str or len(value) != 64
                    or any(c not in "0123456789abcdef" for c in value)):
                return None
        if row["before_state_sha256"] == result.get("state_sha256"):
            return None
        cost, meter = row.get("observed_cost"), result.get("chunk_costs")
        before_facts, after_facts = row.get("before"), row.get("after")
        if not all(type(value) is dict for value in (cost, meter, before_facts, after_facts)):
            return None
        for key, delta_key, meter_key in (("actions", "actions", "actions_attempted"),
                                         ("frames", "frames", "frames"),
                                         ("completed_actions", "completed_actions", "actions_completed")):
            if (type(cost.get(key)) is not int or cost[key] <= 0
                    or type(before_facts.get(delta_key)) is not int
                    or type(after_facts.get(delta_key)) is not int
                    or after_facts[delta_key] - before_facts[delta_key] != cost[key]
                    or type(meter.get(meter_key)) is not int
                    or meter[meter_key] != cost[key]):
                return None
        if cost["completed_actions"] != cost["actions"]:
            return None
        # The new row shape must not hide an unrelated cause in either chain.
        for chain in (row.get("error_chain"), result.get("error_chain")):
            if (not isinstance(chain, (list, tuple)) or not chain
                    or any(type(item) is not dict or item.get("error_type") != error_type
                           or item.get("reason_code") != "retained_trainer_battle_decision_budget"
                           for item in chain)):
                return None
    error = result if row is None else row
    if (
        error.get("error_type") != error_type or error.get("error") != message
        or not any(
            isinstance(item, dict) and item.get("error_type") == error_type
            and item.get("reason_code") == "retained_trainer_battle_decision_budget"
            for item in (error.get("error_chain") or ())
        )
        or not result.get("released") or result.get("field_ready") is not False
        or runtime.emulator.pressed_buttons or _field_ready(runtime)
    ):
        return None
    raw = runtime.reader.read()
    if raw.battle_state != 2 or not raw.party_hp or not any(raw.party_hp):
        return None
    before, frames = runtime.emulator.save_state_bytes(), runtime.emulator.frame_count
    if sha256(before).hexdigest() != result.get("state_sha256"):
        return None
    bindings = inspect_bindings()
    if (runtime.emulator.save_state_bytes() != before or runtime.emulator.frame_count != frames
            or runtime.emulator.pressed_buttons):
        raise ValueError("native control handoff inspection changed state")
    expected = "pokemon.red:retained-engagement:" + result["state_sha256"]
    if (
        type(bindings) is not GoalBindingSet or len(bindings.bindings) != 1
        or bindings.bindings[0].kind is not GoalKind.RECOVER_CONTROL
        or bindings.bindings[0].binding_ref != expected
    ):
        return None
    return dict(
        schema="pokemon.red.qualified-native-control-handoff.v1",
        state_sha256=result["state_sha256"], binding_ref=expected, qualified=True,
        inputs=0, frames=0, model_queries=0, failed_transport_preserved=True,
        strategic_substitution=False, censored_story_battle=True,
        compulsory_preface_censor=row is None, retained_outcome_censor=row is not None,
        finite_in_battle_censor=True, original_terminal_safe=False,
        local_decision_limit_unchanged=True, aggregate_budget_reset=False,
        **({"source_state_sha256": row["before_state_sha256"],
            "context_sha256": result["context_sha256"],
            "observed_actions": row["observed_cost"]["actions"],
            "observed_frames": row["observed_cost"]["frames"],
            "raw_error_type": error_type,
            "raw_reason_code": "retained_trainer_battle_decision_budget"} if row is not None else {}),
    )


PAUSED_CAPTURE_EXHAUSTIONS = frozenset({
    "throw budget exhausted; live encounter retained without Run",
    "throw budget exhausted at catcher faint",
})


def paused_capture_outcome(outcome):
    """A one-off catch that stopped inside its live battle with a known, resumable reason.

    Either the declared throws are spent, or status preparation found nobody
    above half health to act as catcher. Both leave the encounter and its
    journal intact for the retained-capture executor; nothing else qualifies.
    """
    return outcome.get("selected_kind") == GoalKind.ACQUIRE_SPECIES.value and (
        (
            outcome.get("error_type") == "OneOffCapturePaused"
            and outcome.get("error") in PAUSED_CAPTURE_EXHAUSTIONS
        )
        or (
            outcome.get("error_type") == "RedCaptureStatusError"
            and outcome.get("error") == "capture preparation has no healthy catcher"
        )
    )


def qualified_league_income_budget(result, parent):
    """Verify the spent rematch segment against its frozen actor's battle endpoint."""
    if parent is None or result.get("paired_context_authenticated") is not True:
        return False
    outcomes = result.get("episode", {}).get("outcomes") or ()
    if not outcomes:
        return False
    last = outcomes[-1]
    if last.get("selected_kind") != "resupply" or last.get("error_type") != "RedLeagueFundingExecutionError":
        return False
    chain = last.get("error_chain") or ()
    if len(chain) != 3 or not all(isinstance(row, dict) for row in chain):
        return False
    stage = last.get("error", "").removesuffix(" failed")
    if (
        stage not in {"defeat_lorelei", "defeat_bruno", "defeat_agatha", "defeat_lance", "defeat_champion"}
        or chain[0].get("error_type") != "RedLeagueFundingExecutionError"
        or chain[0].get("reason_code") != stage + " failed"
        or chain[1].get("error_type") != "StoryBattleDecisionBudgetReached"
        or chain[1].get("reason_code") != "story_battle_decision_budget"
        or chain[2].get("error_type") != "LoreleiStoryBattleStopped"
        or (last.get("after") or {}).get("battle_state") != 2
        or "enter_hall_of_fame" not in (last.get("before") or {}).get("completed_objectives", ())
    ):
        return False
    state = result.get("state_sha256")
    if last.get("terminal_state_sha256") != state or not state:
        return False
    parent = Path(parent)
    matches = []
    for path in parent.glob(f"income-{stage}-offer-*/battle-*/endpoint.json"):
        endpoint = json.loads(path.read_bytes())
        if endpoint.get("final_state_sha256") != state:
            continue
        battle = json.loads(path.with_name("outcome.json").read_bytes())
        matches.append(
            endpoint.get("actor_returned_win") is False
            and endpoint.get("outer_goal_verification_required") is True
            and sha256(path.with_name("final.state").read_bytes()).hexdigest() == state
            and canonical_sha256(battle) == endpoint.get("outcome_sha256")
            and battle.get("battle_won") is False
            and battle.get("stop_reason") == "decision_budget"
            and battle.get("final_battle_state") == 2
            and battle.get("decision_count") == len(battle.get("decisions", ())) > 0
        )
    return matches == [True]


def qualified_native_control_handoff(result, *, runtime, inspect_bindings, retained_parent=None, catcher_plan=None):
    """Recognize one retained native introduction, never waive an unknown error.

    The trusted live inventory must contain one exact retained recovery and no
    alternative. Interrupted trainer/static transport or declared evolution-loan
    settlement stays failed, with all error/costs retained. No new encounter or
    strategic goal is selected.
    """
    episode = result.get("episode", {})
    outcomes = episode.get("outcomes", ())
    retained = _qualified_retained_budget_handoff(
        result, runtime=runtime, inspect_bindings=inspect_bindings
    )
    if retained is not None:
        return retained
    if not outcomes:
        return None
    last = outcomes[-1]
    from pokemon_red_completion.red_capture_switch_handoff import catcher_switch_failure, development_recovery
    from pokemon_red_completion.red_player_configuration import _failed_wild_acquisition_faint
    known_catcher = (catcher_switch_failure(last) and result.get("paired_context_authenticated") is True
                     and development_recovery(catcher_plan)
                     and _failed_wild_acquisition_faint(runtime.reader, result, last))
    known_trainer_error = last.get("error_type") == "RouteExecutionError" and last.get("error") in {
        "field dialogue lacks a newly poisoned member faint",
        "field dialogue is not an admitted native faint",
        "Gen I route cannot dismiss 'trainer_engagement'",
    }
    known_loan_wild_error = (
        last.get("selected_kind") == GoalKind.EVOLVE_SPECIES.value
        and last.get("error_type") == "RedGoalContextError"
        and last.get("error") == "PC loan settlement requires settled field control"
    )
    known_static_settlement = (
        last.get("selected_kind") == GoalKind.ACQUIRE_SPECIES.value
        and last.get("error_type") == "RouteExecutionError"
        and last.get("error") == "selected static transport requires ordinary player settlement"
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
    # A one-off catch that spent its declared throws pauses inside the live
    # wild battle. Its own retained-capture executor (remaining carried balls,
    # then the exact consumed loss) is the only admissible successor.
    known_capture_pause = paused_capture_outcome(last)
    known_league_income_budget = qualified_league_income_budget(result, retained_parent)
    if (
        result.get("error_type")
        or not result.get("released")
        or result.get("field_ready") is not False
        or episode.get("stop_reason") != "execution_failed"
        or last.get("selected_kind") not in {kind.value for kind in GoalKind}
        or last.get("failure_phase") != "execution"
        or (
            last.get("safe_terminal") is not True
            and not (
                (known_loan_wild_error or known_story_decision_budget or known_capture_pause or known_catcher)
                and last.get("safe_terminal") is False
            )
        )
        or not (
            known_trainer_error
            or known_loan_wild_error
            or known_static_settlement
            or known_story_decision_budget
            or known_league_income_budget
            or known_capture_pause
            or known_catcher
        )
        or last.get("terminal_state_sha256") != result.get("state_sha256")
        or any(
            outcome.get("error_type")
            and not (known_capture_pause and qualified_route_setback_receipt(outcome))
            for outcome in outcomes[:-1]
        )
        or runtime.emulator.pressed_buttons
        or _field_ready(runtime)
    ):
        return None
    before, frames = runtime.emulator.save_state_bytes(), runtime.emulator.frame_count
    if sha256(before).hexdigest() != result["state_sha256"]:
        return None
    if known_capture_pause:
        raw = runtime.reader.read()
        if raw.battle_state != 1 or not raw.party_hp or not any(raw.party_hp):
            return None
    if known_static_settlement:
        from pokemon_red_completion.red_player_party_guard import RedPlayerPartyGuard

        guard = getattr(runtime.adapter, "party_guard", None)
        raw = runtime.reader.read()
        if (
            not isinstance(guard, RedPlayerPartyGuard)
            or raw.battle_state != 0
            or not raw.party_hp
            or not any(raw.party_hp)
            or not runtime.reader.read_bottom_dialogue_box_visible()
            or runtime.reader.read_overworld_start_menu_visible()
        ):
            return None
        guard.verify_active_roster_restored()
    if known_loan_wild_error:
        from pokemon_red_completion.red_player_party_guard import RedPlayerPartyGuard

        guard = getattr(runtime.adapter, "party_guard", None)
        if (
            not isinstance(guard, RedPlayerPartyGuard)
            or len(guard.loanable_refs) != 1
            or runtime.reader.read().battle_state not in (0, 1)
        ):
            return None
        guard.verify()
        if set(guard.refs) - set(guard.reader.preparation_specimen_refs()) != set(
            guard.loanable_refs
        ):
            return None
    bindings = inspect_bindings()
    if runtime.emulator.save_state_bytes() != before or runtime.emulator.frame_count != frames:
        raise ValueError("native control handoff inspection changed state")
    expected_ref = (
        "pokemon.red:interrupted-wild:"
        if known_catcher or known_loan_wild_error and runtime.reader.read().battle_state == 1
        else "pokemon.red:retained-motion:"
        if known_loan_wild_error
        else "pokemon.red:retained-capture:"
        if known_capture_pause
        else "pokemon.red:retained-engagement:"
    ) + result["state_sha256"]
    if (
        type(bindings) is not GoalBindingSet
        or len(bindings.bindings) != 1
        or bindings.bindings[0].kind is not GoalKind.RECOVER_CONTROL
        or bindings.bindings[0].binding_ref != expected_ref
    ):
        return None
    return dict(
        schema="pokemon.red.qualified-native-control-handoff.v1",
        state_sha256=result["state_sha256"],
        binding_ref=bindings.bindings[0].binding_ref,
        qualified=True,
        inputs=0,
        frames=0,
        model_queries=0,
        failed_transport_preserved=True,
        strategic_substitution=False,
        **({"ordinary_capture_switch_faint": True, "original_failure_reason": "native_execution_error",
            "failed_outcome_sha256": canonical_sha256(last), "original_terminal_safe": last["safe_terminal"],
            "compulsory_settlement_required": True} if known_catcher else {}),
        **({"retained_league_income_budget": True, "funding_attempt_failed": True,
            "local_decision_limit_unchanged": True, "aggregate_budget_reset": False}
           if known_league_income_budget else {}),
        **(
            {"retained_declared_loan": True,
             "wild_exit_before_pc_return": runtime.reader.read().battle_state == 1,
             "field_faint_before_pc_return": runtime.reader.read().battle_state == 0}
            if known_loan_wild_error
            else {}
        ),
        **(
            {"original_terminal_safe": False, "compulsory_settlement_required": True}
            if known_loan_wild_error and last.get("safe_terminal") is False
            else {}
        ),
        **(
            {"retained_native_introduction": True, "retained_roster_restored": True}
            if known_static_settlement
            else {}
        ),
        **(
            {"retained_capture_pause": True, "original_terminal_safe": False,
             "compulsory_settlement_required": True}
            if known_capture_pause
            else {}
        ),
        **(
            {
                "censored_story_battle": True,
                "original_terminal_safe": False,
                "local_decision_limit_unchanged": True,
                "aggregate_budget_reset": False,
            }
            if known_story_decision_budget
            else {}
        ),
    )


AUTOMATIC_CONTINUATIONS = {
    "automatic_budget_recovery",
    "automatic_chunk_renewal",
    "automatic_control_recovery",
    "automatic_registration_task_renewal",
}


def _qualified_zero_input_carrier_abort_handoff(
    result, *, plan, runtime, inspect_bindings, source_context_bytes,
    exported_context_bytes, expected_source_context_sha256,
):
    """Authenticate one metadata abort; the generic physical-progress guard stays."""
    from math import isfinite, isclose
    try:
        if not declared_automatic_renewal(plan):
            return None
        before_context = json.loads(source_context_bytes)
        after_context = json.loads(exported_context_bytes)
        old_sha = sha256(source_context_bytes).hexdigest()
        new_sha = sha256(exported_context_bytes).hexdigest()
        episode = result["episode"]
        rows = episode["outcomes"]
        if len(rows) != 1:
            return None
        row, meter = rows[0], result["chunk_costs"]
        evidence = row["evidence"]
        state = runtime.emulator.save_state_bytes()
        state_sha = sha256(state).hexdigest()
        if (old_sha != expected_source_context_sha256 or old_sha == new_sha
                or result.get("passed") is not True or result.get("released") is not True
                or result.get("field_ready") is not True or result.get("paired_context_authenticated") is not True
                or episode.get("stop_reason") != "no_state_progress" or episode.get("admission_failure")
                or any(result.get(k) for k in ("error", "error_type", "error_chain", "context_error", "checkpoint_export_error"))
                or any(row.get(k) for k in ("error", "error_type", "error_chain", "failure_phase"))
                or row.get("selected_kind") != GoalKind.RECOVER_CONTROL.value
                or row.get("verification") != "succeeded" or row.get("safe_terminal") is not True
                or row.get("ordinary_setback") is not False
                or evidence.get("support") != "authenticated_zero_input_field_carrier_return_abort"
                or evidence.get("model_queries") != 0 or type(evidence.get("model_queries")) is not int
                or evidence.get("original_source_pending_preserved") is not True
                or evidence.get("retained_active_field_carrier") is not True
                or evidence.get("original_roster_restored") is not False
                or evidence.get("objective_completed") is not False
                or evidence.get("no_controller_input") is not True
                or evidence.get("historical_costs_retained") is not True
                or result.get("state_sha256") != state_sha or result.get("context_sha256") != new_sha
                or before_context.get("state_sha256") != state_sha or after_context.get("state_sha256") != state_sha
                or row.get("before_state_sha256") != state_sha or row.get("terminal_state_sha256") != state_sha
                or evidence.get("source_sha256") != state_sha or evidence.get("terminal_sha256") != state_sha
                or any(c.get("grants_new_budget") is not False or c.get("fit_allowed") is not False
                       for c in (before_context, after_context))
                or any(before_context.get(k) != after_context.get(k) for k in ("schema", "lesson", "cash", "bag", "battle", "search_memory"))
                or result.get("spent") != after_context.get("spent")
                or row.get("observed_cost") != dict(actions=0, completed_actions=0, frames=0, cash_spent=0)
                or not _field_ready(runtime) or runtime.emulator.pressed_buttons):
            return None
        for key in ("actions", "completed_actions", "frames", "cash"):
            if (type(row["before"].get(key)) is not int or row["before"][key] < 0
                    or row["after"].get(key) != row["before"][key]):
                return None
        if any(type(row["observed_cost"].get(k)) is not int for k in ("actions", "completed_actions", "frames", "cash_spent")):
            return None
        old_cost = continuation_costs(before_context["spent"])
        new_cost = continuation_costs(after_context["spent"])
        for key in ("actions", "frames", "heals", "cash_debits"):
            if new_cost[key] != old_cost[key]:
                return None
        seconds = meter.get("seconds")
        if (type(seconds) not in (int, float) or not isfinite(seconds) or seconds < 0
                or new_cost["decisions"] != old_cost["decisions"] + 1
                or not isclose(new_cost["seconds"] - old_cost["seconds"], seconds, abs_tol=1e-6)
                or type(meter.get("goal_attempts")) is not int or meter["goal_attempts"] != 1
                or any(type(meter.get(k)) is not int or meter[k] != 0
                       for k in ("actions_attempted", "actions_completed", "frames", "restore_attempts", "nested_restore_attempts", "training_healing_attempts"))):
            return None
        old_custody, new_custody = before_context["field_carrier"], after_context["field_carrier"]
        if old_custody.get("phase") != "pending" or new_custody.get("phase") != "active":
            return None
        unchanged = dict(new_custody, phase="pending")
        if (canonical_sha256(unchanged) != canonical_sha256(old_custody)
                or evidence.get("original_guard_sha256") != old_custody.get("original_guard_sha256")):
            return None
        guard = runtime.adapter.party_guard
        if (not isinstance(guard, RedPlayerPartyGuard) or guard.field_carrier is None
                or canonical_sha256(guard.field_carrier.private_dict()) != canonical_sha256(new_custody)):
            return None
        guard.verify_authorized_active_roster()
        original_plan = old_custody["preparation_before"]
        before_plan, after_plan = before_context["preparation"], after_context["preparation"]
        if (not all(type(p) is dict for p in (original_plan, before_plan, after_plan))
                or canonical_sha256({k:v for k,v in before_plan.items() if k not in {"roster", "targets"}})
                   != canonical_sha256({k:v for k,v in after_plan.items() if k not in {"roster", "targets"}})
                or evidence.get("active_preparation_projection_sha256") != canonical_sha256(after_plan)):
            return None
        refs, party = guard.reader.preparation_specimen_refs(), guard.reader.read()
        observed = dict(zip(refs, party.members, strict=True))
        archived_targets = original_plan["targets"]
        if canonical_sha256(before_plan["targets"]) != canonical_sha256(archived_targets):
            return None
        expected_targets = tuple((ref, level) for ref, level in archived_targets
                                 if ref in observed and observed[ref].level < level)
        if (any(ref not in observed for ref, _ in archived_targets)
                or canonical_sha256(after_plan["targets"]) != canonical_sha256(expected_targets)):
            return None
        original = {m["specimen_ref"]:m for m in original_plan["roster"]}
        prior = {m["specimen_ref"]:m for m in before_plan["roster"]}
        projected = {m["specimen_ref"]:m for m in after_plan["roster"]}
        if (len(projected) != len(after_plan["roster"]) or set(projected) != set(observed)
                or set(prior) != set(observed)):
            return None
        carrier = old_custody["carrier_ref"]
        for ref, member in projected.items():
            role = {k:v for k,v in member.items() if k != "observation"}
            old_role = {k:v for k,v in prior[ref].items() if k != "observation"}
            if role != old_role or canonical_sha256(member["observation"]) != canonical_sha256(asdict(observed[ref])):
                return None
            if ref == carrier:
                if member.get("purpose") != "field_utility" or member.get("milestone_level") is not None:
                    return None
            elif role != {k:v for k,v in original[ref].items() if k != "observation"}:
                return None
        frames = runtime.emulator.frame_count
        buttons = tuple(runtime.emulator.pressed_buttons)
        inventory = inspect_bindings()
        bindings = getattr(inventory, "bindings", ())
        if (not isinstance(inventory, GoalBindingSet) or not bindings
                or any(b.binding_ref.startswith("pokemon.red:aborted-field-carrier-return:") for b in bindings)
                or runtime.emulator.save_state_bytes() != state or runtime.emulator.frame_count != frames
                or tuple(runtime.emulator.pressed_buttons) != buttons
                or runtime.adapter.party_guard is not guard):
            return None
        guard.verify_authorized_active_roster()
        return dict(schema="pokemon.red.zero-input-carrier-abort-handoff.v1",
                    source_state_sha256=state_sha, source_context_sha256=old_sha,
                    exported_context_sha256=new_sha, original_guard_sha256=old_custody["original_guard_sha256"],
                    active_preparation_projection_sha256=canonical_sha256(after_plan),
                    pending_to_active=True, raw_no_state_progress_preserved=True,
                    archived_targets_preserved=True,
                    active_targets_reconciled_from_native_levels=True,
                    physically_achieved_target_count=len(archived_targets) - len(expected_targets),
                    native_progress=False, quest_progress=False, new_controller_inputs=0,
                    successor_inventory_verified_no_repeat_abort=True,
                    decision_debit=1, seconds_debit=seconds, aggregate_reset=False)
    except (KeyError, IndexError, TypeError, ValueError, AttributeError):
        return None


def qualified_zero_input_carrier_abort_handoff(
    result, *, plan, runtime, menu, source_context_bytes,
    exported_context_bytes, expected_source_context_sha256,
):
    def inspect():
        actions = InspectionExecutor(FrameSafeExecutor(ReadOnlyController(runtime.emulator)))
        return menu.enumerate_base(runtime, actions, runtime.adapter.observe())
    return _qualified_zero_input_carrier_abort_handoff(
        result, plan=plan, runtime=runtime, inspect_bindings=inspect,
        source_context_bytes=source_context_bytes, exported_context_bytes=exported_context_bytes,
        expected_source_context_sha256=expected_source_context_sha256,
    )

def qualified_collection_field_handoff(result, *, runtime, menu, parent):
    """Inspect the already selected PC loan or the interrupted trainer-funding route."""
    from pokemon_red_completion.red_player_configuration import (
        _interrupted_bird_loan_refs, _retained_field_faint_inventory,
    )
    from pokemon_red_completion.red_player_party_guard import RedPlayerPartyGuard

    episode = result.get("episode", {})
    outcomes = episode.get("outcomes") or ()
    if (not outcomes or result.get("error_type") or result.get("released") is not True
            or result.get("paired_context_authenticated") is not True
            or episode.get("stop_reason") != "execution_failed"
            or any(row.get("error_type") for row in outcomes[:-1])):
        return None
    last = outcomes[-1]
    signature = (last.get("selected_kind"), last.get("error_type"), last.get("error"))
    bird = signature == ("acquire_species", "SettledNativeTrainerRecovery",
                         "verified trainer exit needs native faint recovery")
    funding = signature == ("resupply", "RouteExecutionError", "Gen I route cannot dismiss 'scripted_dialogue'")
    if not (bird or funding):
        return None
    expected_error = dict(error_type=last["error_type"], error=last["error"],
                          reason_code="interruption_unrecovered" if bird else "world_state_diverged")
    if (last.get("error_chain") != [expected_error] or last.get("failure_phase") != "execution"
            or last.get("safe_terminal") is not True or runtime.emulator.pressed_buttons
            or result.get("field_ready") is not bird or bool(_field_ready(runtime)) != bird):
        return None
    raw = runtime.reader.read()
    if raw.battle_state != 0 or not raw.party_hp or not any(raw.party_hp) or 0 not in raw.party_hp:
        return None
    state, frame = runtime.emulator.save_state_bytes(), runtime.emulator.frame_count
    digest = sha256(state).hexdigest()
    if (result.get("state_sha256") != digest or last.get("terminal_state_sha256") != digest
            or set(last["before"]["owned_species"]) != set(last["after"]["owned_species"])):
        return None
    actions = InspectionExecutor(FrameSafeExecutor(ReadOnlyController(runtime.emulator)))
    if bird:
        plan = json.loads((Path(parent) / "PLAN.json").read_bytes())
        configuration = RedPlayerConfiguration.from_dict(plan["configuration"])
        refs = _interrupted_bird_loan_refs(parent, configuration, failed_result=result)
        guard = getattr(runtime.adapter, "party_guard", None)
        if not refs or not isinstance(guard, RedPlayerPartyGuard) or set(guard.loanable_refs) != set(refs):
            return None
        guard.verify()
        inventory = menu.enumerate_base(runtime, actions, runtime.adapter.observe())
        expected = "pokemon.red:retained-loan-return:" + digest
    else:
        started = Path(parent)/"native"/"episode"/f"step-{last['ordinal']:03d}"/"execution-started.json"
        if not started.is_file():
            return None
        chosen = json.loads(started.read_bytes())
        if (chosen.get("state_sha256") != last["before_state_sha256"]
                or chosen.get("selected_kind") != "resupply"
                or not str(chosen.get("selected_binding_ref", "")).startswith("red-trainer-funding:")):
            return None
        inventory = _retained_field_faint_inventory(runtime, actions, parent=parent, failed_result=result)
        expected = "pokemon.red:retained-motion:" + digest
    if state != runtime.emulator.save_state_bytes() or frame != runtime.emulator.frame_count:
        raise ValueError("collection handoff inspection changed the held state")
    if (type(inventory) is not GoalBindingSet or len(inventory.bindings) != 1
            or inventory.bindings[0].kind is not GoalKind.RECOVER_CONTROL
            or inventory.bindings[0].binding_ref != expected):
        return None
    return dict(schema="pokemon.red.qualified-native-control-handoff.v1", state_sha256=digest,
                binding_ref=expected, qualified=True, inputs=0, frames=0, model_queries=0,
                failed_transport_preserved=True, strategic_substitution=False, original_terminal_safe=True,
                failed_outcome_sha256=canonical_sha256(last), retained_bird_loan=bird,
                retained_funding_faint=funding, captured=False)


def qualified_menu_control_handoff(result, *, runtime, menu, retained_parent=None,
                                   catcher_plan=None, failure_reason=None, rom=None):
    """One action-free qualification shared by fresh and continuation entry.

    This delegates to the existing exact retained-source/unique-recovery guard;
    it neither supplies a strategic goal nor turns an unknown error into success.
    """

    from pokemon_red_completion.red_capture_switch_handoff import catcher_switch_failure, development_recovery
    outcomes = result.get("episode", {}).get("outcomes") or ()
    if (outcomes and outcomes[-1].get("error_type") == "Gen1FieldBlackoutPending"
            and retained_parent is not None and failure_reason == "native_execution_error"
            and development_recovery(catcher_plan)):
        from pokemon_red_completion.red_player_configuration import _retained_field_blackout_inventory
        last = outcomes[-1]
        error = "observed all-party field poison faint requires native blackout"
        if (result.get("error_type") or result.get("paired_context_authenticated") is not True
                or result.get("episode", {}).get("stop_reason") != "execution_failed"
                or any(row.get("error_type") for row in outcomes[:-1])
                or last.get("failure_phase") != "execution" or last.get("safe_terminal") is not True
                or last.get("error_chain") != [dict(error_type="Gen1FieldBlackoutPending",
                                                    error=error, reason_code="world_state_diverged")]
                or runtime.emulator.pressed_buttons or _field_ready(runtime)):
            return None
        started = Path(retained_parent)/"native"/"episode"/f"step-{last['ordinal']:03d}"/"execution-started.json"
        if not started.is_file():
            return None
        choice = json.loads(started.read_bytes())
        if (choice.get("selected_kind") != "restore_team"
                or choice.get("state_sha256") != last.get("before_state_sha256")
                or not str(choice.get("selected_binding_ref", "")).startswith("pokemon.red:routed-restoration:")):
            return None
        state, frame = runtime.emulator.save_state_bytes(), runtime.emulator.frame_count
        inspection = InspectionExecutor(FrameSafeExecutor(ReadOnlyController(runtime.emulator)))
        inventory = _retained_field_blackout_inventory(runtime, inspection, parent=retained_parent, failed_result=result)
        if runtime.emulator.save_state_bytes() != state or runtime.emulator.frame_count != frame:
            raise ValueError("field blackout inspection changed the held checkpoint")
        digest = sha256(state).hexdigest()
        expected = "pokemon.red:field-blackout:" + digest
        if (type(inventory) is not GoalBindingSet or len(inventory.bindings) != 1
                or inventory.bindings[0].kind is not GoalKind.RECOVER_CONTROL
                or inventory.bindings[0].binding_ref != expected):
            return None
        return dict(schema="pokemon.red.qualified-native-control-handoff.v1", state_sha256=digest,
                    binding_ref=expected, qualified=True, inputs=0, frames=0, model_queries=0,
                    failed_transport_preserved=True, strategic_substitution=False, original_terminal_safe=True,
                    failed_outcome_sha256=canonical_sha256(last), retained_field_blackout=True)
    if (outcomes and retained_parent is not None and failure_reason == "native_execution_error"
            and development_recovery(catcher_plan)
            and outcomes[-1].get("error_type") in ("SettledNativeTrainerRecovery", "RouteExecutionError")):
        handoff = qualified_collection_field_handoff(result, runtime=runtime, menu=menu, parent=retained_parent)
        if handoff is not None:
            return handoff
    if (outcomes and outcomes[-1].get("error_type") in ("RedCaptureStatusError", "RouteExecutionError")
            and failure_reason == "native_execution_error" and retained_parent is not None
            and rom is not None and development_recovery(catcher_plan)):
        from pokemon_red_completion.red_survey_faint_settlement import retained_survey_faint_inventory

        state, frame = runtime.emulator.save_state_bytes(), runtime.emulator.frame_count
        inspection = InspectionExecutor(FrameSafeExecutor(ReadOnlyController(runtime.emulator)))
        inventory = retained_survey_faint_inventory(runtime, inspection, parent=retained_parent,
                                                    rom=rom, failed_result=result)
        if runtime.emulator.save_state_bytes() != state or runtime.emulator.frame_count != frame:
            raise ValueError("survey faint inspection changed the held state")
        expected = "pokemon.red:retained-survey-faint:" + sha256(state).hexdigest()
        if (inventory is not None and len(inventory.bindings) == 1
                and inventory.bindings[0].kind is GoalKind.RECOVER_CONTROL
                and inventory.bindings[0].binding_ref == expected):
            return dict(schema="pokemon.red.qualified-native-control-handoff.v1",
                        state_sha256=sha256(state).hexdigest(), binding_ref=expected, qualified=True,
                        inputs=0, frames=0, model_queries=0, failed_transport_preserved=True,
                        strategic_substitution=False, retained_survey_faint=True,
                        original_terminal_safe=outcomes[-1]["safe_terminal"], captured=False)
    is_catcher = bool(outcomes and catcher_switch_failure(outcomes[-1]))
    if is_catcher:
        if (failure_reason != "native_execution_error" or retained_parent is None or rom is None
                or not development_recovery(catcher_plan)):
            return None
        # The normal runner has just computed the failure reason. RESULT is
        # finalized after this no-input inspection; terminal and CONTEXT exist.
        result = dict(result, continuation_reason=failure_reason)

    def inspect_control_bindings():
        actions = InspectionExecutor(FrameSafeExecutor(ReadOnlyController(runtime.emulator)))
        if is_catcher:
            from pokemon_red_completion.red_player_configuration import _retained_wild_faint_inventory
            return _retained_wild_faint_inventory(
                runtime, actions, parent=retained_parent, rom=rom, failed_result=result)
        outcomes = result.get("episode", {}).get("outcomes", ())
        last = outcomes[-1] if outcomes else {}
        if (retained_parent is not None and runtime.reader.read().battle_state == 0
                and last.get("selected_kind") == "evolve_species"
                and last.get("error_type") == "RedGoalContextError"
                and last.get("error") == "PC loan settlement requires settled field control"):
            from pokemon_red_completion.red_player_configuration import _retained_field_faint_inventory
            retained = _retained_field_faint_inventory(
                runtime, actions, parent=retained_parent, failed_result=result)
            if retained is not None:
                return retained
        if retained_parent is not None and paused_capture_outcome(last):
            # The live menu is still bound to the previous segment. Inspect the
            # exact successor this failed segment would be offered; the journal
            # verifier writes nothing until its binding executes.
            from pokemon_red_completion.red_player_configuration import _retained_capture_inventory
            try:
                return _retained_capture_inventory(
                    runtime, actions, parent=retained_parent,
                    output=Path(retained_parent) / "capture-handoff-inspection")
            except (ValueError, AssertionError):
                return None
        return menu.enumerate_base(runtime, actions, runtime.adapter.observe())

    return qualified_native_control_handoff(
        result, runtime=runtime, inspect_bindings=inspect_control_bindings, retained_parent=retained_parent,
        **({"catcher_plan": catcher_plan} if is_catcher else {})
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
        **({"required_species": tuple(plan["required_species"])}
           if "required_species" in plan else {}),
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
            result.update(
                error_type=type(error).__name__,
                error=str(error),
                error_chain=_exception_chain(error),
            )
        finally:
            rec.enabled = False
            ctrl.input_enabled = False
            _write(output / "terminal.state", ctrl.save_state_bytes())
            result.update(
                actions=len(rec.trace),
                frames=ctrl.frames_executed,
                seconds=wall.elapsed_seconds,
                released=not ctrl.pressed_buttons,
                **player_lifecycle_fields(
                    scope="diagnostic_chunk",
                    released=not ctrl.pressed_buttons,
                    guest_backend_closed=(em._backend is None) if hasattr(em, "_backend") else None,
                ),
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
    result.update(
        player_lifecycle_fields(
            scope="driver_terminal",
            released=result["released"],
            guest_backend_closed=(em._backend is None) if hasattr(em, "_backend") else None,
        )
    )
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
        raise ValueError(
            "evolution experiment requires bounded non-copy-back DEVELOPMENT diagnostic"
        )
    return dict(spec)


def evolution_recovery_accounting(session, evidence):
    """Reconcile all charged attempts; skill trips are a narrower counter."""
    charged = session.heals
    training = session.training_healing_trips
    restores = session.support_restorations
    overlaps = session.training_restoration_overlaps
    reported = evidence.get("healing_trips")
    valid = all(
        type(v) is int and v >= 0 for v in (charged, training, restores, overlaps, reported)
    )
    exact = (
        valid and overlaps <= min(training, restores) and charged == training + restores - overlaps
    )
    funded = valid and reported <= charged
    return dict(
        passed=bool(exact and funded),
        charged_recovery_attempts=charged,
        training_trip_attempts=training,
        restoration_attempts=restores,
        verified_overlap_credits=overlaps,
        reported_skill_healing_trips=reported,
        counters_have_different_scope=True,
    )


def evolution_copy_limits(args, left, seconds, *, experiment):
    """Explicit measurements reuse the same finite aggregate clipping as play."""
    if experiment is not None:
        request = argparse.Namespace(
            decisions=1,
            seconds=seconds,
            actions=getattr(args, "actions", 20000),
            frames=getattr(args, "frames", 2000000),
        )
        return configured_execution_limits(request, left, seconds)
    return NativePlayerLimits(
        decisions=1,
        actions=min(20000, int(left["actions"])),
        frames=min(2000000, int(left["frames"])),
        seconds=seconds,
        heals=int(left["heals"]),
        cash_debits=None,
    )


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
        **dict(player_wiring_declaration(plan), diagnostic_only=True),
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
        backend, configuration, parent, output, plan_path=output / "PLAN.json",
        **({"required_species": tuple(plan["required_species"])}
           if "required_species" in plan else {}),
    )
    result = dict(passed=False, error=None, copy_back=False, model_queries=0, fits=0)
    with c.PyBoyAdapter(c.ROM) as em:
        em.load_state_bytes(payload)
        journal = output / "journal"
        journal.mkdir(mode=0o700)
        store = initialize_private_root(
            journal,
            repository_root=c.REPO,
            allow_same_device=True,
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
                world, venues = provider(
                    runtime, holder["configured_route"].route_world, experiment["venue"]
                )
                if (
                    em.save_state_bytes() != state
                    or em.frame_count != frames
                    or session.actions.actions_executed != action_count
                ):
                    raise ValueError("evolution venue discovery changed the game")
                options = dict(
                    training_venues=venues,
                    prefer_highest_supported_venue=True,
                    allow_guarded_venue_escapes=True,
                    maximum_quanta=experiment["maximum_quanta"],
                    maximum_wall_seconds=min(
                        experiment["maximum_wall_seconds"], max(1, limits.seconds - 20)
                    ),
                )
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
                final = next(
                    (row for row in after if prior is not None and row[0] == prior[0]), None
                )
                gain = None if prior is None or final is None else final[3] - prior[3]
                bounded_partial = (
                    verdict.status.value == "failed"
                    and verdict.failure_reason is GoalFailureReason.OUTCOME_NOT_VERIFIED
                    and report.evidence.get("evolution_partial") is True
                    and any(
                        report.evidence.get(k) is True
                        for k in (
                            "settlement_reserve_reached",
                            "wall_limit_reached",
                            "quantum_limit_reached",
                        )
                    )
                )
                result.update(
                    experiment=experiment,
                    trainee_ref=None if prior is None else prior[0],
                    trainee_experience_before=None if prior is None else prior[3],
                    trainee_experience_after=None if final is None else final[3],
                    useful_trainee_xp_gain=gain,
                    native_evolution_succeeded=verdict.status.value == "succeeded",
                    productive_bounded_partial=bounded_partial,
                    passed=preserved
                    and xp_retained
                    and type(gain) is int
                    and gain > 0
                    and (bounded_partial or verdict.status.value == "succeeded")
                    and evolution_recovery_accounting(session, report.evidence)["passed"]
                    and _field_ready(runtime),
                )
        except BaseException as error:
            result.update(
                error_type=type(error).__name__,
                error=str(error),
                error_chain=_exception_chain(error),
            )
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
                **player_lifecycle_fields(
                    scope="diagnostic_chunk",
                    released=not em.pressed_buttons,
                    guest_backend_closed=(em._backend is None) if hasattr(em, "_backend") else None,
                ),
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
                    result.update(
                        passed=False,
                        context_error=str(error),
                        context_error_type=type(error).__name__,
                        context_error_chain=_exception_chain(error),
                    )
            _record(output / "RESULT.json", result)
    result.update(
        player_lifecycle_fields(
            scope="driver_terminal",
            released=result["released"],
            guest_backend_closed=(em._backend is None) if hasattr(em, "_backend") else None,
        )
    )
    if result["passed"]:
        try:
            proof = verify_diagnostic_reload(c, factory, payload, output, after, result["spent"])
            result["reload_passed"] = proof["passed"]
            result["passed"] = bool(result["passed"] and proof["passed"])
        except BaseException as error:
            result.update(
                passed=False,
                reload_error=str(error),
                reload_error_type=type(error).__name__,
                reload_error_chain=_exception_chain(error),
            )
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
        carried = restore_player_continuation(
            reloaded,
            doc(output / "CONTEXT.json"),
            expected_sha256=canonical_sha256(doc(output / "CONTEXT.json")),
            evolution_rom=c.ROM.read_bytes(),
        )
        proof = dict(
            passed=fresh.save_state_bytes() == terminal
            and fresh.frame_count == 0
            and not fresh.pressed_buttons
            and _stock(reloaded) == after_stock
            and carried.spent == spent
            and _field_ready(reloaded),
            inputs=0,
            frames=fresh.frame_count,
            model_queries=0,
            state_sha256=c.digest(output / "terminal.state"),
            context_sha256=c.digest(output / "CONTEXT.json"),
            copy_back=False,
            inherited_spent=carried.spent,
        )
        _record(output / "RELOAD.json", proof)
        return proof


def verify_boxed_machine_copy(
    args, plan, root, backend, configuration, parent, context, left, *, prepared_evolution=False
):
    """One explicit operator diagnostic; ordinary gameplay still uses the model."""
    from pokemon_red_completion.red_boxed_machine_options import boxed_frontier_machine_options
    from pokemon_red_completion.red_player_party_loan import _stock

    expected_mode = (
        "boxed_frontier_evolution_bundles_v3"
        if prepared_evolution
        else "boxed_frontier_attack_capacity_v2"
    )
    if (
        type(prepared_evolution) is not bool
        or plan.get("diagnostic_only") is not True
        or plan.get("actual_gameplay_resume_authorized") is not False
        or plan.get("copy_back") is not False
        or plan.get("fit_allowed") is not False
        or not declared_owned_machine_options(plan)
        or plan["owned_machine_options"]["mode"] != expected_mode
    ):
        raise ValueError("boxed-machine copy requires explicit non-copy-back diagnostic authority")
    c = backend.c
    seconds = min(
        args.seconds,
        int(left["seconds"]),
        int((datetime.fromisoformat(plan["cutoff_utc"]) - datetime.now(UTC)).total_seconds()),
    )
    request = argparse.Namespace(
        decisions=1, actions=args.actions, frames=args.frames, seconds=seconds
    )
    limits = configured_execution_limits(request, left, seconds)
    prefix = "prepared-evolution" if prepared_evolution else "boxed-machine"
    output = root / f"diagnostics/{prefix}-{datetime.now(UTC).strftime('%H%M%S%f')}"
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    declaration = dict(
        partition="development",
        correlated_copy=True,
        copy_back=False,
        operator_diagnostic_choice=True,
        goal_model_queries=0,
        **dict(player_wiring_declaration(plan), diagnostic_only=True),
        actual_gameplay_resume_authorized=False,
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
    payload, factory, menu, holder, source = assemble_configured_player(
        backend, configuration, parent, output, plan_path=output / "PLAN.json",
        **({"required_species": tuple(plan["required_species"])}
           if "required_species" in plan else {}),
    )
    if prepared_evolution:
        connect_declared_machine_options(
            menu, plan, rom=c.ROM.read_bytes(), holder=holder, configuration=configuration
        )
    result = dict(
        passed=False,
        error=None,
        copy_back=False,
        model_queries=0,
        fits=0,
        decisions=1,
        prepared_evolution=prepared_evolution,
    )
    after = None
    with c.PyBoyAdapter(c.ROM) as em:
        em.load_state_bytes(payload)
        factory(ReadOnlyController(em))
        journal = output / "journal"
        journal.mkdir(mode=0o700)
        store = initialize_private_root(
            journal,
            repository_root=c.REPO,
            allow_same_device=True,
            **declared_input_recording(plan),
        )
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
            combat_specimen_refs=tuple(
                m.specimen_ref for m in holder["plan"].roster if m.purpose.value == "combat"
            ),
            battle_observer=holder["observe_history"],
            target_cash=0,
            model_feature_version=7,
            curriculum=declared_player_curriculum(
                plan,
                next(m.specimen_ref for m in holder["plan"].roster if m.purpose.value == "combat"),
            ),
            allow_collection_restoration=True,
            force_resource_safety=False,
            include_live_pp_readiness=True,
        )
        runtime = session.runtime
        before = _stock(runtime)
        try:
            if prepared_evolution:
                choices = tuple(
                    row
                    for row in menu.enumerate_collection(
                        runtime, session.actions, runtime.adapter.observe()
                    )
                    if row.binding.binding_ref.startswith("pokemon.red:prepared-evolution:")
                )
            else:
                choices = boxed_frontier_machine_options(
                    runtime,
                    session.actions,
                    runtime.adapter.observe(),
                    rom=c.ROM.read_bytes(),
                    world=holder["configured_route"].route_world,
                )
            if not choices:
                raise ValueError("no observed boxed-frontier machine bundle is available")
            choice = max(choices, key=lambda row: row.candidate.features.dependency_unlock_gain)
            _record(
                output / "CHOICE.json",
                dict(
                    binding_ref=choice.binding.binding_ref,
                    operator_choice=True,
                    selector="highest_declared_capacity_gain",
                    available_bundles=len(choices),
                    model_queries=0,
                ),
            )
            session.active_kind = (
                GoalKind.EVOLVE_SPECIES if prepared_evolution else GoalKind.DEVELOP_TEAM
            )
            session.recorder.enabled = True
            report = choice.binding.execute()
            session.recorder.enabled = False
            verdict = choice.binding.verify(report)
            after = _stock(runtime)
            runtime.adapter.party_guard.verify_active_roster_restored()
            if prepared_evolution:
                from pokemon_red_completion.red_prepared_evolution_options import (
                    prepared_stock_progress,
                )

                progress = prepared_stock_progress(before, after)
                result.update(progress)
                result["recovery_accounting"] = evolution_recovery_accounting(
                    session, report.evidence
                )
                stock_ok = all(progress.values()) and result["recovery_accounting"]["passed"]
            else:
                stock_ok = before == after
            result.update(
                passed=verdict.status.value == "succeeded" and stock_ok and _field_ready(runtime),
                evidence=dict(report.evidence),
                verification=verdict.status.value,
                stock_xp_preserved=stock_ok,
            )
        except BaseException as error:
            result.update(
                error_type=type(error).__name__,
                error=str(error),
                error_chain=_exception_chain(error),
            )
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
                original_roles_restored=set(runtime.adapter.party_guard.refs)
                <= set(runtime.adapter.party_guard.reader.preparation_specimen_refs()),
                field_ready=_field_ready(runtime),
                released=not em.pressed_buttons,
                **player_lifecycle_fields(
                    scope="diagnostic_chunk",
                    released=not em.pressed_buttons,
                    guest_backend_closed=(em._backend is None) if hasattr(em, "_backend") else None,
                ),
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
                        runtime, preparation=holder["plan"], battle=None, spent=spent
                    )
                    _record(output / "CONTEXT.json", exported)
                    result.update(spent=spent, context_sha256=c.digest(output / "CONTEXT.json"))
                except BaseException as error:
                    result.update(
                        passed=False,
                        context_error=str(error),
                        context_error_type=type(error).__name__,
                        context_error_chain=_exception_chain(error),
                    )
            _record(output / "RESULT.json", result)
    result.update(
        player_lifecycle_fields(
            scope="driver_terminal",
            released=result["released"],
            guest_backend_closed=(em._backend is None) if hasattr(em, "_backend") else None,
        )
    )
    if result["passed"]:
        try:
            proof = verify_diagnostic_reload(c, factory, payload, output, after, result["spent"])
            result["reload_passed"] = proof["passed"]
            result["passed"] = bool(result["passed"] and proof["passed"])
        except BaseException as error:
            result.update(
                passed=False,
                reload_error=str(error),
                reload_error_type=type(error).__name__,
                reload_error_chain=_exception_chain(error),
            )
        # Native RESULT is already immutable. Keep final reload status separately.
    _record(output / "FINAL-RESULT.json", result)
    authenticate_parent(parent, c.digest)
    verify_pins(plan["protected"])
    print(json.dumps(dict(result, output=str(output)), default=str), flush=True)


def run(args):
    path = Path(args.plan).resolve()
    plan, root = doc(path), path.parent
    validate_sequence_runner_mode(plan, args)
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
    if nodes:
        previous = doc(parent / "PLAN.json")
        if previous["configuration_sha256"] != configuration.sha256:
            raise ValueError("cannot silently change configuration across a continuation")
        validate_continued_sequence_wiring(plan, previous)
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
        verify_boxed_machine_copy(
            args,
            plan,
            root,
            backend,
            configuration,
            parent,
            context,
            left,
            prepared_evolution=prepared_copy,
        )
        return
    if args.evolution_copy:
        if args.inspect:
            raise ValueError("evolution copy and zero-input inspection are separate modes")
        verify_evolution_copy(args, plan, root, backend, configuration, parent, context, left)
        return
    model = declared_goal_model(plan, configuration, backend)
    declared_sequence_options(plan, model)
    refinement = declared_readiness_refinement(plan)
    greedy = declared_greedy_selection(plan)
    _preparation_component = declared_preparation_component(plan)
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
        **(
            {
                "goal_model_observation_identity": dict(
                    stored_model_sha256=configuration.goal_model_sha256,
                    effective_model_sha256=model.model_sha256,
                )
            }
            if "goal_model_observation_compatibility" in wiring
            else {}
        ),
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
            backend,
            configuration,
            parent,
            output,
            plan_path=output / "PLAN.json",
            **({"required_species": tuple(plan["required_species"])}
               if "required_species" in plan else {}),
            model_feature_version=model.feature_version,
            **(
                {"include_preparation_party_context": True}
                if declared_preparation_context(plan) or (refinement.get("consequence_head") is not None
                and refinement["consequence_head"].context_projection
                == "prospective_preparation_party_context_v1")
                else {}
            ),
        )
    except BaseException as error:
        _record(
            output / "PRELAUNCH-ERROR.json",
            dict(
                phase="before_emulator",
                released=True,
                **player_lifecycle_fields(
                    scope="prelaunch_failure", released=True, guest_backend_closed=None
                ),
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
        connect_declared_machine_options(
            menu, plan, rom=rom, holder=holder, configuration=configuration
        )
    with (
        RunFrameFeed(plan, root, enabled=not args.inspect) as feed,
        c.PyBoyAdapter(c.ROM, **feed.adapter_options) as em,
    ):
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
                association_source_sha256 = None
                if refinement is not None and refinement.get("associate_unique_combat", False):
                    observed_state = em.save_state_bytes()
                    association_source_sha256 = sha256(observed_state).hexdigest()
                    if (
                        observed_state != payload
                        or association_source_sha256 != context["state_sha256"]
                    ):
                        raise ValueError(
                            "inspection association source differs from authenticated "
                            "native boundary"
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
                        defer_unbound_preparation=refinement.get(
                            "defer_unbound_preparation", False
                        ),
                        allow_singleton_parent_support=refinement.get(
                            "allow_singleton_parent_support", False
                        ),
                        associate_unique_combat=refinement.get("associate_unique_combat", False),
                        source_state_sha256=association_source_sha256,
                    )
                    if refinement
                    else select_red_live_option(
                        model,
                        options,
                        seed=plan["seed"] + ordinal,
                        greedy_selection=greedy,
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
            if automatic and reason == "declared_consequence_complete":
                task_handoff = qualified_registration_task_handoff(
                    result, plan=plan, runtime=holder["runtime"], output=output)
                if task_handoff is not None:
                    result["qualified_registration_task_handoff"] = task_handoff
                    reason = "automatic_registration_task_renewal"
            if automatic and reason == "native_execution_error":
                handoff = qualified_menu_control_handoff(
                    result,
                    runtime=holder["runtime"],
                    menu=menu,
                    retained_parent=output, catcher_plan=plan, failure_reason=reason,
                    rom=lambda: c.ROM.read_bytes(),
                )
                if handoff is not None:
                    result["qualified_native_control_handoff"] = handoff
                    reason = "automatic_control_recovery"
            if automatic and reason == "no_executable_progress":
                handoff = qualified_zero_input_carrier_abort_handoff(
                    result, plan=plan, runtime=holder["runtime"], menu=menu,
                    source_context_bytes=(parent / "CONTEXT.json").read_bytes(),
                    exported_context_bytes=(output / "CONTEXT.json").read_bytes(),
                    expected_source_context_sha256=declaration["context_sha256"],
                )
                if handoff is not None:
                    result["qualified_zero_input_carrier_abort_handoff"] = handoff
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
            driver_terminal_reason = configured_renewal_stop_reason(
                args,
                left,
                int(
                    (datetime.fromisoformat(plan["cutoff_utc"]) - datetime.now(UTC)).total_seconds()
                ),
                compulsory_settlement=requires_compulsory_settlement(holder["runtime"]),
            )
            if driver_terminal_reason is not None:
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
                backend,
                configuration,
                parent,
                output,
                plan_path=output / "PLAN.json",
                **({"required_species": tuple(plan["required_species"])}
                   if "required_species" in plan else {}),
                model_feature_version=model.feature_version,
                live_party_runtime=holder["runtime"],
                **(
                    {"include_preparation_party_context": True}
                    if declared_preparation_context(plan) or (refinement.get("consequence_head") is not None
                    and refinement["consequence_head"].context_projection
                    == "prospective_preparation_party_context_v1")
                    else {}
                ),
            )
            if payload != em.save_state_bytes():
                raise ValueError("automatic renewal changed the retained native state")
            if machine_options:
                connect_declared_machine_options(
                    menu, plan, rom=c.ROM.read_bytes(), holder=holder, configuration=configuration
                )
            factory(ReadOnlyController(em))
    result = dict(
        result,
        **player_lifecycle_fields(
            scope="driver_terminal",
            released=result.get("released") is True,
            guest_backend_closed=em._backend is None,
        ),
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
