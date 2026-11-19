"""Durable configuration around the current native player, not a new planner.

The legacy assembly is an explicit dependency. Configuration survives a fresh
process; executable availability exclusions never become policy features.
"""

import json
from dataclasses import asdict, dataclass, fields, replace
from hashlib import sha256
from pathlib import Path

from .goal_manager import GoalAvailability, GoalKind, GoalOpportunity, GoalUnavailableReason
from .goal_manager_runtime import GoalBindingSet
from .provenance import canonical_sha256
from .red_player_gym import pending_gym_reward_binding
from .red_player_party_guard import RedPlayerPartyGuard, RetainedPartyGoalStateAdapter
from .red_player_party_loan import party_loan_return_binding, restore_guarded_party_loan

SCHEMA = "pokemon.red.configured-native-player.v1"
ROUTE_WORK_SCHEMA = "pokemon.red.configured-native-player.v2"
VENUE_SCHEMA = "pokemon.red.configured-native-player.v3"
HELPER_VENUE_SCHEMA = "pokemon.red.configured-native-player.v4"
PREPARATION_QUANTUM_SCHEMA = "pokemon.red.configured-native-player.v5"
NO_LOAN_SCHEMA = "pokemon.red.configured-native-player.v6"
WILD_TRAIN_RECOVERY_SCHEMA = "pokemon.red.configured-native-player.v7"
VENUE_SCOPE_NAMES = frozenset({"route11", "digletts_cave", "mansion"})
ASSEMBLY_FLAGS = frozenset(
    {
        "continuous_travel",
        "include_preparation",
        "include_supply",
        "include_rewards",
        "include_early_preparation",
        "protect_party_species",
        "include_silph_continuation",
        "silph_useful_moves",
    }
)


def player_lifecycle_fields(*, scope, released, guest_backend_closed):
    """Describe an in-process boundary; never attest the host process exited.

    ``worker_stopped`` is retained only as a deprecated guest-backend alias.
    Chunk completion and released inputs permit same-emulator continuation;
    actual host exit still requires the supervisor/OS evidence outside Python.
    """
    scopes = {"live_chunk", "diagnostic_chunk", "driver_terminal", "prelaunch_failure"}
    if (
        type(scope) is not str
        or scope not in scopes
        or type(released) is not bool
        or guest_backend_closed is not None
        and type(guest_backend_closed) is not bool
    ):
        raise ValueError("invalid measured player lifecycle boundary")
    return dict(
        worker_stopped=guest_backend_closed is True,
        live_driver_running=scope in {"live_chunk", "diagnostic_chunk"},
        checkpoint_lifecycle=dict(
            schema="pokemon.red.checkpoint-quiescence.v1",
            scope=scope,
            chunk_complete=True,
            inputs_released=released,
            guest_backend_closed=guest_backend_closed,
            host_process_exit_confirmed=False,
            unexpected_guest_closure=(
                scope in {"live_chunk", "diagnostic_chunk"} and guest_backend_closed is True
            ),
        ),
    )


def checkpoint_quiescent(result):
    """Check a released checkpoint, not worker/guest/host termination.

    Old retained rows preserve their original released/stopped compatibility
    semantics. Neither that legacy flag nor this predicate proves process exit.
    A new lifecycle block is strict and cannot fall back after invalid data.
    Source-specific state, cost, field/battle and custody checks remain callers'.
    """
    if not isinstance(result, dict) or result.get("released") is not True:
        return False
    if "checkpoint_lifecycle" not in result:
        return result.get("worker_stopped") is True
    life = result["checkpoint_lifecycle"]
    if (
        type(life) is not dict
        or set(life)
        != {
            "schema",
            "scope",
            "chunk_complete",
            "inputs_released",
            "guest_backend_closed",
            "host_process_exit_confirmed",
            "unexpected_guest_closure",
        }
        or life.get("schema") != "pokemon.red.checkpoint-quiescence.v1"
        or life.get("chunk_complete") is not True
        or life.get("inputs_released") is not True
        or life.get("host_process_exit_confirmed") is not False
    ):
        return False
    try:
        expected = player_lifecycle_fields(
            scope=life.get("scope"),
            released=True,
            guest_backend_closed=life.get("guest_backend_closed"),
        )
    except (ValueError, TypeError):
        return False
    return (
        life == expected["checkpoint_lifecycle"]
        and result.get("worker_stopped") is expected["worker_stopped"]
        and result.get("live_driver_running") is expected["live_driver_running"]
    )


def _sha(value):
    return (
        isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)
    )


@dataclass(frozen=True)
class RedPlayerConfiguration:
    origin_sha256: str
    origin_id: str
    goal_model_sha256: str
    assembly_flags: tuple[tuple[str, bool], ...]
    excluded_profiles: tuple[tuple[str, str], ...]
    loanable_specimen_refs: tuple[str, ...]
    quote_capture_route_work: bool = False
    evolution_venue_model_sha256: str | None = None
    evolution_venue_scope: tuple[str, ...] = ()
    evolution_allow_direct_fights: bool = True
    preparation_encounter_quantum: int | None = None
    evolution_recover_wild_faints: bool = False

    def __post_init__(self):
        from .red_player_preparation_binding import preparation_encounter_limits

        preparation_encounter_limits(self.preparation_encounter_quantum)
        if type(self.evolution_recover_wild_faints) is not bool:
            raise ValueError("configured training faint recovery requires an explicit boolean")
        if type(self.evolution_allow_direct_fights) is not bool:
            raise ValueError("configured evolution mode requires an explicit boolean")
        if not self.evolution_allow_direct_fights and self.evolution_venue_model_sha256 is None:
            raise ValueError("helper-only evolution requires its configured venue model")
        _validate_venue_configuration(self.evolution_venue_model_sha256, self.evolution_venue_scope)
        if type(self.quote_capture_route_work) is not bool:
            raise ValueError("configured route-work projection requires an explicit boolean")
        if (
            not _sha(self.origin_sha256)
            or not _sha(self.goal_model_sha256)
            or not isinstance(self.origin_id, str)
            or not self.origin_id
        ):
            raise ValueError("configured player requires its origin and frozen goal model")
        if (
            type(self.assembly_flags) is not tuple
            or len(self.assembly_flags) != len(ASSEMBLY_FLAGS)
            or any(
                type(p) is not tuple or len(p) != 2 or type(p[1]) is not bool
                for p in self.assembly_flags
            )
            or set(dict(self.assembly_flags)) != ASSEMBLY_FLAGS
        ):
            raise ValueError("configured player requires every explicit boolean assembly flag")
        if (
            type(self.excluded_profiles) is not tuple
            or any(
                type(p) is not tuple
                or len(p) != 2
                or p[0] not in {k.value for k in GoalKind}
                or not _sha(p[1])
                for p in self.excluded_profiles
            )
            or len(set(self.excluded_profiles)) != len(self.excluded_profiles)
        ):
            raise ValueError("configured player exclusions must name exact kind/profile pairs")
        if (
            type(self.loanable_specimen_refs) is not tuple
            or len(self.loanable_specimen_refs) > 1
            or any(not isinstance(ref, str) or not ref for ref in self.loanable_specimen_refs)
        ):
            raise ValueError(
                "configured player permits zero or one declared temporary reserve loan"
            )

    def to_dict(self):
        values = asdict(self)
        if not self.quote_capture_route_work:
            values.pop("quote_capture_route_work")
        if self.evolution_venue_model_sha256 is None:
            values.pop("evolution_venue_model_sha256")
            values.pop("evolution_venue_scope")
        if self.evolution_allow_direct_fights:
            values.pop("evolution_allow_direct_fights")
        if self.preparation_encounter_quantum is None:
            values.pop("preparation_encounter_quantum")
        if not self.evolution_recover_wild_faints:
            values.pop("evolution_recover_wild_faints")
        schema = (
            PREPARATION_QUANTUM_SCHEMA
            if self.preparation_encounter_quantum is not None
            else HELPER_VENUE_SCHEMA
            if not self.evolution_allow_direct_fights
            else VENUE_SCHEMA
            if self.evolution_venue_model_sha256 is not None
            else ROUTE_WORK_SCHEMA
            if self.quote_capture_route_work
            else SCHEMA
        )
        if not self.loanable_specimen_refs:
            schema = NO_LOAN_SCHEMA
        if self.evolution_recover_wild_faints:
            schema = WILD_TRAIN_RECOVERY_SCHEMA
        return dict(schema=schema, **values)

    @classmethod
    def from_dict(cls, document):
        optional = {
            "quote_capture_route_work",
            "evolution_venue_model_sha256",
            "evolution_venue_scope",
            "evolution_allow_direct_fights",
            "preparation_encounter_quantum",
            "evolution_recover_wild_faints",
        }
        names = {entry.name for entry in fields(cls)} - optional
        if not isinstance(document, dict):
            raise ValueError("configured player document schema differs")
        schema = document.get("schema")
        recovery = schema == WILD_TRAIN_RECOVERY_SCHEMA
        no_loan = schema == NO_LOAN_SCHEMA or (
            recovery and document.get("loanable_specimen_refs") in ([], ())
        )
        quantum = schema == PREPARATION_QUANTUM_SCHEMA or (
            (no_loan or recovery) and "preparation_encounter_quantum" in document
        )
        helper_only = schema == HELPER_VENUE_SCHEMA or (
            (quantum or no_loan or recovery) and "evolution_allow_direct_fights" in document
        )
        venue = schema in {VENUE_SCHEMA, HELPER_VENUE_SCHEMA} or (
            (quantum or no_loan or recovery)
            and bool({"evolution_venue_model_sha256", "evolution_venue_scope"} & set(document))
        )
        route = (
            schema == ROUTE_WORK_SCHEMA
            or (venue or quantum or no_loan or recovery)
            and "quote_capture_route_work" in document
        )
        expected = {"schema", *names}
        if recovery:
            expected.add("evolution_recover_wild_faints")
        if quantum:
            expected.add("preparation_encounter_quantum")
        if route:
            expected.add("quote_capture_route_work")
        if venue:
            expected.update(("evolution_venue_model_sha256", "evolution_venue_scope"))
        if helper_only:
            expected.add("evolution_allow_direct_fights")
        if (
            schema
            not in {
                SCHEMA,
                ROUTE_WORK_SCHEMA,
                VENUE_SCHEMA,
                HELPER_VENUE_SCHEMA,
                PREPARATION_QUANTUM_SCHEMA,
                NO_LOAN_SCHEMA,
                WILD_TRAIN_RECOVERY_SCHEMA,
            }
            or recovery
            and document.get("evolution_recover_wild_faints") is not True
            or (no_loan and document.get("loanable_specimen_refs") not in ([], ()))
            or (not no_loan and document.get("loanable_specimen_refs") in ([], ()))
            or quantum
            and document.get("preparation_encounter_quantum") is None
            or helper_only
            and document.get("evolution_allow_direct_fights") is not False
            or set(document) != expected
            or route
            and document["quote_capture_route_work"] is not True
            or venue
            and (
                not _sha(document["evolution_venue_model_sha256"])
                or type(document["evolution_venue_scope"]) not in (list, tuple)
            )
        ):
            raise ValueError("configured player document schema differs")
        return cls(
            origin_sha256=document["origin_sha256"],
            origin_id=document["origin_id"],
            goal_model_sha256=document["goal_model_sha256"],
            assembly_flags=tuple(tuple(pair) for pair in document["assembly_flags"]),
            excluded_profiles=tuple(tuple(pair) for pair in document["excluded_profiles"]),
            loanable_specimen_refs=tuple(document["loanable_specimen_refs"]),
            quote_capture_route_work=route,
            evolution_venue_model_sha256=document["evolution_venue_model_sha256"]
            if venue
            else None,
            evolution_venue_scope=tuple(document["evolution_venue_scope"]) if venue else (),
            evolution_allow_direct_fights=not helper_only,
            evolution_recover_wild_faints=recovery,
            preparation_encounter_quantum=document["preparation_encounter_quantum"]
            if quantum
            else None,
        )

    @property
    def sha256(self):
        return canonical_sha256(self.to_dict())

    def admits(self, binding):
        return not any(
            binding.kind.value == kind
            and (
                binding.binding_ref.endswith(":" + profile)
                or binding.binding_ref.endswith(":config-" + profile)
            )
            for kind, profile in self.excluded_profiles
        )


