"""Clean power-on entry for the existing frozen hybrid DEVELOPMENT candidate.

One emulator remains alive across automatic runtime renewals. Snapshots are
receipts only: this entry has no restore/resume command. Model weights never fit
or change. The fixed starter initialization is explicitly unlearned support.
"""

import argparse
import importlib
import json
from contextlib import contextmanager
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from time import monotonic

from run_configured_red_player import (
    AUTOMATIC_CONTINUATIONS,
    CHUNK_BUDGET_ERRORS,
    paused_capture_outcome,
    chunk_continuation_reason,
    connect_declared_machine_options,
    declared_automatic_renewal,
    declared_input_recording,
    declared_preparation_context,
    declared_readiness_refinement,
    declared_safe_stop_continuation,
    execute_player_chunk,
    player_wiring_declaration,
    qualified_menu_control_handoff,
    qualified_registration_task_handoff,
    qualified_movement_stall_setback,
    qualified_safe_stop_setback,
    requires_compulsory_settlement,
)

from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING
from pokemon_red_completion.executor import MonotonicWallTimeBudgetController, ReadOnlyController
from pokemon_red_completion.goal_search_memory import GoalSearchMemory
from pokemon_red_completion.opening import run_opening_chapter
from pokemon_red_completion.private_artifacts import (
    gitless_fast_path_worktree_probe,
    initialize_private_root,
)
from pokemon_red_completion.red_autonomous_player import _record, _write
from pokemon_red_completion.red_goal_context_profile import RedGoalMechanic
from pokemon_red_completion.red_native_player import (
    NativePlayerLimits,
)
from pokemon_red_completion.red_player_configuration import (
    RedPlayerConfiguration,
    assemble_configured_player,
)
from pokemon_red_completion.red_player_continuation import (
    capture_player_continuation,
)
from pokemon_red_completion.red_player_model import load_player_goal_model_record_bytes
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.red_player_origins import _NoLoadController, _OpeningActions
from pokemon_red_completion.red_player_package import bind_player_package
from pokemon_red_completion.red_player_story_menu import (
    NativeStoryBranchInventory,
    SafeStopSuppression,
)
from pokemon_red_completion.red_spectator_feed import RunFrameFeed, declared_spectator

SCHEMA = "pokemon.red.fresh-frozen-player-plan.v1"


@contextmanager
def retained_power_on(adapter, root, result):
    try:
        with adapter as emulator:
            try:
                yield emulator
            finally:
                payload = emulator.save_state_bytes()
                _write(root / "terminal.state", payload)
                result.update(
                    terminal_sha256=sha256(payload).hexdigest(),
                    released=not emulator.pressed_buttons,
                    frames=emulator.frame_count,
                )
    finally:
        result["worker_stopped"] = adapter._backend is None


FRESH_ACCEPTANCE_SCHEMA = "pokemon.red.frozen-fresh-acceptance.v1"
FRESH_ACCEPTANCE_SUPPORT = frozenset(
    {
        "declared_startup_mechanics",
        "deterministic_execution",
        "forced_singleton_mechanics",
        "league_medicine_reserve",
    }
)