def connect_retained_route22_recovery(backend, holder):
    """Reuse exact retained rival executors before ordinary field routing.

    The legacy early-trainer dispatcher excludes the second rival. Its existing
    late-rival callback already owns the qualified actor; expose that callback
    only after the exact cartridge introduction has been observed. No approach,
    strategic query or model change belongs to this control bridge. Tower's
    already-active rival uses its existing public contract and the unchanged
    actor supplied to the early-trainer dispatcher.
    """
    previous = getattr(backend, "retained_early_trainer_binding", None)
    retained = holder.get("retained_trainer_binding")
    if not callable(previous) or not callable(retained):
        return
    previous = getattr(previous, "configured_route22_fallback", previous)

    def recover(runtime, actions, *, rom, battler):
        from .red_player_route22_rival import retained_second_route22_contract

        if retained_second_route22_contract(rom, runtime.reader) is not None:
            return retained(runtime, actions)
        read = getattr(runtime.reader, "read", None)
        raw = read() if callable(read) else None
        if raw is not None:
            from .observation import MapId

            if raw.map_id == int(MapId.POKEMON_TOWER_2F) and raw.battle_state == 2:
                from .red_player_engaged_story import engaged_story_binding

                # The public executor authenticates the starter branch, active
                # trainer and unbeaten event. This already active battle does
                # not require the later Silph Scope/Fuji quest prerequisite.
                # It supplies no
                # approach or full-quest credit; unknown contracts still fail.
                binding = engaged_story_binding(
                    runtime,
                    actions,
                    rom=rom,
                    battler=battler,
                    objective_id="rescue_fuji",
                    allow_retained_tower=True,
                )
                if binding is not None:
                    return binding
        return previous(runtime, actions, rom=rom, battler=battler)

    recover.configured_route22_fallback = previous
    backend.retained_early_trainer_binding = recover


def connect_retained_ordinary_funding(runtime, battler):
    """Expose existing earned-income skills with the same qualified player actor.

    Resource peers already admit exhausted ordinary-ball stock before the League.
    They still need a qualified battle owner at that phase. This binds capability
    only: live route, cash, trainer, party and native-return guards still decide
    availability, and the goal model retains every other executable alternative.
    """
    from .red_learned_trainer import (
        FROZEN_K_SHA256,
        K_QUALIFICATION_SHA256,
        FrozenTrainerBattler,
    )

    if (
        not isinstance(battler, FrozenTrainerBattler)
        or battler.model_sha256 != FROZEN_K_SHA256
        or battler.qualification_sha256 != K_QUALIFICATION_SHA256
        or runtime.league_story_battle_controller is not None
    ):
        return runtime
    runner = runtime.trainer_battle_runner
    if runner is not None and (
        runner != battler.run
        or runtime.trainer_battle_model_sha256 != battler.model_sha256
        or runtime.trainer_battle_qualification_sha256 != battler.qualification_sha256
    ):
        return runtime
    try:
        battler.require_funding_scope()
    except ValueError:
        return runtime
    return replace(
        runtime,
        trainer_battle_runner=battler.run,
        trainer_battle_model_sha256=battler.model_sha256,
        trainer_battle_qualification_sha256=battler.qualification_sha256,
        trainer_funding_recovery=True,
        trainer_funding_ledges=True,
        trainer_funding_surf=True,
        trainer_funding_indoor_departure=True,
    )


def declared_native_evolution_venue_model(plan, configuration=None, *, production_train_scope=None):
    """Load a declared existing local scorer without fitting or changing saves."""
    spec = plan.get("native_evolution_venue_model")
    raw = plan.get("configuration", plan.get("configuration_template", {}))
    if configuration is not None:
        expected = configuration.evolution_venue_model_sha256
        scope = configuration.evolution_venue_scope
    else:
        raw = raw if isinstance(raw, dict) else {}
        expected = raw.get("evolution_venue_model_sha256")
        scope = raw.get("evolution_venue_scope", ())
    if expected is None and not scope and spec is None:
        return None
    if expected is None:
        raise ValueError("native venue model lacks an explicit configured identity")
    _validate_venue_configuration(expected, tuple(scope) if type(scope) in (list, tuple) else scope)
    if production_train_scope is not None:
        from .red_scoped_train_composition import ProductionSequenceTrainScope
        if type(production_train_scope) is not ProductionSequenceTrainScope:
            raise TypeError("typed production TRAIN sequence scope required")
        production_train_scope.require_plan(plan)
    if (
        (plan.get("partition") != "development" and production_train_scope is None)
        or not isinstance(spec, dict)
        or set(spec) != {"path", "content_sha256", "reason"}
        or not isinstance(spec["path"], str)
        or not Path(spec["path"]).is_absolute()
        or not _sha(spec["content_sha256"])
        or not isinstance(spec["reason"], str)
        or not spec["reason"].strip()
    ):
        raise ValueError("native venue model requires a pinned DEVELOPMENT declaration")
    from .party_development_outcome_learning import load_party_development_outcome_model
    from .red_native_boxed_evolution import validate_native_evolution_venue_model

    model = load_party_development_outcome_model(
        spec["path"], expected_sha256=spec["content_sha256"]
    )
    validate_native_evolution_venue_model(model, expected)
    return model


def declared_ordinary_preparation_venue_policy(plan):
    """Explicit, pinned opt-in for the distinct ordinary K training protocol."""
    spec = plan.get("ordinary_preparation_venue_model")
    if spec is None:
        return None
    if (plan.get("partition") not in ("train", "development")
        or not isinstance(spec, dict)
        or set(spec) not in (
            {"path", "content_sha256", "model_sha256", "scope", "reason"},
            {"path", "content_sha256", "model_sha256", "scope", "reason", "task_contract"},
        )
        or not isinstance(spec.get("task_contract", "native-level-dose-v1"), str)
        or spec.get("task_contract", "native-level-dose-v1") not in {
            "native-level-dose-v1", "party-development.fixed-level-ready-task-cost.v1"
        }
        or not isinstance(spec["path"], str) or not Path(spec["path"]).is_absolute()
        or not _sha(spec["content_sha256"]) or not _sha(spec["model_sha256"])
        or spec["scope"] != "all-existing-legal-ordinary-preparation-venues"
        or not isinstance(spec["reason"], str) or not spec["reason"].strip()):
        raise ValueError("ordinary venue policy requires a pinned TRAIN or DEVELOPMENT declaration")
    from .party_development_outcome_learning import load_party_development_outcome_model
    from .party_development_rank import PARTY_DEVELOPMENT_MATCHUP_FEATURE_SCHEMA_ID
    from .red_ordinary_preparation_venue import OrdinaryPreparationVenuePolicy
    model = load_party_development_outcome_model(spec["path"], expected_sha256=spec["content_sha256"])
    if model.feature_schema_id != PARTY_DEVELOPMENT_MATCHUP_FEATURE_SCHEMA_ID:
        raise ValueError("ordinary venue policy requires the matchup schema")
    return OrdinaryPreparationVenuePolicy(
        model, spec["model_sha256"], spec.get("task_contract", "native-level-dose-v1")
    )


def _validate_venue_configuration(model_sha256, scope):
    if model_sha256 is None and scope == ():
        return
    if (
        not _sha(model_sha256)
        or type(scope) is not tuple
        or len(scope) < 2
        or any(type(name) is not str or name not in VENUE_SCOPE_NAMES for name in scope)
        or len(set(scope)) != len(scope)
    ):
        raise ValueError(
            "native venue configuration requires its model identity and distinct scope"
        )


def declared_evolution_recipient_yield(plan, venue_model):
    enabled = plan.get("compare_evolution_recipient_yield", False)
    from .red_collection_campaign_scope import development_campaign_scope
    if enabled is True and development_campaign_scope(plan):
        if venue_model is None:
            raise ValueError("campaign venue observation requires the frozen venue model")
        return True
    if type(enabled) is not bool or (enabled and (
        venue_model is None
        or plan.get("partition") != "development"
        or plan.get("diagnostic_only") is not True
        or plan.get("fit_allowed") is not False or plan.get("copy_back") is not False
        or plan.get("new_campaign") is not False or plan.get("official_acceptance") is not False
        or plan.get("actual_gameplay_resume_authorized", False) is not False
    )):
        raise ValueError("venue yield comparison requires a declared non-fitting development copy")
    return enabled


def _configured_native_venue_policy(configuration, model, *, compare_recipient_yield=False):
    if configuration.evolution_venue_model_sha256 is None:
        if compare_recipient_yield:
            raise ValueError("venue yield comparison requires the frozen model")
        if model is not None:
            raise ValueError("native venue model lacks an explicit configured identity")
        return None
    from . import red_goal_context as context
    from .red_native_boxed_evolution import NativeEvolutionVenuePolicy

    venues = dict(
        route11=context.ROUTE_11_TRAINING_VENUE,
        digletts_cave=context.DIGLETTS_CAVE_TRAINING_VENUE,
        mansion=context.MANSION_TRAINING_VENUE,
    )
    return NativeEvolutionVenuePolicy(
        model,
        configuration.evolution_venue_model_sha256,
        tuple(venues[name] for name in configuration.evolution_venue_scope),
        allow_direct_evolution=configuration.evolution_allow_direct_fights,
        compare_recipient_yield=compare_recipient_yield,
    )


def _failed_wild_acquisition_faint(reader, result, outcome):
    """Recognize ordinary recovery applicability; this grants no escape."""
    from .red_capture_switch_handoff import qualified_catcher_parent
    if not isinstance(outcome, dict):
        return False
    chain = outcome.get("error_chain", ())
    catcher_switch_faint = (
        outcome.get("error_type") == "ProtectedRecoveryError"
        and outcome.get("error") == "capture protected catcher target fainted during the switch."
        and len(chain) == 1 and isinstance(chain[0], dict)
        and chain[0].get("error_type") == "ProtectedRecoveryError"
        and chain[0].get("error") == outcome.get("error")
        and (outcome.get("before") or {}).get("battle_state") == 0
        and (outcome.get("after") or {}).get("battle_state") == 1
    )
    if not (
        outcome.get("selected_kind") == "acquire_species"
        and (catcher_switch_faint or (
            outcome.get("error_type") == "RouteExecutionError"
            and chain and isinstance(chain[0], dict)
            and chain[0].get("error_type") == "RouteExecutionError"
            and chain[0].get("reason_code") == "world_state_diverged"
        ))
        and (result.get("continuation_reason") == "native_execution_error"
             or catcher_switch_faint and qualified_catcher_parent(result, outcome))
        and checkpoint_quiescent(result)
    ):
        return False
    raw = reader.read()
    active = getattr(raw, "active_party_index", None)
    hp = getattr(raw, "party_hp", None)
    if not (
        raw.battle_state == 1 and type(active) is int and hp
        and 0 <= active < len(hp) and hp[active] == 0 and any(hp)
    ):
        return False
    if catcher_switch_faint:
        observed = (outcome["after"].get("diagnostics") or {})
        before = outcome["before"]
        if (
            result.get("field_ready") is not False
            or observed.get("map_id") != raw.map_id
            or observed.get("active_party_index") != active
            or tuple(observed.get("party_hp") or ()) != tuple(hp)
            or observed.get("enemy_species_id") != raw.enemy_species_id
            or before.get("owned_species") != outcome["after"].get("owned_species")
            or before.get("cash") != outcome["after"].get("cash")
        ):
            return False
    retained_identity = getattr(reader, "read_retained_wild_identity", None)
    identity = retained_identity() if callable(retained_identity) else None
    original = getattr(identity, "original_species_id", None)
    # The same conservative native one-off identities used by party escape,
    # including Route12 Snorlax and transformed originals. No current-species
    # fallback can waive a missing or malformed capture allocation.
    from .observation import GEN1_INTERNAL_SPECIES_IDS

    return (type(original) is int and original in GEN1_INTERNAL_SPECIES_IDS
            and original not in {73, 74, 75, 131, 132})


def _failed_fuji_facing_encounter(reader, result, outcome):
    """Recognize the released ordinary encounter left by the old Fuji turn."""
    from .observation import MapId, RawGameState
    from .red_player_tower import fuji_phase

    raw = reader.read()
    before, after = outcome.get("before") or {}, outcome.get("after") or {}
    observed = after.get("diagnostics") or {}
    if (
        not isinstance(raw, RawGameState)
        or raw.map_id != MapId.POKEMON_TOWER_7F
        or raw.battle_state != 1
        or not checkpoint_quiescent(result)
        or result.get("field_ready") is not False
        or result.get("continuation_reason") != "native_execution_error"
        or outcome.get("selected_kind") != GoalKind.ADVANCE_STORY.value
        or outcome.get("error_type") != "RedPCStorageError"
        or outcome.get("error") != "PC facing did not preserve its bound position"
        or outcome.get("failure_phase") != "execution"
        or before.get("battle_state") != 0
        or after.get("battle_state") != 1
        or after.get("buttons_released") is not True
        or (observed.get("map_id"), observed.get("player_y"), observed.get("player_x"))
           != (raw.map_id, raw.player_y, raw.player_x)
    ):
        return False
    # Read-only phase check against the current cartridge facts. This does not
    # claim field control or write any battle or story memory.
    return fuji_phase(replace(raw, battle_state=0)) == ("rescue", 4, 149)


def _retained_lorelei_dialogue_inventory(runtime, actions, parent):
    """Admit the proved old terminal after a native Lorelei rematch win."""
    from .actions import MacroAction, MacroActionKind
    from .goal_manager import GoalFailureReason
    from .goal_manager_runtime import ExecutableGoalBinding, GoalExecutionReport, GoalVerification
    from .observation import EventFlag, MapId, event_flag_is_set
    from .red_player_field_goals import _field_ready
    from .red_player_lesson import capture_player_lesson_snapshot

    reader = runtime.reader
    raw = reader.read()
    if (
        raw.map_id != MapId.LORELEIS_ROOM or raw.battle_state != 0
        or raw.battle_result != 0 or not any(raw.party_hp or ())
        or not raw.event_flags or not event_flag_is_set(raw.event_flags, int(EventFlag.BEAT_LORELEI))
        or not reader.read_input_readiness().ready or not reader.read_bottom_dialogue_box_visible()
        or runtime.emulator.pressed_buttons
    ):
        return None
    parent = Path(parent)
    files = tuple(parent / n for n in ('RESULT.json', 'CONTEXT.json', 'terminal.state'))
    if not all(p.is_file() for p in files):
        return None
    result_bytes, context_bytes, state = (p.read_bytes() for p in files)
    result, context = json.loads(result_bytes), json.loads(context_bytes)
    state_hash = sha256(state).hexdigest()
    if (
        state != runtime.emulator.save_state_bytes() or not checkpoint_quiescent(result)
        or result.get('continuation_reason') != 'native_execution_error'
        or result.get('field_ready') is not False
        or result.get('state_sha256') != state_hash or context.get('state_sha256') != state_hash
        or result.get('context_sha256') != sha256(context_bytes).hexdigest()
        or result.get('spent') != context.get('spent') or context.get('cash') != raw.player_money
    ):
        return None
    outcomes = result.get('episode', {}).get('outcomes', ())
    outcome = outcomes[-1] if outcomes else {}
    if (
        outcome.get('selected_kind') != GoalKind.ADVANCE_STORY.value
        or outcome.get('error_type') != 'TrainerBattleLifecycleError'
        or outcome.get('error') != 'party, inventory or HP integrity changed'
        or outcome.get('terminal_state_sha256') != state_hash
        or outcome.get('after', {}).get('cash') != raw.player_money
        or raw.player_money - outcome.get('before', {}).get('cash', raw.player_money) != 5544
    ):
        return None
    witnesses = []
    for path in parent.glob('league-defeat_lorelei/*/endpoint.json'):
        endpoint = json.loads(path.read_bytes())
        if endpoint.get('final_state_sha256') != state_hash or endpoint.get('actor_returned_win') is not True:
            continue
        battle_bytes = path.with_name('outcome.json').read_bytes()
        battle = json.loads(battle_bytes)
        if (canonical_sha256(battle) == endpoint.get('outcome_sha256')
                and battle.get('battle_won') is True and battle.get('stop_reason') == 'battle_won'
                and battle.get('final_battle_state') == 0):
            witnesses.append(path)
    if len(witnesses) != 1:
        return None

    before, before_lesson = capture_player_lesson_snapshot(runtime)
    before_dex = reader.read_pokedex_state().owned_species
    terminal = None
    consumed = False

    def check_boundary():
        now = reader.read()
        for key in ('map_id', 'player_x', 'player_y', 'battle_state', 'battle_result',
                    'party_species_ids', 'party_levels', 'party_hp', 'party_max_hp',
                    'party_status', 'party_pp', 'party_moves', 'bag_items', 'player_money', 'badge_bits'):
            if getattr(raw, key) != getattr(now, key):
                raise ValueError('retained Lorelei dialogue changed protected state')
        if not event_flag_is_set(now.event_flags, int(EventFlag.BEAT_LORELEI)):
            raise ValueError('retained Lorelei dialogue lost its verified event')

    def execute():
        nonlocal consumed, terminal
        if consumed or runtime.emulator.save_state_bytes() != state:
            raise ValueError('retained Lorelei dialogue is stale')
        consumed = True
        start_actions, start_frames = actions.actions_executed, runtime.emulator.frame_count
        for _ in range(16):
            check_boundary()
            if _field_ready(runtime):
                break
            if reader.read_bottom_dialogue_box_visible():
                actions.execute(MacroAction(MacroActionKind.CONFIRM))
            actions.execute(MacroAction(MacroActionKind.WAIT, repeat=96))
        check_boundary()
        after, after_lesson = capture_player_lesson_snapshot(runtime)
        if (
            not _field_ready(runtime) or before_lesson != after_lesson
            or before.collection_observation != after.collection_observation
            or before_dex != reader.read_pokedex_state().owned_species
        ):
            raise ValueError('retained Lorelei dialogue failed field and progress verification')
        terminal = runtime.emulator.save_state_bytes()
        return GoalExecutionReport(
            actions.actions_executed - start_actions, runtime.emulator.frame_count - start_frames,
            dict(model_queries=0, source_state_sha256=state_hash, retained_native_win=True),
        )

    def verify(report):
        if terminal is not None and terminal == runtime.emulator.save_state_bytes() and _field_ready(runtime):
            return GoalVerification.succeeded()
        return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)

    binding = ExecutableGoalBinding('pokemon.red:retained-lorelei-dialogue:' + state_hash,
                                    GoalKind.RECOVER_CONTROL, 0.04, 0.02, execute, verify)
    blocked = GoalOpportunity(binding.binding_ref + ':settlement-only', GoalKind.ADVANCE_STORY,
                              GoalAvailability.UNAVAILABLE,
                              unavailable_reason=GoalUnavailableReason.TEMPORARILY_BLOCKED)
    return GoalBindingSet((binding.opportunity, blocked), (binding,))


def _retained_capture_inventory(runtime, actions, *, parent, output):
    """Reconnect an exact paused allocation before any ordinary wild exit.

    This is the existing one-off executor and journal verifier. A journal from
    another state cannot authorize a new encounter or reset its throw budget.
    """
    read = getattr(getattr(runtime, "reader", None), "read", None)
    if not callable(read) or read().battle_state != 1:
        return None
    parent = Path(parent)
    state = runtime.emulator.save_state_bytes()
    if state != (parent / "terminal.state").read_bytes():
        return None
    # An export can fail before inputs and create a new paired checkpoint but
    # no new capture journal. Reconnect only its authenticated, byte-identical
    # zero-input ancestry; the current caller keeps every later cost/context.
    seen = set()
    for _ in range(32):
        receipts = tuple(parent.glob("snorlax-*/*-paused/receipt.json")) + tuple(
            parent.glob("static-*/*-paused/receipt.json")
        )
        if receipts:
            break
        if parent in seen:
            raise ValueError("retained capture ancestry cycles")
        seen.add(parent)
        if not (parent / "PLAN.json").is_file():
            return None
        plan = json.loads((parent / "PLAN.json").read_bytes())
        prior = plan.get("actual_parent")
        if prior is None:
            return None
        prior = Path(prior)
        if not prior.is_absolute():
            raise ValueError("retained capture ancestry must be absolute")
        context_bytes = (parent / "CONTEXT.json").read_bytes()
        context = json.loads(context_bytes)
        result = json.loads((parent / "RESULT.json").read_bytes())
        prior_bytes = (prior / "CONTEXT.json").read_bytes()
        prior_context = json.loads(prior_bytes)
        prior_state = (prior / "terminal.state").read_bytes()
        # Stop ancestry discovery at authenticated work in a non-capture goal.
        # A later ordinary travel encounter is not a zero-input child of an old
        # paused capture. Never cross this boundary to reuse an old allocation.
        outcomes = result.get("episode", {}).get("outcomes", ())
        last = outcomes[-1] if isinstance(outcomes, (list, tuple)) and outcomes else None
        if (
            state != prior_state
            and isinstance(last, dict)
            and (
                last.get("selected_kind") in {"resupply", "restore_team", "manage_storage", "develop_team", "evolve_species"}
                or (
                    plan.get("partition") == "development"
                    and (
                        _failed_wild_acquisition_faint(runtime.reader, result, last)
                        or _failed_fuji_facing_encounter(runtime.reader, result, last)
                    )
                )
            )
            and last.get("terminal_state_sha256") == sha256(state).hexdigest()
            and plan.get("source_sha256") == sha256(prior_state).hexdigest()
            and context.get("state_sha256") == sha256(state).hexdigest()
            and result.get("state_sha256") == sha256(state).hexdigest()
            and result.get("context_sha256") == sha256(context_bytes).hexdigest()
            and result.get("spent") == context.get("spent")
            and plan.get("context_sha256") == sha256(prior_bytes).hexdigest()
            and prior_context.get("state_sha256") == plan["source_sha256"]
            and plan.get("inherited_spent") == prior_context.get("spent")
            and all(type(context["spent"].get(key)) is int
                    and type(prior_context["spent"].get(key)) is int
                    and context["spent"][key] > prior_context["spent"][key]
                    for key in ("actions", "frames"))
        ):
            return None
        if (
            state != prior_state
            or plan.get("source_sha256") != sha256(state).hexdigest()
            or context.get("state_sha256") != plan["source_sha256"]
            or result.get("state_sha256") != plan["source_sha256"]
            or result.get("context_sha256") != sha256(context_bytes).hexdigest()
            or result.get("spent") != context.get("spent")
            or plan.get("context_sha256") != sha256(prior_bytes).hexdigest()
            or prior_context.get("state_sha256") != plan["source_sha256"]
            or plan.get("inherited_spent") != prior_context.get("spent")
            or any(context["spent"].get(key) != prior_context["spent"].get(key)
                   for key in ("actions", "frames"))
        ):
            raise ValueError("retained capture ancestry differs from zero-input source")
        parent = prior
    else:
        raise ValueError("retained capture ancestry exceeds finite bound")
    from red_earned_run_completion_20261005 import retained_capture_binding

    binding = retained_capture_binding(runtime, actions, parent=parent, output=output)
    if (
        binding is None
        or binding.kind is not GoalKind.RECOVER_CONTROL
        or binding.binding_ref != "pokemon.red:retained-capture:" + sha256(state).hexdigest()
    ):
        raise ValueError("retained capture inventory lacks its exact verified binding")
    blocked = GoalOpportunity(
        binding.binding_ref + ":settlement-only",
        GoalKind.ADVANCE_STORY,
        GoalAvailability.UNAVAILABLE,
        unavailable_reason=GoalUnavailableReason.TEMPORARILY_BLOCKED,
    )
    return GoalBindingSet((binding.opportunity, blocked), (binding,))