def declared_fresh_acceptance(plan):
    """Classify an attempt prospectively; final acceptance still needs audit."""
    from pokemon_red_completion.provenance import canonical_sha256

    requested = plan.get("official_acceptance", False)
    if type(requested) is not bool:
        raise ValueError("fresh acceptance requires an explicit boolean")
    declaration = plan.get("acceptance_declaration")
    if not requested:
        if declaration is not None:
            raise ValueError("fresh acceptance declaration lacks prospective authority")
        return False
    expected = {
        "schema",
        "lane",
        "teacher_oracle_fallback",
        "cross_run_memory",
        "freeze_until_exit",
        "champion_and_concurrent_hall_of_fame",
        "required_registrations",
        "required_species_sha256",
        "configuration_template_sha256",
        "allowed_support",
    }
    species = plan.get("required_species")
    configuration = plan.get("configuration_template")
    if (
        not isinstance(declaration, dict)
        or set(declaration) != expected
        or declaration.get("schema") != FRESH_ACCEPTANCE_SCHEMA
        or declaration.get("lane") != "learned_hybrid"
        or declaration.get("teacher_oracle_fallback") is not False
        or declaration.get("cross_run_memory") is not False
        or declaration.get("freeze_until_exit") is not True
        or declaration.get("champion_and_concurrent_hall_of_fame") is not True
        or type(declaration.get("required_registrations")) is not int
        or declaration["required_registrations"] != 124
        or type(species) is not list
        or len(species) != 124
        or any(type(s) is not str for s in species)
        or len(set(species)) != 124
        or not isinstance(configuration, dict)
        or declaration.get("required_species_sha256") != canonical_sha256(species)
        or declaration.get("configuration_template_sha256") != canonical_sha256(configuration)
        or type(declaration.get("allowed_support")) is not list
        or any(type(s) is not str for s in declaration["allowed_support"])
        or len(declaration["allowed_support"]) != len(FRESH_ACCEPTANCE_SUPPORT)
        or set(declaration["allowed_support"]) != FRESH_ACCEPTANCE_SUPPORT
        or any(
            type(plan.get(k)) is not int or plan[k] != n
            for k, n in (
                ("maximum_state_loads", 0),
                ("maximum_emulators", 1),
                ("runtime_llm_calls", 0),
            )
        )
        or any(
            plan.get(k) is not False
            for k in ("fit_allowed", "training_admission", "copy_back", "resume_allowed")
        )
        or any(
            plan.get(k) is not True
            for k in (
                "source_and_models_frozen_during_attempt",
                "no_midrun_repair_or_rollback",
                "all_attempts_count",
            )
        )
    ):
        raise ValueError(
            "fresh acceptance needs frozen zero-load unassisted identity and full curriculum"
        )
    from pokemon_red_completion.red_player_curriculum import validate_full_red_curriculum_plan

    validate_full_red_curriculum_plan(plan)
    return True


def fresh_official_completion_candidate(plan, result, terminal_reason):
    """A runtime candidate never substitutes for final frozen/native review."""
    return (
        declared_fresh_acceptance(plan)
        and terminal_reason == "curriculum_complete"
        and result.get("passed") is True
        and all(
            type(result.get(k)) is int and result[k] == 0
            for k in ("state_loads", "training", "fits", "runtime_llm_calls")
        )
        and not result.get("error_type")
        and not result.get("pending_automatic_control_recoveries")
    )


def validate_fresh_plan(plan, *, import_only=False):
    if type(import_only) is not bool:
        raise TypeError("import-only validation must be explicit")
    if (
        plan.get("schema") != SCHEMA
        or plan.get("partition") != "development"
        or plan.get("fit_allowed") is not False
        or plan.get("copy_back") is not False
        or plan.get("resume_allowed") is not False
        or "parent" in plan
        or (not import_only and plan.get("launch_authorized") is False)
        or (not import_only and plan.get("readiness_only") is True)
        or plan.get("startup") != "declared_squirtle_mechanics_no_teacher_combat"
        or plan.get("loan_identity_binding") != "observed_initial_starter"
        or type(plan.get("extra_boot_frames")) is not int
        or not 0 <= plan["extra_boot_frames"] <= 10000
        or type(plan.get("seed")) is not int
        or not 0 <= plan["seed"] < 2**64
    ):
        raise ValueError("fresh launch declaration has a restore, teacher or undeclared start")
    declared_fresh_acceptance(plan)
    NativePlayerLimits(**plan["limits"])
    if any(
        type(plan["chunk"][key]) is not int or plan["chunk"][key] <= 0
        for key in ("decisions", "actions", "frames", "seconds")
    ):
        raise ValueError("fresh launch needs finite automatic chunks")
    player_wiring_declaration(plan)
    declared_automatic_renewal(plan)
    if declared_safe_stop_continuation(plan) is not None and not declared_automatic_renewal(plan):
        raise ValueError("safe-stop continuation requires declared automatic renewal")
    declared_input_recording(plan)
    declared_spectator(plan)
    return plan