def _retained_wild_faint_inventory(runtime, actions, *, parent, rom, failed_result=None):
    """Resume only an authenticated failed wild tail through existing Run support.

    This offers control settlement, never a strategic action or a healed copy.
    The whole-party executor owns encounter, PP, inventory and surviving-party
    conservation; one-off captures retain their separate journal authority.
    """
    read = getattr(getattr(runtime, "reader", None), "read", None)
    if not callable(read):
        return None
    raw = read()
    active = getattr(raw, "active_party_index", None)
    if (
        raw.battle_state != 1
        or type(active) is not int
        or not raw.party_hp
        or not 0 <= active < len(raw.party_hp)
        or raw.party_hp[active] != 0
        or not any(raw.party_hp)
    ):
        return None
    parent = Path(parent)
    if (failed_result is None and not (parent / "RESULT.json").is_file()) or not all(
        (parent / name).is_file() for name in ("CONTEXT.json", "terminal.state")
    ):
        return None
    state = runtime.emulator.save_state_bytes()
    context_bytes = (parent / "CONTEXT.json").read_bytes()
    result = json.loads((parent / "RESULT.json").read_bytes()) if failed_result is None else failed_result
    context = json.loads(context_bytes)
    state_sha = sha256(state).hexdigest()
    if (
        state != (parent / "terminal.state").read_bytes()
        or not checkpoint_quiescent(result)
        or result.get("state_sha256") != state_sha
        or context.get("state_sha256") != state_sha
        or result.get("context_sha256") != sha256(context_bytes).hexdigest()
        or result.get("spent") != context.get("spent")
    ):
        return None
    outcomes = result.get("episode", {}).get("outcomes", ())
    if not outcomes:
        return None
    outcome = outcomes[-1]
    from .red_capture_switch_handoff import qualified_catcher_parent
    if result.get("continuation_reason") != "native_execution_error" and not qualified_catcher_parent(result, outcome):
        return None
    chain = outcome.get("error_chain", ())
    legacy_route_faint = (
        outcome.get("error_type") == "RouteExecutionError"
        and chain and type(chain[0]) is dict
        and chain[0].get("error_type") == "RouteExecutionError"
        and chain[0].get("reason_code") == "world_state_diverged"
    )
    if (
        outcome.get("terminal_state_sha256") != state_sha
        or not (legacy_route_faint or _failed_wild_acquisition_faint(runtime.reader, result, outcome))
    ):
        return None
    from .red_player_wild_recovery import interrupted_wild_binding

    binding = interrupted_wild_binding(
        runtime,
        actions,
        rom=rom() if callable(rom) else rom,
        allow_fainted_active=True,
    )
    if binding is None:
        return None
    blocked = GoalOpportunity(
        binding.binding_ref + ":settlement-only",
        GoalKind.ADVANCE_STORY,
        GoalAvailability.UNAVAILABLE,
        unavailable_reason=GoalUnavailableReason.TEMPORARILY_BLOCKED,
    )
    return GoalBindingSet((binding.opportunity, blocked), (binding,))


def _retained_field_blackout_inventory(runtime, actions, *, parent, failed_result=None):
    """Expose only the recorded, still pending native field blackout."""
    read = getattr(getattr(runtime, "reader", None), "read", None)
    if not callable(read):
        return None
    raw = read()
    if raw.battle_state != 0 or not raw.party_hp or any(raw.party_hp):
        return None
    parent = Path(parent)
    result_path = parent / "RESULT.json"
    if (failed_result is None and not result_path.is_file()) or not (parent / "terminal.state").is_file():
        return None
    result = failed_result if failed_result is not None else json.loads(result_path.read_bytes())
    outcomes = result.get("episode", {}).get("outcomes", ())
    if not outcomes or not checkpoint_quiescent(result):
        return None
    last = outcomes[-1]
    reason = result.get("continuation_reason")
    if failed_result is None and reason != "native_execution_error":
        receipt = result.get("qualified_native_control_handoff") or {}
        if (
            reason != "automatic_control_recovery"
            or receipt.get("schema") != "pokemon.red.qualified-native-control-handoff.v1"
            or receipt.get("retained_field_blackout") is not True
            or receipt.get("qualified") is not True
            or receipt.get("state_sha256") != result.get("state_sha256")
            or receipt.get("failed_outcome_sha256") != canonical_sha256(last)
            or receipt.get("binding_ref") != "pokemon.red:field-blackout:" + str(result.get("state_sha256"))
            or receipt.get("strategic_substitution") is not False
            or receipt.get("failed_transport_preserved") is not True
            or any(receipt.get(k) != 0 for k in ("inputs", "frames", "model_queries"))
        ):
            return None
    if (
        result.get("field_ready") is not False
        or last.get("selected_kind") != GoalKind.RESTORE_TEAM.value
        or last.get("error_type") != "Gen1FieldBlackoutPending"
        or last.get("error") != "observed all-party field poison faint requires native blackout"
        or last.get("terminal_state_sha256") != result.get("state_sha256")
    ):
        return None
    state = runtime.emulator.save_state_bytes()
    if state != (parent / "terminal.state").read_bytes() or sha256(state).hexdigest() != result["state_sha256"]:
        return None
    from .red_player_field_blackout import field_blackout_binding

    binding = field_blackout_binding(runtime, actions)
    if binding is None:
        return None
    blocked = GoalOpportunity(
        binding.binding_ref + ":settlement-only",
        GoalKind.ADVANCE_STORY,
        GoalAvailability.UNAVAILABLE,
        unavailable_reason=GoalUnavailableReason.TEMPORARILY_BLOCKED,
    )
    return GoalBindingSet((binding.opportunity, blocked), (binding,))


def _retained_field_faint_inventory(runtime, actions, *, parent, failed_result=None):
    """Read the exact failed native parent before offering compulsory settlement."""
    read = getattr(getattr(runtime, "reader", None), "read", None)
    if not callable(read) or read().battle_state != 0:
        return None
    parent = Path(parent)
    if (failed_result is None and not (parent / "RESULT.json").is_file()) or not (
        parent / "terminal.state"
    ).is_file():
        return None
    state = runtime.emulator.save_state_bytes()
    if state != (parent / "terminal.state").read_bytes():
        return None
    result = (
        json.loads((parent / "RESULT.json").read_bytes())
        if failed_result is None
        else failed_result
    )
    handoff = result.get("qualified_native_control_handoff") or {}
    qualified_live_faint = (
        result.get("continuation_reason") == "automatic_control_recovery"
        and handoff.get("schema") == "pokemon.red.qualified-native-control-handoff.v1"
        and handoff.get("qualified") is True
        and (
            (handoff.get("retained_declared_loan") is True
             and handoff.get("field_faint_before_pc_return") is True)
            or (handoff.get("retained_funding_faint") is True
                and handoff.get("failed_outcome_sha256")
                == canonical_sha256((result.get("episode", {}).get("outcomes") or [{}])[-1]))
        )
        and handoff.get("state_sha256") == result.get("state_sha256")
        and handoff.get("binding_ref")
        == "pokemon.red:retained-motion:" + str(result.get("state_sha256"))
        and handoff.get("strategic_substitution") is False
        and all(handoff.get(k) == 0 for k in ("inputs", "frames", "model_queries"))
    )
    if (
        not checkpoint_quiescent(result)
        or result.get("state_sha256") != sha256(state).hexdigest()
        or (
            failed_result is None
            and result.get("continuation_reason") != "native_execution_error"
            and not qualified_live_faint
        )
    ):
        return None
    outcomes = result.get("episode", {}).get("outcomes", ())
    if not outcomes:
        return None
    from .red_player_forced_motion import retained_field_faint_binding

    prior_native = None
    boundary_path = parent / "retained-native-field-boundary.json"
    if boundary_path.is_file():
        prior_native = json.loads(boundary_path.read_bytes())
        boundary_state = parent / "retained-native-field-boundary.state"
        if (
            prior_native.get("retained_tail_sha256") != sha256(state).hexdigest()
            or prior_native.get("source_chunk_state_sha256")
            != outcomes[0].get("before_state_sha256")
            or not boundary_state.is_file()
            or sha256(boundary_state.read_bytes()).hexdigest()
            != prior_native.get("native_final_state_sha256")
        ):
            return None
    last = outcomes[-1]
    if (
        last.get("selected_kind") == "evolve_species"
        and last.get("error_type") == "RedGoalContextError"
        and last.get("error") == "PC loan settlement requires settled field control"
    ):
        from .red_player_party_guard import RedPlayerPartyGuard

        guard = getattr(runtime.adapter, "party_guard", None)
        if (
            not isinstance(guard, RedPlayerPartyGuard)
            or len(guard.loanable_refs) != 1
            or set(guard.refs) - set(guard.reader.preparation_specimen_refs())
            != set(guard.loanable_refs)
        ):
            return None
        guard.verify()
        diagnostic = json.loads((parent / "native" / "diagnostic-events.json").read_bytes())
        costs = json.loads((parent / "native" / "native-costs.json").read_bytes())
        prior_native = dict(
            schema="pokemon.red.retained-loan-poison.v1",
            named_loan_verified=True,
            events=diagnostic["events"],
            native_frames=costs["frames"],
        )
    binding = retained_field_faint_binding(
        runtime, actions, outcome=last, prior_native_boundary=prior_native
    )
    if binding is None:
        return None
    blocked = GoalOpportunity(
        binding.binding_ref + ":settlement-only",
        GoalKind.ADVANCE_STORY,
        GoalAvailability.UNAVAILABLE,
        unavailable_reason=GoalUnavailableReason.TEMPORARILY_BLOCKED,
    )
    return GoalBindingSet((binding.opportunity, blocked), (binding,))


def local_ordinary_ball_supply_profile(profile, mart_map_id):
    """Reuse the verified local clerk and the existing affordable five-ball order."""
    from .observation import ItemId, MapId
    from .red_goal_context_profile import (
        RedGoalMechanic,
        _thaw,
        build_red_goal_context_profile_payload,
        parse_red_goal_context_profile,
    )

    profile_ids = {
        int(MapId.PEWTER_MART): "whole-player-local-pewter-ordinary-balls-v1",
        int(MapId.CERULEAN_MART): "whole-player-local-cerulean-ordinary-balls-v1",
        int(MapId.VERMILION_MART): "whole-player-local-vermilion-ordinary-balls-v1",
    }
    if type(mart_map_id) is not int or mart_map_id not in profile_ids:
        raise ValueError("ordinary ball supplier needs a verified clerk catalog entry")
    providers = [
        (spec.kind, spec.mechanic, _thaw(spec.parameters))
        for spec in profile.providers
        if spec.kind is not GoalKind.RESUPPLY
    ]
    providers.append(
        (
            GoalKind.RESUPPLY,
            RedGoalMechanic.MART_RESUPPLY,
            dict(
                map_id=mart_map_id,
                player_x=2,
                player_y=5,
                interaction_direction="left",
                purchases=[
                    dict(
                        absolute_index=0, item_id=int(ItemId.POKE_BALL), quantity=5, unit_price=200
                    )
                ],
                affordable_ball_purchase=True,
                resource_choice_variants=True,
            ),
        )
    )
    providers.sort(key=lambda row: tuple(GoalKind).index(row[0]))
    return parse_red_goal_context_profile(
        build_red_goal_context_profile_payload(
            profile_id=profile_ids[mart_map_id],
            providers=tuple(providers),
        )
    )


def local_ordinary_ball_supply_peers(
    runtime, actions, observation, *, world, _town=None, interruption_handler_wrapper=None
):
    """Quote every verified ordinary-ball clerk through the existing router.

    Route availability, exact affordable quotes, cash and native purchase
    verification remain unchanged. No preferred town or purchase is selected.
    The private locality argument only preserves the old Vermilion helper API.
    """
    from .observation import MapId
    from .red_player_collection_options import ordinary_ball_resupply_peer_needed
    from .red_resource_goal_router import RedResourceGoalRouter

    raw = observation.raw
    if raw.battle_state or not observation.input_ready:
        return ()
    # Capability data, not a supplied strategic ordering: every clerk here has
    # native-verified stance (2,5), LEFT, ordinary ball stock index zero at 200.
    # Pewter reuses the stance/stock the existing Pewter chapter purchase
    # verifies natively (cerulean._purchase_early_supplies; ROM stock 0x2449).
    # Without it, a Pewter-side ball shortage could only quote the Viridian
    # clerk back through the forest (fresh-save opus55-fresh-b: 323 actions).
    # The current route quote decides reachability for every verified clerk;
    # no current-town filter hides a legitimate nearby supplier from the model.
    catalog = (
        (int(MapId.PEWTER_CITY), int(MapId.PEWTER_MART)),
        (int(MapId.CERULEAN_CITY), int(MapId.CERULEAN_MART)),
        (int(MapId.VERMILION_CITY), int(MapId.VERMILION_MART)),
    )
    outside = runtime.reader.read_retained_outside_map()
    matches = [
        mart
        for town, mart in catalog
        if _town is None
        or (
            town == _town
            and (
                raw.map_id == town
                or raw.map_id == mart
                or type(raw.map_id) is int
                and raw.map_id >= 0x25
                and outside == town
            )
        )
    ]
    completed = set(runtime.adapter.graph.completed_ids(observation.game_state))
    # Pewter is the one clerk the cheap route planner can reach before the
    # story does (it ignores the scripted Oak's-lab rival exit). Native F17
    # fresh runs chose that quote at decision 0 and failed on the scripted
    # dialogue. Admit it only after the verified arrival objective, the same
    # stage at which the other clerks first become route-reachable.
    story_gate = {int(MapId.PEWTER_MART): "reach_pewter"}
    matches = [mart for mart in matches if story_gate.get(mart, None) in (None, *completed)]
    if not matches:
        return ()
    if not ordinary_ball_resupply_peer_needed(
        raw,
        hall_of_fame="enter_hall_of_fame" in completed,
    ):
        return ()
    world = world.with_current_observation(runtime.reader)
    bindings = []
    for mart_map_id in matches:
        configured = replace(
            runtime, profile=local_ordinary_ball_supply_profile(runtime.profile, mart_map_id)
        )
        inventory = RedResourceGoalRouter(
            configured,
            actions,
            world,
            quote_resource_costs=True,
            prepare_capture_party=False,
            prepare_capture_escort=False,
            include_recovery_offers=False,
            interruption_handler_wrapper=interruption_handler_wrapper,
        ).enumerate_routed_kinds(observation, frozenset({GoalKind.RESUPPLY}))
        bindings.extend(
            binding for binding in inventory.bindings if binding.kind is GoalKind.RESUPPLY
        )
    return tuple(bindings)


def local_vermilion_ball_supply_profile(profile):
    """Compatibility view of the existing verified Vermilion capability."""
    from .observation import MapId

    return local_ordinary_ball_supply_profile(profile, int(MapId.VERMILION_MART))


def local_vermilion_ball_supply_peers(runtime, actions, observation, *, world):
    """Preserve the original Vermilion-only helper contract."""
    from .observation import MapId

    return local_ordinary_ball_supply_peers(
        runtime, actions, observation, world=world, _town=int(MapId.VERMILION_CITY)
    )


def connect_early_capture_status_support(runtime):
    """Reuse optional non-damaging preparation, even without a status helper.

    The existing preparer can select a healthy catcher and throw directly. It
    never substitutes the legacy damaging Tackle fallback or requires ownership
    of a sleep/paralysis move. Nonlethal damage support is not enabled here.
    """
    from .red_living_dex_wild_corridor import bind_red_optional_capture_status_profile

    return replace(runtime, profile=bind_red_optional_capture_status_profile(runtime.profile))


def _bind_required_registration_targets(runtime, required_species):
    """Bind declared planning demand without inputs or imported global credit."""
    if required_species is None:
        return runtime
    if runtime.registration_policy is None:
        raise ValueError("declared species require a registered player runtime")
    policy = replace(
        runtime.registration_policy,
        completion_scope="local_red",
        target_species=required_species,
    )
    runtime = replace(runtime, registration_policy=policy)
    runtime.adapter.registration_policy = policy
    return runtime