def realized_configuration(template, *, origin_sha256, origin_id, starter_ref, teacher_profiles):
    """Bind observed identity, never choose a strategic replacement or starter."""
    base = RedPlayerConfiguration(
        origin_sha256,
        origin_id,
        template["goal_model_sha256"],
        tuple(tuple(p) for p in template["assembly_flags"]),
        tuple(tuple(p) for p in template["excluded_profiles"]),
        (starter_ref,),
        quote_capture_route_work=template["quote_capture_route_work"],
        evolution_venue_model_sha256=template.get("evolution_venue_model_sha256"),
        evolution_venue_scope=tuple(template.get("evolution_venue_scope", ())),
        evolution_allow_direct_fights=template.get("evolution_allow_direct_fights", True),
        evolution_recover_wild_faints=template.get("evolution_recover_wild_faints", False),
    )
    # Validate each input list before composing them. An already excluded exact
    # teacher must remain excluded once, not relax duplicate/identity checks.
    teachers = replace(base, excluded_profiles=tuple(teacher_profiles))
    return replace(
        base,
        excluded_profiles=base.excluded_profiles
        + tuple(pair for pair in teachers.excluded_profiles if pair not in base.excluded_profiles),
    )


def model_handoff_verified(episodes, *, recovered_control_handoffs=()):
    """Require local choice and no unresolved failure.

    Only exact live-guard receipts confirmed by a later settled chunk may
    adjudicate expected control interruptions. Original failures stay recorded.
    """
    from pokemon_red_completion.red_capture_switch_handoff import ERROR, completed_catcher_handoff
    from pokemon_red_completion.provenance import canonical_sha256
    recovered_catchers = {(r["state_sha256"], r["failed_outcome_sha256"]) for r in recovered_control_handoffs
                          if completed_catcher_handoff(r)}
    recovered = {
        receipt.get("state_sha256")
        for receipt in recovered_control_handoffs
        if receipt.get("schema") == "pokemon.red.qualified-native-control-handoff.v1"
        and isinstance(receipt.get("state_sha256"), str)
        and len(receipt["state_sha256"]) == 64
        and all(c in "0123456789abcdef" for c in receipt["state_sha256"])
        and receipt.get("ordinary_capture_switch_faint") is not True
        and receipt.get("qualified") is True
        and receipt.get("failed_transport_preserved") is True
        and receipt.get("strategic_substitution") is False
        and all(
            type(receipt.get(key)) is int and receipt[key] == 0
            for key in ("inputs", "frames", "model_queries")
        )
        and (
            receipt.get("binding_ref") in {
                "pokemon.red:retained-engagement:" + str(receipt.get("state_sha256")),
                "pokemon.red:interrupted-wild:" + str(receipt.get("state_sha256")),
            }
            or (
                receipt.get("binding_ref") == "pokemon.red:retained-motion:" + str(receipt.get("state_sha256"))
                and receipt.get("retained_declared_loan") is True
                and receipt.get("field_faint_before_pc_return") is True
            )
            or (
                receipt.get("binding_ref") == "pokemon.red:retained-capture:" + str(receipt.get("state_sha256"))
                and receipt.get("retained_capture_pause") is True
            )
        )
    }

    def unresolved_error(outcome):
        if not outcome.get("error_type") or outcome["error_type"] in CHUNK_BUDGET_ERRORS:
            return False
        if (outcome.get("error_type") == "ProtectedRecoveryError" and outcome.get("error") == ERROR
                and outcome.get("selected_kind") == "acquire_species"):
            failure = outcome.get("original_outcome_sha256") or canonical_sha256(outcome)
            return (outcome.get("terminal_state_sha256"), failure) not in recovered_catchers
        known = (
            outcome["error_type"] == "RouteExecutionError"
            and outcome.get("error")
            in {
                "field dialogue lacks a newly poisoned member faint",
                "field dialogue is not an admitted native faint",
                "Gen I route cannot dismiss 'trainer_engagement'",
            }
        ) or (
            outcome["error_type"] == "RedGoalContextError"
            and outcome.get("selected_kind") == "evolve_species"
            and outcome.get("error") == "PC loan settlement requires settled field control"
        ) or paused_capture_outcome(outcome)
        return not (known and outcome.get("terminal_state_sha256") in recovered)

    return any(e.get("model_decisions", 0) > 0 for e in episodes) and not any(
        unresolved_error(o) for e in episodes for o in e.get("outcomes", ())
    )