def assemble_configured_player(
    backend,
    configuration,
    parent,
    output,
    *,
    plan_path,
    model_feature_version=7,
    evolution_venue_model=None,
    training_admission=None,
    scoped_train_composition=None,
    production_train_scope=None,
    include_preparation_party_context=False,
    required_species=None,
    live_party_runtime=None,
):
    """Reuse the existing composition with persistent admission and loan wiring."""
    if not isinstance(configuration, RedPlayerConfiguration):
        raise TypeError("typed player configuration required")
    if type(model_feature_version) is not int or model_feature_version not in (
        5,
        6,
        7,
        8,
        9,
        10,
        11,
        13,
        14,
        15,
        16,
    ):
        raise ValueError("configured player requires a supported model feature version")
    if type(include_preparation_party_context) is not bool or (
        include_preparation_party_context and model_feature_version not in (15, 16)
    ):
        raise ValueError("preparation party context requires explicit V15 observation opt-in")
    if required_species is not None:
        from .red_collection import RED_SOLO_COLLECTION_CONTRACT

        if (
            type(required_species) is not tuple
            or not required_species
            or any(type(s) is not str for s in required_species)
            or len(set(required_species)) != len(required_species)
            or not set(required_species) <= set(RED_SOLO_COLLECTION_CONTRACT.species_universe)
        ):
            raise ValueError("configured planning requires distinct declared local species")
    if configuration.evolution_venue_model_sha256 is not None and evolution_venue_model is None:
        evolution_venue_model = declared_native_evolution_venue_model(
            json.loads(Path(plan_path).read_bytes()), configuration,
            **({"production_train_scope": production_train_scope} if production_train_scope is not None else {})
        )
    assembly_plan = json.loads(Path(plan_path).read_bytes()) if Path(plan_path).is_file() else {}
    compare_yield = declared_evolution_recipient_yield(assembly_plan, evolution_venue_model)
    if compare_yield and any(scope is not None for scope in (training_admission, scoped_train_composition, production_train_scope)):
        raise ValueError("venue yield comparison cannot use a TRAIN scope")
    venue_policy = _configured_native_venue_policy(
        configuration, evolution_venue_model, compare_recipient_yield=compare_yield,
    )
    ordinary_venue_policy = declared_ordinary_preparation_venue_policy(assembly_plan)
    if ordinary_venue_policy is not None and training_admission is not None:
        raise ValueError("ordinary venue model cannot use the single-map production TRAIN admission")
    if training_admission is not None:
        from .red_production_train_admission import ProductionTrainAdmission

        if type(training_admission) is not ProductionTrainAdmission:
            raise TypeError("typed production TRAIN admission required")
        training_admission.require_work_order(Path(plan_path).read_bytes())
        if (
            configuration.origin_sha256 != training_admission.source_origin_sha256
            or configuration.origin_id != training_admission.root_lineage_id
        ):
            raise ValueError("configured TRAIN origin differs from admitted source")
    if scoped_train_composition is not None:
        from .red_scoped_train_composition import ScopedTrainComposition

        if (
            type(scoped_train_composition) is not ScopedTrainComposition
            or training_admission is not None
        ):
            raise TypeError("explicit scoped TRAIN composition cannot mix production admission")
        scoped_train_composition.require_source(
            (Path(parent) / "terminal.state").read_bytes(),
            (Path(parent) / "CONTEXT.json").read_bytes(),
            Path(plan_path).read_bytes(),
            origin_sha=configuration.origin_sha256,
            origin_id=configuration.origin_id,
        )
    if production_train_scope is not None:
        from .red_scoped_train_composition import ProductionSequenceTrainScope
        if (type(production_train_scope) is not ProductionSequenceTrainScope
                or training_admission is not None or scoped_train_composition is not None):
            raise ValueError("production TRAIN sequence cannot mix assembly scopes")
        production_train_scope.require_assembly(payload=(Path(parent)/"terminal.state").read_bytes(),
            context_bytes=(Path(parent)/"CONTEXT.json").read_bytes(),work_order_bytes=Path(plan_path).read_bytes(),
            origin_sha=configuration.origin_sha256,origin_id=configuration.origin_id)
    preparation_history_enabled = (json.loads(Path(plan_path).read_bytes()).get(
        "retain_story_preparation_opposition", False) if Path(plan_path).is_file() else False)
    if type(preparation_history_enabled) is not bool:
        raise ValueError("retained story preparation must be an explicit boolean")
    if preparation_history_enabled and getattr(backend, "PREPARATION_LOSS_OBSERVER_SUPPORTED", False) is not True:
        raise ValueError("selected backend lacks retained preparation observation support")
    from .red_income_preparation import configure_native_owned_stock_income

    income_declaration = (json.loads(Path(plan_path).read_bytes())
        if Path(plan_path).is_file() else {})
    if income_declaration.get("native_owned_stock_income") is not None and (
        training_admission is not None or scoped_train_composition is not None
    ):
        raise ValueError("native owned-stock income is not TRAIN admission")
    configure_native_owned_stock_income(backend, income_declaration,
        **({"production_train_scope": production_train_scope} if production_train_scope is not None else {}))
    bird_return_refs = _interrupted_bird_loan_refs(parent, configuration)
    effective_loan_refs = bird_return_refs or frozenset(configuration.loanable_specimen_refs)
    payload, factory0, menu, holder, source = backend.assembly(
        parent,
        output,
        plan_path=plan_path,
        **({"production_train_scope": production_train_scope} if production_train_scope is not None else {}),
        **({"ordinary_preparation_venue_policy": ordinary_venue_policy} if ordinary_venue_policy is not None else {}),
        **({"training_admission": training_admission} if training_admission is not None else {}),
        **(
            {"scoped_train_composition": scoped_train_composition}
            if scoped_train_composition is not None
            else {}
        ),
        origin_sha=configuration.origin_sha256,
        origin_id=configuration.origin_id,
        continuation_loan_refs=effective_loan_refs,
        **({"quote_capture_route_work": True} if configuration.quote_capture_route_work else {}),
        **(
            {"preparation_encounter_quantum": configuration.preparation_encounter_quantum}
            if configuration.preparation_encounter_quantum is not None
            else {}
        ),
        **({"include_level_workload": True} if model_feature_version >= 9 else {}),
        **({"include_capture_invocation": True} if model_feature_version >= 13 else {}),
        **({"include_matchup_observation": True} if model_feature_version >= 15 else {}),
        **(
            {"include_preparation_party_context": True} if include_preparation_party_context else {}
        ),
        **dict(configuration.assembly_flags),
    )
    # Callers authenticate the parent against RESULT before assembly; the backend
    # factory reobserves that paired state/context before this carrier can act.
    # Never infer a commitment from a chapter or overwrite its failure count.
    context_path = Path(parent) / "CONTEXT.json"
    if context_path.is_file():
        context = json.loads(context_path.read_bytes())
        if "story_kind_commitment" in context:
            from .red_story_kind_commitment import StoryKindCommitmentCarrier

            holder["story_kind_commitment_carrier"] = StoryKindCommitmentCarrier.from_document(
                context["story_kind_commitment"],
                completed_objectives=context["lesson"]["completed_objectives"],
            )
    if (context_path.is_file() and context.get("preparation_story_loss") is not None
            and not preparation_history_enabled):
        raise ValueError("carried story preparation cannot silently disable its declaration")
    if preparation_history_enabled:
        if source.get("partition") not in {"train", "development"}:
            raise ValueError("retained preparation is an explicit TRAIN/DEVELOPMENT repair")
        from .red_player_preparation_history import RetainedStoryDefeat, StoryPreparationHistory

        saved = context.get("preparation_story_loss") if context_path.is_file() else None
        preparation_history = StoryPreparationHistory.from_document(saved,
            expected_lineage=configuration.origin_id, expected_partition=source["partition"])
        holder["preparation_story_history"] = preparation_history
        from .red_player_preparation_history import connect_story_preparation_observation
        connect_story_preparation_observation(holder, preparation_history)
        holder["observe_preparation_loss"] = lambda runtime, observation, latest: preparation_history.preparation_loss(
            runtime, observation, latest, holder)
    if scoped_train_composition is not None and (
        source.get("partition") != "train"
        or source.get("state_sha256") != scoped_train_composition.source_state_sha256
        or source.get("origin_sha256") != scoped_train_composition.source_origin_sha256
        or source.get("source_commit") != scoped_train_composition.source_commit
    ):
        raise ValueError("configured scoped TRAIN source differs")
    if model_feature_version >= 10:
        from .red_player_owned_machines import connect_move_change_inventory

        connect_move_change_inventory(menu, rom=backend.c.ROM.read_bytes())
    connect_retained_route22_recovery(backend, holder)
    if (
        training_admission is None
        and menu.enumerate_resources is not None
        and dict(configuration.assembly_flags)["include_supply"]
        and dict(configuration.assembly_flags)["include_rewards"]
    ):
        regional_resources = menu.enumerate_resources

        def resources_with_local_mart(runtime, actions, observation):
            from .red_player_story_menu import merge_resource_observer_bindings

            rows = regional_resources(runtime, actions, observation)
            route = holder.get("configured_route")
            def shop_transport(inner, spec):
                from .red_player_engaged_story import EngagedStoryRouteHandler

                return EngagedStoryRouteHandler(
                    inner,
                    runtime.reader,
                    lambda: backend.retained_early_trainer_binding(
                        runtime, actions, rom=route.rom,
                        battler=holder.get("scoped_native_train_group", holder["actor"]),
                    ),
                    maximum_trainers=32,
                )

            local = (
                ()
                if route is None
                else local_ordinary_ball_supply_peers(
                    runtime, actions, observation, world=route.route_world,
                    interruption_handler_wrapper=(
                        shop_transport if dict(configuration.assembly_flags)["include_early_preparation"]
                        else None
                    ),
                )
            )
            return merge_resource_observer_bindings(rows + local)

        menu.enumerate_resources = resources_with_local_mart
    if training_admission is None:
        from .red_indoor_departure_plan import indoor_departure_binding

        def empty_indoor_recovery(runtime, actions, observation):
            route = holder.get("configured_route")
            return (
                None if route is None else indoor_departure_binding(runtime, actions, route=route)
            )

        menu.enumerate_empty_recovery = empty_indoor_recovery
    carrier_enabled = (
        json.loads(Path(plan_path).read_bytes()).get("owned_field_carrier_exchange", False)
        if Path(plan_path).is_file()
        else False
    )
    if type(carrier_enabled) is not bool:
        raise ValueError("owned field-carrier permission must be boolean")
    if carrier_enabled and (training_admission is not None or scoped_train_composition is not None):
        raise ValueError("field-carrier exchange is a declared DEVELOPMENT capability")
    if carrier_enabled:
        from .red_field_carrier import field_carrier_branches
        from .red_field_carrier_custody import active_carrier_preparation

        original_branches = menu.enumerate_branches

        def branches_with_carrier(runtime, actions, observation):
            rows = original_branches(runtime, actions, observation)
            route = holder.get("configured_route")
            if route is None:
                return rows
            plan = holder.get("plan")
            combat = frozenset(m.specimen_ref for m in plan.roster if m.purpose.value == "combat")

            def committed(custody):
                holder["plan"] = active_carrier_preparation(plan, runtime, custody)

            return rows + field_carrier_branches(
                runtime,
                actions,
                observation,
                rom=backend.c.ROM.read_bytes(),
                route=route,
                combat_refs=combat,
                preparation=plan,
                on_commit=committed,
            )

        menu.enumerate_branches = branches_with_carrier

    def returned_field_carrier(custody):
        from .red_field_carrier_custody import restored_carrier_preparation

        holder["plan"] = restored_carrier_preparation(
            custody, holder["runtime"], rom=backend.c.ROM.read_bytes()
        )

    def aborted_field_carrier_return(custody):
        from .red_field_carrier_custody import aborted_active_carrier_preparation
        projected = aborted_active_carrier_preparation(custody, holder["runtime"])
        projection_sha = canonical_sha256(asdict(projected))
        holder["plan"] = projected
        return projection_sha

    ordinary, supplements = menu.enumerate_base, menu.supplements

    def enumerate_allowed(*args):
        if training_admission is None and scoped_train_composition is None and production_train_scope is None:
            retained = _retained_field_blackout_inventory(args[0], args[1], parent=parent)
            if retained is not None:
                return retained
        retained = _retained_field_faint_inventory(args[0], args[1], parent=parent)
        if retained is not None:
            return retained
        if training_admission is None and scoped_train_composition is None and production_train_scope is None:
            from .red_survey_faint_settlement import retained_survey_faint_inventory

            faint = retained_survey_faint_inventory(
                args[0], args[1], parent=parent, rom=lambda: backend.c.ROM.read_bytes()
            )
            if faint is not None:
                return faint
        if training_admission is None and scoped_train_composition is None and production_train_scope is None:
            from .red_faint_recovery import retained_field_item_menu
            item_menu = retained_field_item_menu(args[0], args[1], parent)
            if item_menu is not None:
                return item_menu
        retained = _retained_capture_inventory(args[0], args[1], parent=parent, output=output)
        if retained is not None:
            return retained
        if training_admission is None:
            retained = _retained_lorelei_dialogue_inventory(args[0], args[1], parent)
            if retained is not None:
                return retained
            retained = _retained_wild_faint_inventory(
                args[0],
                args[1],
                parent=parent,
                rom=lambda: backend.c.ROM.read_bytes(),
            )
            if retained is not None:
                return retained
            from .red_indoor_departure_plan import native_ship_departure_binding

            departure = native_ship_departure_binding(args[0], args[1])
            if departure is not None:
                blocked = GoalOpportunity(
                    departure.binding_ref + ":settlement-only",
                    GoalKind.ADVANCE_STORY,
                    GoalAvailability.UNAVAILABLE,
                    unavailable_reason=GoalUnavailableReason.TEMPORARILY_BLOCKED,
                )
                return GoalBindingSet((departure.opportunity, blocked), (departure,))
        if "configured_route" in holder:
            runtime, actions, _ = args
            from .red_field_carrier_return_abort import retained_field_carrier_return_abort_binding
            aborted_return = retained_field_carrier_return_abort_binding(
                runtime, actions, parent=parent, on_abort=aborted_field_carrier_return,
            )
            if aborted_return is not None:
                blocked = GoalOpportunity(
                    aborted_return.binding_ref + ":settlement-only", GoalKind.ADVANCE_STORY,
                    GoalAvailability.UNAVAILABLE,
                    unavailable_reason=GoalUnavailableReason.TEMPORARILY_BLOCKED,
                )
                return GoalBindingSet((aborted_return.opportunity, blocked), (aborted_return,))
            loan = party_loan_return_binding(
                runtime,
                actions,
                holder["configured_route"].route_world,
                on_field_return=returned_field_carrier,
            )
            if loan is not None:
                blocked = GoalOpportunity(
                    loan.binding_ref + ":settlement-only",
                    GoalKind.ADVANCE_STORY,
                    GoalAvailability.UNAVAILABLE,
                    unavailable_reason=GoalUnavailableReason.TEMPORARILY_BLOCKED,
                )
                return GoalBindingSet((loan.opportunity, blocked), (loan,))
            pending = pending_gym_reward_binding(runtime, actions, route=holder["configured_route"])
            if pending is not None:
                blocked = GoalOpportunity(
                    pending.binding_ref + ":settlement-only",
                    GoalKind.ADVANCE_STORY,
                    GoalAvailability.UNAVAILABLE,
                    unavailable_reason=GoalUnavailableReason.TEMPORARILY_BLOCKED,
                )
                return GoalBindingSet((pending.opportunity, blocked), (pending,))
        inventory = ordinary(*args)
        if (
            carrier_enabled
            and "configured_route" in holder
            and not any(b.kind is GoalKind.MANAGE_STORAGE for b in inventory.bindings)
        ):
            from .red_field_carrier import field_carrier_return_binding

            unavailable_return = []
            binding = field_carrier_return_binding(
                args[0], args[1], route=holder["configured_route"], on_return=returned_field_carrier,
                on_unavailable=unavailable_return.append,
            )
            if binding is not None:
                inventory = GoalBindingSet(
                    tuple(
                        o for o in inventory.opportunities if o.kind is not GoalKind.MANAGE_STORAGE
                    )
                    + (binding.opportunity,),
                    inventory.bindings + (binding,),
                )
            elif unavailable_return:
                inventory = GoalBindingSet(
                    tuple(o for o in inventory.opportunities if o.kind is not GoalKind.MANAGE_STORAGE)
                    + tuple(unavailable_return), inventory.bindings,
                )
        admitted = tuple(b for b in inventory.bindings if configuration.admits(b))
        if admitted == inventory.bindings:
            return inventory
        # Preserve every other offer and its unavailability evidence.
        excluded_refs = {b.binding_ref for b in inventory.bindings if not configuration.admits(b)}
        record = getattr(args[1], "record_diagnostic_event", None)
        if callable(record):
            record(
                "configured_goal_exclusions",
                dict(
                    selection_authority="deterministic_capability_guard",
                    reason="declared_profile_exclusion",
                    binding_refs=sorted(excluded_refs),
                ),
            )
        opportunities = tuple(
            GoalOpportunity(
                o.binding_ref,
                o.kind,
                GoalAvailability.UNAVAILABLE,
                unavailable_reason=GoalUnavailableReason.MISSING_CAPABILITY,
            )
            if o.binding_ref in excluded_refs
            else o
            for o in inventory.opportunities
        )
        return replace(inventory, bindings=admitted, opportunities=opportunities)

    def supplements_allowed(*args):
        rows = supplements(*args)
        admitted = tuple(row for row in rows if configuration.admits(row.binding))
        record = getattr(args[1], "record_diagnostic_event", None)
        if callable(record):
            excluded = [
                row.binding.binding_ref for row in rows if not configuration.admits(row.binding)
            ]
            if excluded:
                record(
                    "configured_goal_exclusions",
                    dict(
                        selection_authority="deterministic_capability_guard",
                        reason="declared_profile_exclusion",
                        binding_refs=sorted(excluded),
                    ),
                )
        return admitted

    menu.enumerate_base, menu.supplements = enumerate_allowed, supplements_allowed

    def factory(controller):
        runtime = factory0(controller)
        commitment_carrier = holder.get("story_kind_commitment_carrier")
        if commitment_carrier is not None and commitment_carrier.current is not None:
            runtime.adapter.graph.objective(commitment_carrier.current.objective_ref)
        runtime = _bind_required_registration_targets(runtime, required_species)
        flags = dict(configuration.assembly_flags)
        if (
            training_admission is None
            and flags["include_rewards"]
            and flags["include_early_preparation"]
        ):
            runtime = connect_early_capture_status_support(runtime)
        if flags["include_rewards"] and flags["include_supply"]:
            runtime = connect_retained_ordinary_funding(runtime, holder.get("actor"))
        state = controller.save_state_bytes()
        from .red_party import PokemonRedPartyReader

        reader = PokemonRedPartyReader(controller)
        pending_loan = not effective_loan_refs <= set(
            reader.preparation_specimen_refs()
        )
        custody_document = (
            json.loads((Path(parent) / "CONTEXT.json").read_bytes()).get("field_carrier")
            if (Path(parent) / "CONTEXT.json").is_file()
            else None
        )
        if custody_document is not None:
            from .red_field_carrier_custody import FieldCarrierCustody, restore_custody_guard

            if not carrier_enabled:
                raise ValueError("field-carrier continuation needs its declared capability")
            custody = FieldCarrierCustody.from_private_dict(custody_document)
            guard = restore_custody_guard(runtime, custody, rom=backend.c.ROM.read_bytes())
            if custody.phase == "pending":
                holder["plan"] = custody.preparation_before
        elif pending_loan and live_party_runtime is not None:
            guard = _same_guest_pending_loan_guard(
                runtime,
                live_party_runtime,
                configuration,
                json.loads((Path(parent) / "CONTEXT.json").read_bytes()),
                observed_bird_refs=bird_return_refs,
            )
        elif pending_loan:
            before, refs = authenticated_preloan_roster(parent, configuration, observed_bird_refs=bird_return_refs)
            from .red_trainer_evolution import level_evolution_edges

            guard = RedPlayerPartyGuard(
                reader,
                before,
                refs,
                level_evolution_edges(backend.c.ROM.read_bytes()),
                runtime.reader,
                effective_loan_refs,
            )
            guard.verify()
        else:
            guard = RedPlayerPartyGuard.from_rom(
                backend.c.ROM.read_bytes(),
                controller,
                loanable_refs=frozenset(configuration.loanable_specimen_refs),
                storage_reader=runtime.reader,
            )
        if training_admission is None and not pending_loan and custody_document is None:
            origin = _retained_battle_level_origin(parent, runtime, configuration, guard)
            if origin is not None:
                guard = replace(guard, retained_story_origin=origin)
        if dict(configuration.assembly_flags)["protect_party_species"]:
            raise ValueError(
                "temporary loans require retained individuals, not fixed species reserves"
            )
        adapter = RetainedPartyGoalStateAdapter(
            **{
                f.name: getattr(runtime.adapter, f.name)
                for f in fields(runtime.adapter)
                if f.name != "party_guard"
            },
            party_guard=guard,
        )
        runtime = replace(
            runtime,
            adapter=adapter,
            evolution_training_faint_recovery=configuration.evolution_recover_wild_faints,
            certified_evolution_helper_xp=(
                training_admission is None
                and scoped_train_composition is None
                and flags["include_rewards"]
            ),
        )
        if venue_policy is not None:
            runtime = replace(runtime, native_evolution_venue_policy=venue_policy)
        # Existing ROM route topology; there is no supplied strategic destination.
        route = replace(
            backend.shared.RedVermilionGroundTransition.from_rom(backend.c.ROM.read_bytes()),
            full_event_offsets=True,
            observe_terrain=True,
            allow_wild_faints=dict(configuration.assembly_flags)["include_rewards"],
            allow_field_faint_dialogue=dict(configuration.assembly_flags)["include_rewards"],
        )
        holder["configured_route"] = route
        runtime = replace(
            runtime,
            evolution_settlement=_optional_loan_settlement(
                guard,
                lambda actions: restore_guarded_party_loan(runtime, actions, route.route_world),
            ),
            resource_wild_faint_recovery=(
                training_admission is None
                and scoped_train_composition is None
                and dict(configuration.assembly_flags)["include_rewards"]
            ),
        )
        if guard.field_carrier is not None and guard.field_carrier.phase == "active":
            guard.verify_authorized_active_roster()
        elif guard.field_carrier is not None:
            # Pending custody owns its named return, irrespective of legacy loan slot.
            guard.verify()
        elif not pending_loan:
            guard.verify_active_roster_restored()
        if controller.save_state_bytes() != state:
            raise ValueError("configured player construction changed native state")
        holder["runtime"] = runtime
        holder["configuration_sha256"] = configuration.sha256
        return runtime

    if "compare_successful_fishing_site_effort" in income_declaration:
        from .red_fishing_survey_history import declared_survey_comparison, previous_successful_survey
        if declared_survey_comparison(income_declaration):
            if any(s is not None for s in (training_admission, scoped_train_composition, production_train_scope)):
                raise ValueError("same-site survey history is outside TRAIN")
            survey = previous_successful_survey(parent, income_declaration, backend.c.ROM.read_bytes())
            if survey is not None:
                from .red_collection_campaign_scope import collection_observation_wiring
                source = dict(source, verified_preceding_fishing_survey=survey,
                              compare_successful_fishing_site_effort=True, fit_allowed=False, copy_back=False,
                              **collection_observation_wiring(income_declaration))
    return payload, factory, menu, holder, dict(source, configuration_sha256=configuration.sha256)


def _retained_battle_level_origin(parent, runtime, configuration, guard):
    """Carry the last proven level origin across contiguous retained combat."""
    from .party import MoveObservation, PartyMemberObservation, PartyObservation, StatusCondition
    from .observation import MapId

    if guard.field_carrier is not None or runtime.reader.read().battle_state != 2:
        return None
    parent = Path(parent).resolve()
    family = parent.parent
    raw = runtime.reader.read()
    if raw.map_id not in {
        MapId.LORELEIS_ROOM, MapId.BRUNOS_ROOM, MapId.AGATHAS_ROOM,
        MapId.LANCES_ROOM, MapId.CHAMPIONS_ROOM,
    }:
        return None
    current = guard.before
    refs = guard.refs
    frame, held = runtime.emulator.frame_count, runtime.emulator.save_state_bytes()
    if not (parent / 'RESULT.json').is_file():
        return None
    expected = sha256(held).hexdigest()
    seen = {parent}
    origin = None
    for _ in range(16):
        result = json.loads((parent / 'RESULT.json').read_bytes())
        handoff = result.get('qualified_native_control_handoff') or {}
        if not (handoff.get('retained_outcome_censor') and handoff.get('censored_story_battle')):
            break
        plan = json.loads((parent / 'PLAN.json').read_bytes())
        context_bytes = (parent / 'CONTEXT.json').read_bytes()
        context = json.loads(context_bytes)
        outcome, = result['episode']['outcomes']
        if (
            not checkpoint_quiescent(result) or result.get('field_ready') is not False
            or result.get('configuration_sha256') != configuration.sha256
            or result['state_sha256'] != expected or context['state_sha256'] != expected
            or sha256((parent / 'terminal.state').read_bytes()).hexdigest() != expected
            or sha256(context_bytes).hexdigest() != result['context_sha256']
            or result['spent'] != context['spent'] or not context['lesson']['in_battle']
            or handoff.get('qualified') is not True
            or handoff.get('binding_ref') != 'pokemon.red:retained-engagement:' + expected
            or handoff.get('state_sha256') != expected
            or handoff.get('source_state_sha256') != plan['source_sha256']
            or outcome.get('selected_kind') != 'recover_control'
            or outcome.get('error_type') != 'RetainedTrainerBattleDecisionBudgetReached'
            or outcome['terminal_state_sha256'] != expected
            or outcome['before_state_sha256'] != plan['source_sha256']
            or any(outcome[edge].get('battle_state') != 2
                   or outcome[edge]['diagnostics']['map_id'] != raw.map_id
                   for edge in ('before', 'after'))
        ):
            raise ValueError('retained battle level origin lacks its exact native censor')
        prior = Path(plan['actual_parent']).resolve()
        if prior.parent != family or prior in seen:
            # A new copy can start at a pinned foreign parent. Its own field
            # observation is safe, with no additional evidence carried here.
            break
        seen.add(prior)
        prior_bytes = (prior / 'CONTEXT.json').read_bytes()
        previous = json.loads(prior_bytes)
        previous_result = json.loads((prior / 'RESULT.json').read_bytes())
        if (
            sha256(prior_bytes).hexdigest() != plan['context_sha256']
            or sha256((prior / 'terminal.state').read_bytes()).hexdigest() != plan['source_sha256']
            or previous['state_sha256'] != plan['source_sha256']
            or previous_result['state_sha256'] != plan['source_sha256']
            or previous_result['context_sha256'] != plan['context_sha256']
            or previous_result['spent'] != plan['inherited_spent'] or previous['spent'] != plan['inherited_spent']
            or previous_result.get('map_id') != raw.map_id
            or not checkpoint_quiescent(previous_result) or not previous['lesson']['in_battle']
            or canonical_sha256(outcome['before']['player_lesson']) != canonical_sha256(previous['lesson'])
        ):
            raise ValueError('retained battle level source is not the bound predecessor')
        rows = {row['specimen_ref']: row for row in previous['lesson']['party']}
        if len(rows) != len(previous['lesson']['party']) or set(rows) != set(refs):
            raise ValueError('retained battle level origin changed roster identity')
        members = []
        for slot, (ref, live) in enumerate(zip(refs, current.members, strict=True), 1):
            row = dict(rows[ref])
            row.pop('specimen_ref')
            row['status'] = StatusCondition(row['status'])
            row['moves'] = tuple(MoveObservation(*pair) for pair in row['moves'])
            old = PartyMemberObservation(slot=slot, **row)
            if (old.species_id != live.species_id or old.level > live.level
                    or old.experience is None or live.experience is None
                    or old.experience > live.experience):
                raise ValueError('retained battle level origin has incoherent progress')
            members.append(old)
        origin = PartyObservation(tuple(members))
        parent, expected = prior, plan['source_sha256']
    else:
        raise ValueError('retained battle level origin exceeded its ancestry bound')
    if runtime.emulator.frame_count != frame or runtime.emulator.save_state_bytes() != held:
        raise ValueError('retained battle level origin changed the native boundary')
    return origin