def compact_handoff_episode(episode):
    """Retain verification facts without keeping prior diagnostic payloads alive.

    Full episode/outcome reports remain durably recorded by the chunk runner.
    This projection preserves exactly the fields model_handoff_verified reads.
    """
    from pokemon_red_completion.red_capture_switch_handoff import catcher_switch_failure
    from pokemon_red_completion.provenance import canonical_sha256
    return {
        "model_decisions": episode.get("model_decisions", 0),
        "outcomes": [
            dict(
                {key: outcome.get(key) for key in ("error_type", "error", "selected_kind", "terminal_state_sha256")},
                **({"original_outcome_sha256": canonical_sha256(outcome)} if catcher_switch_failure(outcome) else {}),
            )
            for outcome in episode.get("outcomes", ())
            if outcome.get("error_type")
        ],
    }


def run(plan_path):
    plan_path = Path(plan_path).resolve()
    plan, root = validate_fresh_plan(json.loads(plan_path.read_bytes())), plan_path.parent
    package = plan["runtime_package"]
    manifest = bind_player_package(package["path"], package["sha256"], history_output=root)
    backend = importlib.import_module(plan["backend_module"])
    c = backend.c
    c.FROZEN_SOURCE_COMMIT = manifest["source_commit"]
    model_spec = plan["goal_model_record"]
    model_bytes = Path(model_spec["path"]).read_bytes()
    if sha256(model_bytes).hexdigest() != model_spec["content_sha256"]:
        raise ValueError("fresh actor artifact changed")
    model = load_player_goal_model_record_bytes(
        model_bytes, expected_model_sha256=plan["configuration_template"]["goal_model_sha256"]
    ).model
    limits = NativePlayerLimits(**plan["limits"])
    _record(
        root / "CLAIM.json",
        dict(
            plan_sha256=sha256(plan_path.read_bytes()).hexdigest(),
            no_resume=True,
            started_new_attempt=True,
        ),
    )
    initial, bootstrap, started = root / "initial", root / "bootstrap", monotonic()
    initial.mkdir(mode=0o700)
    bootstrap.mkdir(mode=0o700)
    journal = root / "journal"
    journal.mkdir(mode=0o700)
    recording = dict(git_worktree_probe=gitless_fast_path_worktree_probe)
    recording.update(declared_input_recording(plan))
    store = initialize_private_root(
        journal,
        repository_root=c.REPO,
        allow_same_device=True,
        **recording,
    )
    memory = GoalSearchMemory()
    result = dict(
        passed=False,
        ready=False,
        state_loads=0,
        training=0,
        fits=0,
        runtime_llm_calls=0,
        worker_stopped=False,
        fresh_power_on=True,
        assistance=plan["startup"],
        official_acceptance=False,
        official_acceptance_attempt=declared_fresh_acceptance(plan),
        official_completion_candidate=False,
        final_acceptance_requires_independent_native_review=True,
        segments=[],
    )
    emulator, episodes = None, []
    pending_control_handoffs, recovered_control_handoffs = [], []
    safe_stop = declared_safe_stop_continuation(plan)
    suppression = SafeStopSuppression() if safe_stop is not None else None
    safe_stop_setbacks, safe_stop_repeats = [], {}
    try:
        with (
            RunFrameFeed(plan, root) as feed,
            retained_power_on(
                c.PyBoyAdapter(c.ROM, watch=False, speed=None, **feed.adapter_options), root, result
            ) as emulator,
        ):
            wall = MonotonicWallTimeBudgetController(emulator, maximum_wall_seconds=limits.seconds)
            controller = _NoLoadController(wall, maximum_frames=limits.frames)
            if controller.frame_count != 0 or controller.pressed_buttons:
                raise ValueError("fresh emulator was not at untouched power-on")
            power_on = controller.save_state_bytes()
            origin_sha = sha256(power_on).hexdigest()
            _write(bootstrap / "power-on.state", power_on)
            actions = _OpeningActions(controller, bootstrap)
            opening = run_opening_chapter(
                c.ROM,
                _emulator=controller,
                _executor=actions,
                new_game_timing=replace(
                    DEFAULT_NEW_GAME_TIMING,
                    boot_frames=DEFAULT_NEW_GAME_TIMING.boot_frames + plan["extra_boot_frames"],
                ),
            )
            if not opening.passed:
                raise ValueError("fresh starter initialization failed its native gates")
            _record(bootstrap / "OPENING.json", opening.public_dict())
            payload = controller.save_state_bytes()
            _write(initial / "terminal.state", payload)
            factory, _, holder, _ = backend.shared.assembly(
                payload,
                initial,
                origin_sha=origin_sha,
                partition="development",
                origin_id=root.name,
                objective_ids=opening.verified_objectives,
                protect_party_species=False,
            )
            runtime = factory(ReadOnlyController(controller))
            holder["runtime"] = runtime
            refs = holder["refs"]
            if len(refs) != 1:
                raise ValueError("fresh initializer must observe exactly its actual starter")
            teacher_profiles = tuple(
                (p.kind.value, p.configuration_sha256)
                for p in runtime.profile.providers
                if p.mechanic is RedGoalMechanic.OAKS_ERRAND
            )
            if len(teacher_profiles) != 1:
                raise ValueError(
                    "fresh player must exclude its deterministic rival/errand provider"
                )
            configuration = realized_configuration(
                plan["configuration_template"],
                origin_sha256=origin_sha,
                origin_id=root.name,
                starter_ref=refs[0],
                teacher_profiles=teacher_profiles,
            )
            _record(root / "REALIZED-CONFIGURATION.json", configuration.to_dict())
            spent = dict(
                actions=actions.delegate.attempted_actions,
                frames=controller.frame_count,
                decisions=0,
                heals=0,
                cash_debits=0,
                seconds=monotonic() - started,
            )
            context = capture_player_continuation(
                runtime, preparation=holder["plan"], battle=None, spent=spent, search_memory=memory
            )
            _record(initial / "CONTEXT.json", context)
            _record(
                initial / "RESULT.json",
                dict(
                    passed=True,
                    worker_stopped=True,
                    live_driver_running=True,
                    released=not controller.pressed_buttons,
                    state_sha256=context["state_sha256"],
                    context_sha256=c.digest(initial / "CONTEXT.json"),
                    spent=spent,
                    configuration_sha256=configuration.sha256,
                ),
            )
            result.update(
                power_on_sha256=origin_sha,
                configuration_sha256=configuration.sha256,
                goal_model_sha256=model.model_sha256,
                startup_actions=spent["actions"],
                startup_frames=spent["frames"],
                deterministic_combat_disabled=True,
            )
            parent, ordinal = initial, 0
            while True:
                left = {
                    key: getattr(limits, key) - spent[key]
                    for key in ("decisions", "actions", "frames", "heals")
                }
                left["seconds"] = int(limits.seconds - (monotonic() - started))
                if min(left.values()) <= 0:
                    result["terminal_reason"] = "declared_budget_exhausted"
                    break
                if (
                    requires_compulsory_settlement(holder["runtime"])
                    and min(left["decisions"], plan["chunk"]["decisions"]) < 2
                ):
                    result["terminal_reason"] = "insufficient_settlement_allowance"
                    break
                ordinal += 1
                output = root / "runs" / f"segment-{ordinal:03d}"
                output.mkdir(mode=0o700, parents=True)
                _record(
                    output / "PLAN.json",
                    dict(
                        partition="development",
                        actual_parent=str(parent),
                        source_sha256=context["state_sha256"],
                        context_sha256=c.digest(parent / "CONTEXT.json"),
                        inherited_spent=spent,
                        configuration_sha256=configuration.sha256,
                        **({"fit_allowed": plan["fit_allowed"], "copy_back": plan["copy_back"]}
                           if plan.get("compare_evolution_recipient_yield") or
                              plan.get("compare_successful_fishing_site_effort") else {}),
                        **player_wiring_declaration(plan),
                        source_identity=c.source_code_identity(c.REPO),
                        same_live_emulator=True,
                        state_restoration=False,
                    ),
                )
                source_payload, factory, menu, holder, source = assemble_configured_player(
                    backend,
                    configuration,
                    parent,
                    output,
                    plan_path=output / "PLAN.json",
                    model_feature_version=model.feature_version,
                    live_party_runtime=holder["runtime"],
                    **(
                        {"include_preparation_party_context": True}
                        if declared_preparation_context(plan) or getattr(
                            declared_readiness_refinement(plan).get("consequence_head"),
                            "context_projection",
                            None,
                        )
                        == "prospective_preparation_party_context_v1"
                        else {}
                    ),
                    **({"required_species": tuple(plan["required_species"])}
                       if "required_species" in plan else {}),
                )
                if source_payload != controller.save_state_bytes():
                    raise ValueError("live runtime renewal changed the retained native state")
                factory(ReadOnlyController(controller))
                if suppression is not None:
                    if not isinstance(menu, NativeStoryBranchInventory):
                        raise ValueError("safe-stop continuation requires the native story menu")
                    menu.safe_stop_suppression = suppression
                connect_declared_machine_options(
                    menu, plan, rom=c.ROM.read_bytes(), holder=holder, configuration=configuration
                )
                cash_left = (
                    None
                    if limits.cash_debits is None
                    else max(0, limits.cash_debits - spent["cash_debits"])
                )
                chunk = NativePlayerLimits(
                    **{
                        key: min(left[key], plan["chunk"][key])
                        for key in ("decisions", "actions", "frames", "seconds")
                    },
                    heals=left["heals"],
                    cash_debits=cash_left,
                )
                row, context = execute_player_chunk(
                    plan=plan,
                    configuration=configuration,
                    c=c,
                    emulator=controller,
                    factory=factory,
                    menu=menu,
                    holder=holder,
                    source=source,
                    output=output,
                    model=model,
                    limits=chunk,
                    memory=memory,
                    store=store,
                    ordinal=ordinal,
                )
                episode = row.get("episode", {})
                episodes.append(compact_handoff_episode(episode))
                reason = chunk_continuation_reason(
                    row,
                    source_sha256=json.loads((parent / "CONTEXT.json").read_bytes())[
                        "state_sha256"
                    ],
                )
                if declared_automatic_renewal(plan) and reason == "declared_consequence_complete":
                    task_handoff = qualified_registration_task_handoff(
                        row, plan=plan, runtime=holder["runtime"], output=output)
                    if task_handoff is not None:
                        row["qualified_registration_task_handoff"] = task_handoff
                        reason = "automatic_registration_task_renewal"
                if declared_automatic_renewal(plan) and reason == "native_execution_error":
                    handoff = qualified_menu_control_handoff(
                        row, runtime=holder["runtime"], menu=menu, retained_parent=output,
                        catcher_plan=plan, failure_reason=reason, rom=lambda: c.ROM.read_bytes(),
                    )
                    if handoff is not None:
                        row["qualified_native_control_handoff"] = handoff
                        pending_control_handoffs.append(handoff)
                        reason = "automatic_control_recovery"
                if (
                    row.get("field_ready") is True
                    and row.get("error") is None
                    and episode.get("stop_reason") != "execution_failed"
                ):
                    from pokemon_red_completion.red_capture_switch_handoff import confirmed_catcher_settlement
                    outstanding = []
                    for pending in pending_control_handoffs:
                        if pending.get("ordinary_capture_switch_faint") is not True:
                            recovered_control_handoffs.append(pending)
                        else:
                            settled = confirmed_catcher_settlement(pending, episode)
                            if settled is None:
                                outstanding.append(pending)
                            else:
                                recovered_control_handoffs.append(settled)
                    pending_control_handoffs[:] = outstanding
                if suppression is not None and context is not None:
                    signature = qualified_safe_stop_setback(
                        row, runtime=holder["runtime"], reason=reason
                    ) or qualified_movement_stall_setback(
                        row, runtime=holder["runtime"], reason=reason
                    )
                    key = json.dumps(signature)
                    repeat = safe_stop_repeats.get(key, 0) + 1
                    if (
                        signature is not None
                        and len(safe_stop_setbacks) < safe_stop["maximum_total"]
                        and repeat <= safe_stop["maximum_repeats"]
                    ):
                        # A settled, custody-verified failure becomes an ordinary
                        # setback: its kind is withheld for a few menus and the
                        # model chooses again. No input, budget reset or retry.
                        safe_stop_repeats[key] = repeat
                        suppression.hold(GoalKind(signature[0]), safe_stop["hold_menus"])
                        receipt = dict(
                            schema="pokemon.red.safe-stop-setback.v1",
                            segment=ordinal,
                            original_reason=reason,
                            selected_kind=signature[0],
                            error_type=signature[1],
                            error=signature[2],
                            repeat=repeat,
                            state_sha256=row["state_sha256"],
                            held_kind=signature[0],
                            hold_menus=safe_stop["hold_menus"],
                            inputs=0,
                            frames=0,
                            model_queries=0,
                            aggregate_budget_reset=False,
                        )
                        row["qualified_safe_stop_setback"] = receipt
                        safe_stop_setbacks.append(receipt)
                        reason = "automatic_safe_stop_setback"
                row["continuation_reason"] = reason
                _record(output / "RESULT.json", row)
                if context is None:
                    # A chunk that failed before capturing a continuation has no
                    # successor state. Record a clean terminal instead of crashing;
                    # the chunk's own RESULT.json keeps the original error.
                    result["segments"].append(
                        dict(segment=ordinal, native_facts=row.get("native_facts"), spent=None,
                             continuation_reason=reason, error=row.get("error"))
                    )
                    result.update(
                        ready=False, passed=False, terminal_reason="chunk_failed_without_continuation",
                        terminal_error=row.get("error"),
                    )
                    break
                spent, facts = context["spent"], row["native_facts"]
                result["segments"].append(
                    dict(
                        segment=ordinal, native_facts=facts, spent=spent, continuation_reason=reason
                    )
                )
                result.update(
                    ready=model_handoff_verified(
                        episodes, recovered_control_handoffs=recovered_control_handoffs
                    ),
                    native_facts=facts,
                    spent=spent,
                    passed=model_handoff_verified(
                        episodes, recovered_control_handoffs=recovered_control_handoffs
                    ),
                    verified_automatic_control_recoveries=recovered_control_handoffs,
                    pending_automatic_control_recoveries=pending_control_handoffs,
                    **(
                        dict(
                            safe_stop_setbacks=safe_stop_setbacks,
                            safe_stop_suppression=suppression.public_dict(),
                        )
                        if suppression is not None
                        else {}
                    ),
                )
                print(
                    json.dumps(
                        dict(
                            segment=ordinal,
                            facts=facts,
                            decisions=spent["decisions"],
                            continuation_reason=reason,
                        )
                    ),
                    flush=True,
                )
                if (
                    reason not in AUTOMATIC_CONTINUATIONS
                    and reason != "automatic_safe_stop_setback"
                ):
                    result["terminal_reason"] = reason
                    if reason != "curriculum_complete":
                        result.update(ready=False, passed=False)
                    result["official_completion_candidate"] = fresh_official_completion_candidate(
                        plan, result, reason
                    )
                    break
                parent = output
            result["released"] = not controller.pressed_buttons
    except BaseException as error:
        result.update(passed=False, ready=False, error_type=type(error).__name__, error=str(error))
        raise
    finally:
        result.update(
            worker_stopped=emulator is not None and emulator._backend is None,
            seconds=monotonic() - started,
        )
        _record(root / "RESULT.json", result)
        print(json.dumps(result), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True)
    run(parser.parse_args().plan)