def _same_guest_pending_loan_guard(runtime, previous_runtime, configuration, context, *, observed_bird_refs=None):
    """Carry authenticated custody across live chunks, never across a state load.

    A new run directory cannot re-anchor a pending loan's history. The existing
    in-memory guard already owns its original observation; retain it only for
    the identical live backend, exact roster and declared loan. Rebind readers,
    without refreshing the original individual XP or relaxing disk ancestry.
    """
    from .executor import shares_live_controller_guest
    from .red_party import PokemonRedPartyReader

    old = getattr(previous_runtime.adapter, "party_guard", None)
    expected = tuple(m["specimen_ref"] for m in context["preparation"]["roster"])
    authorized_refs = frozenset(configuration.loanable_specimen_refs)
    if observed_bird_refs is not None:
        physical = {m["specimen_ref"] for m in context["lesson"]["party"]}
        if (len(observed_bird_refs) != 1 or len(physical) != 6
                or set(expected)-physical != observed_bird_refs
                or context["state_sha256"] != sha256(runtime.emulator.save_state_bytes()).hexdigest()):
            raise ValueError("live bird loan differs from its authenticated native exchange")
        authorized_refs = observed_bird_refs
    if (
        not isinstance(old, RedPlayerPartyGuard)
        or not shares_live_controller_guest(
            runtime.emulator, previous_runtime.emulator, old.reader.memory
        )
        or runtime.emulator.frame_count != previous_runtime.emulator.frame_count
        or runtime.emulator.pressed_buttons
        or len(expected) != len(set(expected))
        or len(expected) != 6
        or set(old.refs) != set(expected)
        or old.loanable_refs != authorized_refs
        or old.field_carrier is not None
    ):
        raise ValueError("live pending loan requires its exact same guest and retained guard")
    before, frames = runtime.emulator.save_state_bytes(), runtime.emulator.frame_count
    guard = replace(
        old, reader=PokemonRedPartyReader(runtime.emulator), storage_reader=runtime.reader
    )
    guard.verify()
    if (
        runtime.emulator.save_state_bytes() != before
        or runtime.emulator.frame_count != frames
        or runtime.emulator.pressed_buttons
    ):
        raise ValueError("live pending loan guard inspection changed native control")
    return guard


MAX_PRELOAN_HISTORY_LINKS = 64


def _retained_campaign_loan_edge(parent, prior, record):
    """Only an intact same-campaign version handoff can extend a loan's ancestry."""
    try:
        return _verified_campaign_loan_edge(parent, prior, record)
    except (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError):
        # Missing or malformed ancestry leaves the existing typed denial in force.
        return False


def _verified_campaign_loan_edge(parent, prior, record):
    """Authenticate an exact rollover between registered versions of the same campaign."""
    here, earlier = parent.parents[1], prior.parents[1]
    if parent.parent.name != "runs" or prior.parent.name != "runs" or here == earlier:
        return False
    if here.name != earlier.name or here.parent.parent != earlier.parent.parent:
        return False
    root = here.parent.parent
    current_path, prior_path = here / "PLAN.json", earlier / "PLAN.json"
    raw = current_path.read_bytes()
    current = json.loads(raw)
    prior_raw = prior_path.read_bytes()
    old = json.loads(prior_raw)
    run_id = f"{root.name}/{here.name}"
    if (current.get("campaign_continuation") is not True or current.get("partition") != "development"
            or old.get("partition") != "development" or current.get("campaign_run_id") != run_id
            or old.get("campaign_run_id") != run_id or current.get("mission") != old.get("mission")
            or current.get("parent") != str(prior) or current.get("configuration_sha256") != record["configuration_sha256"]):
        return False
    ordinal = current.get("source_segment_ordinal")
    if type(ordinal) is not int or prior.name != f"segment-{ordinal:03d}" or parent.name != f"segment-{ordinal+1:03d}":
        return False
    mission_pin = current["mission"]
    mission = root / "MISSION.json"
    mission_raw = mission.read_bytes()
    if (mission_pin != {"path": str(mission), "sha256": sha256(mission_raw).hexdigest()}
            or json.loads(mission_raw).get("session_id") != root.name):
        return False
    roster = json.loads((root / "CAMPAIGN-SET.json").read_bytes())
    if roster.get("mission") != mission_pin:
        return False
    rows = [r for r in roster.get("runs", ()) if r.get("campaign_run_id") == run_id]
    if len(rows) != 1:
        return False
    versions = [r.get("live_plan") for r in (rows[0], *rows[0].get("continuations", ()))]
    earlier_pin = {"path": str(prior_path), "sha256": sha256(prior_raw).hexdigest()}
    here_pin = {"path": str(current_path), "sha256": sha256(raw).hexdigest()}
    if versions.count(here_pin) != 1 or versions.count(earlier_pin) != 1 or versions.index(earlier_pin) >= versions.index(here_pin):
        return False
    protected = current.get("protected", {})
    if (current.get("source_sha256") != record["source_sha256"]
            or current.get("context_sha256") != record["context_sha256"]):
        return False
    for filename, digest in (("terminal.state", record["source_sha256"]), ("CONTEXT.json", record["context_sha256"])):
        origin = prior / filename
        if protected.get(str(origin)) != digest or sha256(origin.read_bytes()).hexdigest() != digest:
            return False
    result = prior / "RESULT.json"
    return protected.get(str(result)) == sha256(result.read_bytes()).hexdigest()


def authenticated_preloan_roster(parent, configuration, *, observed_bird_refs=None):
    """Follow authenticated source links to the original roster of an open loan.

    Recovery may itself end at a checkpoint while the same individual is boxed.
    Its immediate predecessor then also contains a guest, not the guard baseline.
    Follow only the declared same-family ancestry, checking every edge and the
    exact missing individual. Never load an ancestor or scan unrelated history.
    """
    from .party import MoveObservation, PartyMemberObservation, PartyObservation, StatusCondition

    parent = Path(parent).resolve()
    family, visited = parent.parent, {parent}
    current = json.loads((parent / "CONTEXT.json").read_bytes())
    expected_refs = tuple(m["specimen_ref"] for m in current["preparation"]["roster"])
    expected = set(expected_refs)

    def pending_roster(document):
        refs = tuple(m["specimen_ref"] for m in document["lesson"]["party"])
        return (
            len(refs) == len(set(refs)) == 6
            and expected - set(refs) == (observed_bird_refs or set(configuration.loanable_specimen_refs))
            and len(set(refs) - expected) == 1
        )

    if (
        len(expected_refs) != len(expected)
        or len(expected) != 6
        or any(not isinstance(ref, str) or not ref for ref in expected_refs)
        or not pending_roster(current)
    ):
        raise ValueError("pending loan does not match its original six-member roster")
    for _ in range(MAX_PRELOAN_HISTORY_LINKS):
        record = json.loads((parent / "PLAN.json").read_bytes())
        prior = Path(record["actual_parent"]).resolve()
        if prior in visited or (prior.parent != family and not _retained_campaign_loan_edge(parent, prior, record)):
            raise ValueError("pending loan requires its immediate same-family source")
        family = prior.parent
        visited.add(prior)
        encoded = (prior / "CONTEXT.json").read_bytes()
        context = json.loads(encoded)
        result = json.loads((prior / "RESULT.json").read_bytes())
        if (
            sha256(encoded).hexdigest() != record["context_sha256"]
            or sha256((prior / "terminal.state").read_bytes()).hexdigest()
            != record["source_sha256"]
            or context["state_sha256"] != record["source_sha256"]
            or result["state_sha256"] != context["state_sha256"]
            or result["context_sha256"] != record["context_sha256"]
            or result["spent"] != context["spent"]
            or result["configuration_sha256"] != configuration.sha256
            or not checkpoint_quiescent(result)
            or record["configuration_sha256"] != configuration.sha256
        ):
            raise ValueError("pending loan source authentication differs")
        refs = tuple(m["specimen_ref"] for m in context["lesson"]["party"])
        if len(refs) == len(set(refs)) == 6 and set(refs) == expected:
            members = []
            for slot, entry in enumerate(context["lesson"]["party"], 1):
                row = dict(entry)
                row.pop("specimen_ref")
                row["status"] = StatusCondition(row["status"])
                row["moves"] = tuple(MoveObservation(*pair) for pair in row["moves"])
                members.append(PartyMemberObservation(slot=slot, **row))
            return PartyObservation(tuple(members)), refs
        retained = tuple(
            m["specimen_ref"] for m in context.get("preparation", {}).get("roster", ())
        )
        if not pending_roster(context) or len(retained) != 6 or set(retained) != expected:
            raise ValueError("pending loan does not match its original six-member roster")
        parent = prior
    raise ValueError("pending loan ancestry budget exhausted")


def _optional_loan_settlement(guard, callback):
    """A no-loan retained roster has no borrowed individual to settle.

    Existing named loans and field-carrier custody keep their exact callback.
    This changes no deposit permission, guard baseline or native roster check.
    """
    from .red_player_party_guard import RedPlayerPartyGuard

    if not isinstance(guard, RedPlayerPartyGuard) or not callable(callback):
        raise TypeError("evolution settlement requires its retained guard and callback")
    if not guard.loanable_refs and guard.field_carrier is None:
        return None
    return callback



def _interrupted_bird_loan_refs(parent, configuration, *, failed_result=None):
    """Restore only the named loan made by the preceding failed, model-selected bird attempt."""
    from .red_player_party_guard import BIRD_CAPTURE_LOAN_POLICY
    parent = Path(parent)
    if not (parent/'PLAN.json').is_file():
        return None
    plan = json.loads((parent/'PLAN.json').read_bytes())
    if plan.get('bird_capture_loan') != BIRD_CAPTURE_LOAN_POLICY:
        return None
    if not (parent/'CONTEXT.json').is_file() or (failed_result is None and not (parent/'RESULT.json').is_file()):
        return None
    encoded=(parent/'CONTEXT.json').read_bytes()
    ctx=json.loads(encoded)
    expected={m['specimen_ref'] for m in ctx['preparation']['roster']}
    physical={m['specimen_ref'] for m in ctx['lesson']['party']}
    if expected==physical or ctx.get('field_carrier') is not None:
        return None
    result=json.loads((parent/'RESULT.json').read_bytes()) if failed_result is None else failed_result
    outcomes=result.get('episode',{}).get('outcomes') or ()
    if not outcomes:
        return None
    outcome=outcomes[-1]
    if outcome.get('selected_kind')!='acquire_species' or outcome.get('failure_phase')!='execution':
        return None
    origin=outcome['before_state_sha256']
    started=parent/'native'/'episode'/f"step-{outcome['ordinal']:03d}"/'execution-started.json'
    if not started.is_file():
        return None
    selection=json.loads(started.read_bytes())
    if not str(selection.get('selected_binding_ref','')).startswith('red-prepared-static:'+origin+':'):
        return None
    if (not result['released'] or not result['paired_context_authenticated']
            or result['configuration_sha256']!=plan['configuration_sha256'] or plan['configuration_sha256']!=configuration.sha256
            or result['context_sha256']!=sha256(encoded).hexdigest()
            or result['state_sha256']!=ctx['state_sha256'] or result['state_sha256']!=outcome['terminal_state_sha256']
            or result['state_sha256']!=sha256((parent/'terminal.state').read_bytes()).hexdigest()
            or result['spent']!=ctx['spent'] or selection.get('state_sha256')!=origin
            or len(expected)!=6 or len(physical)!=6 or len(expected-physical)!=1 or len(physical-expected)!=1):
        raise ValueError('interrupted bird loan has inconsistent state or custody')
    before={m['specimen_ref']:m for m in outcome['before']['player_lesson']['party']}
    after={m['specimen_ref']:m for m in ctx['lesson']['party']}
    if set(before)!=expected or outcome['after']['player_lesson']['party']!=ctx['lesson']['party']:
        raise ValueError('interrupted bird loan has inconsistent party observations')
    backup,=expected-physical
    helper,=physical-expected
    receipts=[]
    for path in parent.glob('HELPER-LOAN-*.json'):
        proof=json.loads(path.read_bytes())
        if (proof.get('native_pc_exchange') is True and proof.get('reserved_original_return_slot') is True
                and proof.get('original_backup_ref')==backup and proof.get('helper_ref')==helper
                and proof.get('original_backup_species')==before[backup]['species_id']
                and proof.get('helper_species')==after[helper]['species_id']):
            receipts.append(proof)
    if len(receipts)!=1:
        raise ValueError('interrupted bird loan lacks its unique PC exchange receipt')
    return frozenset({backup})
