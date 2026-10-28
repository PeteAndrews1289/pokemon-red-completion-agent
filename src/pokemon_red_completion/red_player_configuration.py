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
    if (type(scope) is not str or scope not in scopes or type(released) is not bool
        or guest_backend_closed is not None and type(guest_backend_closed) is not bool):
        raise ValueError("invalid measured player lifecycle boundary")
    return dict(
        worker_stopped=guest_backend_closed is True,
        live_driver_running=scope in {"live_chunk", "diagnostic_chunk"},
        checkpoint_lifecycle=dict(
            schema="pokemon.red.checkpoint-quiescence.v1", scope=scope,
            chunk_complete=True, inputs_released=released,
            guest_backend_closed=guest_backend_closed, host_process_exit_confirmed=False,
            unexpected_guest_closure=(scope in {"live_chunk", "diagnostic_chunk"}
                and guest_backend_closed is True),
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
    if (type(life) is not dict or set(life) != {
        "schema", "scope", "chunk_complete", "inputs_released",
        "guest_backend_closed", "host_process_exit_confirmed", "unexpected_guest_closure"}
        or life.get("schema") != "pokemon.red.checkpoint-quiescence.v1"
        or life.get("chunk_complete") is not True or life.get("inputs_released") is not True
        or life.get("host_process_exit_confirmed") is not False):
        return False
    try:
        expected = player_lifecycle_fields(scope=life.get("scope"), released=True,
            guest_backend_closed=life.get("guest_backend_closed"))
    except (ValueError, TypeError):
        return False
    return (life == expected["checkpoint_lifecycle"]
        and result.get("worker_stopped") is expected["worker_stopped"]
        and result.get("live_driver_running") is expected["live_driver_running"])


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

    def __post_init__(self):
        from .red_player_preparation_binding import preparation_encounter_limits

        preparation_encounter_limits(self.preparation_encounter_quantum)
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
            or len(self.loanable_specimen_refs) != 1
            or any(not isinstance(ref, str) or not ref for ref in self.loanable_specimen_refs)
        ):
            raise ValueError("configured player needs one declared temporary reserve loan")

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
        schema = (PREPARATION_QUANTUM_SCHEMA if self.preparation_encounter_quantum is not None else
                  HELPER_VENUE_SCHEMA if not self.evolution_allow_direct_fights else
                  VENUE_SCHEMA if self.evolution_venue_model_sha256 is not None else
                  ROUTE_WORK_SCHEMA if self.quote_capture_route_work else SCHEMA)
        return dict(schema=schema, **values)

    @classmethod
    def from_dict(cls, document):
        optional = {"quote_capture_route_work", "evolution_venue_model_sha256", "evolution_venue_scope",
                    "evolution_allow_direct_fights", "preparation_encounter_quantum"}
        names = {entry.name for entry in fields(cls)} - optional
        if not isinstance(document, dict):
            raise ValueError("configured player document schema differs")
        schema = document.get("schema")
        quantum = schema == PREPARATION_QUANTUM_SCHEMA
        helper_only = schema == HELPER_VENUE_SCHEMA or (
            quantum and "evolution_allow_direct_fights" in document)
        venue = schema in {VENUE_SCHEMA, HELPER_VENUE_SCHEMA} or (
            quantum and bool({"evolution_venue_model_sha256", "evolution_venue_scope"} & set(document)))
        route = schema == ROUTE_WORK_SCHEMA or (venue or quantum) and "quote_capture_route_work" in document
        expected = {"schema", *names}
        if quantum:
            expected.add("preparation_encounter_quantum")
        if route:
            expected.add("quote_capture_route_work")
        if venue:
            expected.update(("evolution_venue_model_sha256", "evolution_venue_scope"))
        if helper_only:
            expected.add("evolution_allow_direct_fights")
        if (schema not in {SCHEMA, ROUTE_WORK_SCHEMA, VENUE_SCHEMA, HELPER_VENUE_SCHEMA, PREPARATION_QUANTUM_SCHEMA}
            or quantum and document.get("preparation_encounter_quantum") is None
            or helper_only and document.get("evolution_allow_direct_fights") is not False
            or set(document) != expected
            or route and document["quote_capture_route_work"] is not True
            or venue and (not _sha(document["evolution_venue_model_sha256"])
                          or type(document["evolution_venue_scope"]) not in (list, tuple))):
            raise ValueError("configured player document schema differs")
        return cls(
            origin_sha256=document["origin_sha256"], origin_id=document["origin_id"],
            goal_model_sha256=document["goal_model_sha256"],
            assembly_flags=tuple(tuple(pair) for pair in document["assembly_flags"]),
            excluded_profiles=tuple(tuple(pair) for pair in document["excluded_profiles"]),
            loanable_specimen_refs=tuple(document["loanable_specimen_refs"]),
            quote_capture_route_work=route,
            evolution_venue_model_sha256=document["evolution_venue_model_sha256"] if venue else None,
            evolution_venue_scope=tuple(document["evolution_venue_scope"]) if venue else (),
            evolution_allow_direct_fights=not helper_only,
            preparation_encounter_quantum=document["preparation_encounter_quantum"] if quantum else None,
        )

    @property
    def sha256(self):
        return canonical_sha256(self.to_dict())

    def admits(self, binding):
        return not any(
            binding.kind.value == kind and (
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
                    runtime, actions, rom=rom, battler=battler, objective_id="rescue_fuji",
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


def declared_native_evolution_venue_model(plan, configuration=None):
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
    if (plan.get("partition") != "development" or not isinstance(spec, dict)
        or set(spec) != {"path", "content_sha256", "reason"}
        or not isinstance(spec["path"], str) or not Path(spec["path"]).is_absolute()
        or not _sha(spec["content_sha256"])
        or not isinstance(spec["reason"], str) or not spec["reason"].strip()):
        raise ValueError("native venue model requires a pinned DEVELOPMENT declaration")
    from .party_development_outcome_learning import load_party_development_outcome_model
    from .red_native_boxed_evolution import validate_native_evolution_venue_model
    model = load_party_development_outcome_model(spec["path"], expected_sha256=spec["content_sha256"])
    validate_native_evolution_venue_model(model, expected)
    return model


def _validate_venue_configuration(model_sha256, scope):
    if model_sha256 is None and scope == ():
        return
    if (not _sha(model_sha256) or type(scope) is not tuple or len(scope) < 2
        or any(type(name) is not str or name not in VENUE_SCOPE_NAMES for name in scope)
        or len(set(scope)) != len(scope)):
        raise ValueError("native venue configuration requires its model identity and distinct scope")


def _configured_native_venue_policy(configuration, model):
    if configuration.evolution_venue_model_sha256 is None:
        if model is not None:
            raise ValueError("native venue model lacks an explicit configured identity")
        return None
    from .red_native_boxed_evolution import NativeEvolutionVenuePolicy
    from . import red_goal_context as context
    venues = dict(route11=context.ROUTE_11_TRAINING_VENUE,
                  digletts_cave=context.DIGLETTS_CAVE_TRAINING_VENUE,
                  mansion=context.MANSION_TRAINING_VENUE)
    return NativeEvolutionVenuePolicy(model, configuration.evolution_venue_model_sha256,
        tuple(venues[name] for name in configuration.evolution_venue_scope),
        allow_direct_evolution=configuration.evolution_allow_direct_fights)


def _retained_capture_inventory(runtime, actions, *, parent, output):
    """Reconnect an exact paused allocation before any ordinary wild exit.

    This is the existing one-off executor and journal verifier. A journal from
    another state cannot authorize a new encounter or reset its throw budget.
    """
    read = getattr(getattr(runtime, "reader", None), "read", None)
    if not callable(read) or read().battle_state != 1:
        return None
    parent = Path(parent)
    receipts = tuple(parent.glob("snorlax-*/*-paused/receipt.json")) + tuple(
        parent.glob("static-*/*-paused/receipt.json"))
    if not receipts:
        return None
    state = runtime.emulator.save_state_bytes()
    if state != (parent / "terminal.state").read_bytes():
        return None
    from hashlib import sha256
    from red_earned_run_completion_20261005 import retained_capture_binding

    binding = retained_capture_binding(runtime, actions, parent=parent, output=output)
    if (binding is None or binding.kind is not GoalKind.RECOVER_CONTROL
            or binding.binding_ref != "pokemon.red:retained-capture:" + sha256(state).hexdigest()):
        raise ValueError("retained capture inventory lacks its exact verified binding")
    blocked = GoalOpportunity(
        binding.binding_ref + ":settlement-only", GoalKind.ADVANCE_STORY,
        GoalAvailability.UNAVAILABLE,
        unavailable_reason=GoalUnavailableReason.TEMPORARILY_BLOCKED,
    )
    return GoalBindingSet((binding.opportunity, blocked), (binding,))



def _retained_field_faint_inventory(runtime, actions, *, parent):
    """Read the exact failed native parent before offering compulsory settlement."""
    read = getattr(getattr(runtime, "reader", None), "read", None)
    if not callable(read) or read().battle_state != 0:
        return None
    parent = Path(parent)
    if not (parent / "RESULT.json").is_file() or not (parent / "terminal.state").is_file():
        return None
    state = runtime.emulator.save_state_bytes()
    if state != (parent / "terminal.state").read_bytes():
        return None
    result = json.loads((parent / "RESULT.json").read_bytes())
    if (not checkpoint_quiescent(result)
        or result.get("state_sha256") != sha256(state).hexdigest()
        or result.get("continuation_reason") != "native_execution_error"):
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
        if (prior_native.get("retained_tail_sha256") != sha256(state).hexdigest()
                or prior_native.get("source_chunk_state_sha256") != outcomes[0].get("before_state_sha256")
                or not boundary_state.is_file()
                or sha256(boundary_state.read_bytes()).hexdigest() != prior_native.get("native_final_state_sha256")):
            return None
    binding = retained_field_faint_binding(runtime, actions, outcome=outcomes[-1], prior_native_boundary=prior_native)
    if binding is None:
        return None
    blocked = GoalOpportunity(binding.binding_ref + ":settlement-only",
        GoalKind.ADVANCE_STORY, GoalAvailability.UNAVAILABLE,
        unavailable_reason=GoalUnavailableReason.TEMPORARILY_BLOCKED)
    return GoalBindingSet((binding.opportunity, blocked), (binding,))



def local_ordinary_ball_supply_profile(profile, mart_map_id):
    """Reuse the verified local clerk and the existing affordable five-ball order."""
    from .observation import ItemId, MapId
    from .red_goal_context_profile import (
        RedGoalMechanic, _thaw, build_red_goal_context_profile_payload,
        parse_red_goal_context_profile,
    )

    if type(mart_map_id) is not int or mart_map_id not in {
            int(MapId.CERULEAN_MART), int(MapId.VERMILION_MART)}:
        raise ValueError('ordinary ball supplier needs a verified clerk catalog entry')
    providers = [(spec.kind, spec.mechanic, _thaw(spec.parameters))
                 for spec in profile.providers if spec.kind is not GoalKind.RESUPPLY]
    providers.append((GoalKind.RESUPPLY, RedGoalMechanic.MART_RESUPPLY, dict(
        map_id=mart_map_id, player_x=2, player_y=5,
        interaction_direction='left',
        purchases=[dict(absolute_index=0, item_id=int(ItemId.POKE_BALL),
                        quantity=5, unit_price=200)],
        affordable_ball_purchase=True, resource_choice_variants=True,
    )))
    providers.sort(key=lambda row: tuple(GoalKind).index(row[0]))
    return parse_red_goal_context_profile(build_red_goal_context_profile_payload(
        profile_id=('whole-player-local-vermilion-ordinary-balls-v1' if mart_map_id == int(MapId.VERMILION_MART)
                    else 'whole-player-local-cerulean-ordinary-balls-v1'), providers=tuple(providers)))


def local_ordinary_ball_supply_peers(runtime, actions, observation, *, world, _town=None):
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
    # Capability data, not a supplied strategic ordering: both clerks have
    # native-verified stance (2,5), LEFT, ordinary ball stock index zero at 200.
    # The current route quote decides reachability for every verified clerk;
    # no current-town filter hides a legitimate nearby supplier from the model.
    catalog = ((int(MapId.CERULEAN_CITY), int(MapId.CERULEAN_MART)),
               (int(MapId.VERMILION_CITY), int(MapId.VERMILION_MART)))
    outside = runtime.reader.read_retained_outside_map()
    matches = [mart for town, mart in catalog if _town is None or (town == _town
               and (raw.map_id == town or raw.map_id == mart
                    or type(raw.map_id) is int and raw.map_id >= 0x25 and outside == town))]
    if not matches:
        return ()
    if not ordinary_ball_resupply_peer_needed(raw, hall_of_fame='enter_hall_of_fame' in set(
            runtime.adapter.graph.completed_ids(observation.game_state))):
        return ()
    world = world.with_current_observation(runtime.reader)
    bindings = []
    for mart_map_id in matches:
        configured = replace(runtime, profile=local_ordinary_ball_supply_profile(runtime.profile, mart_map_id))
        inventory = RedResourceGoalRouter(
            configured, actions, world, quote_resource_costs=True,
            prepare_capture_party=False, prepare_capture_escort=False,
            include_recovery_offers=False,
        ).enumerate_routed_kinds(observation, frozenset({GoalKind.RESUPPLY}))
        bindings.extend(binding for binding in inventory.bindings if binding.kind is GoalKind.RESUPPLY)
    return tuple(bindings)


def local_vermilion_ball_supply_profile(profile):
    """Compatibility view of the existing verified Vermilion capability."""
    from .observation import MapId

    return local_ordinary_ball_supply_profile(profile, int(MapId.VERMILION_MART))


def local_vermilion_ball_supply_peers(runtime, actions, observation, *, world):
    """Preserve the original Vermilion-only helper contract."""
    from .observation import MapId

    return local_ordinary_ball_supply_peers(runtime, actions, observation,
                                          world=world, _town=int(MapId.VERMILION_CITY))


def assemble_configured_player(
    backend, configuration, parent, output, *, plan_path, model_feature_version=7,
    evolution_venue_model=None, training_admission=None, include_preparation_party_context=False,
):
    """Reuse the existing composition with persistent admission and loan wiring."""
    if not isinstance(configuration, RedPlayerConfiguration):
        raise TypeError("typed player configuration required")
    if type(model_feature_version) is not int or model_feature_version not in (5, 6, 7, 8, 9, 10, 11, 13, 14, 15):
        raise ValueError("configured player requires a supported model feature version")
    if type(include_preparation_party_context) is not bool or (include_preparation_party_context and model_feature_version!=15):
        raise ValueError("preparation party context requires explicit V15 observation opt-in")
    if configuration.evolution_venue_model_sha256 is not None and evolution_venue_model is None:
        evolution_venue_model = declared_native_evolution_venue_model(
            json.loads(Path(plan_path).read_bytes()), configuration)
    venue_policy = _configured_native_venue_policy(configuration, evolution_venue_model)
    if training_admission is not None:
        from .red_production_train_admission import ProductionTrainAdmission
        if type(training_admission) is not ProductionTrainAdmission:
            raise TypeError("typed production TRAIN admission required")
        training_admission.require_work_order(Path(plan_path).read_bytes())
        if (configuration.origin_sha256 != training_admission.source_origin_sha256
            or configuration.origin_id != training_admission.root_lineage_id):
            raise ValueError("configured TRAIN origin differs from admitted source")
    payload, factory0, menu, holder, source = backend.assembly(
        parent,
        output,
        plan_path=plan_path,
        **({"training_admission": training_admission} if training_admission is not None else {}),
        origin_sha=configuration.origin_sha256,
        origin_id=configuration.origin_id,
        continuation_loan_refs=frozenset(configuration.loanable_specimen_refs),
        **({"quote_capture_route_work": True} if configuration.quote_capture_route_work else {}),
        **({"preparation_encounter_quantum": configuration.preparation_encounter_quantum}
           if configuration.preparation_encounter_quantum is not None else {}),
        **({"include_level_workload": True} if model_feature_version >= 9 else {}),
        **({"include_capture_invocation": True} if model_feature_version >= 13 else {}),
        **({"include_matchup_observation": True} if model_feature_version >= 15 else {}),
        **({"include_preparation_party_context": True} if include_preparation_party_context else {}),
        **dict(configuration.assembly_flags),
    )
    if model_feature_version >= 10:
        from .red_player_owned_machines import connect_move_change_inventory

        connect_move_change_inventory(menu, rom=backend.c.ROM.read_bytes())
    connect_retained_route22_recovery(backend, holder)
    if (training_admission is None and menu.enumerate_resources is not None
            and dict(configuration.assembly_flags)['include_supply']
            and dict(configuration.assembly_flags)['include_rewards']):
        regional_resources = menu.enumerate_resources

        def resources_with_local_mart(runtime, actions, observation):
            from .red_player_story_menu import merge_resource_observer_bindings

            rows = regional_resources(runtime, actions, observation)
            route = holder.get('configured_route')
            local = (() if route is None else local_ordinary_ball_supply_peers(
                runtime, actions, observation, world=route.route_world))
            return merge_resource_observer_bindings(rows + local)

        menu.enumerate_resources = resources_with_local_mart
    if training_admission is None:
        from .red_indoor_departure_plan import indoor_departure_binding

        def empty_indoor_recovery(runtime, actions, observation):
            route = holder.get("configured_route")
            return None if route is None else indoor_departure_binding(runtime, actions, route=route)

        menu.enumerate_empty_recovery = empty_indoor_recovery
    ordinary, supplements = menu.enumerate_base, menu.supplements

    def enumerate_allowed(*args):
        retained = _retained_field_faint_inventory(args[0], args[1], parent=parent)
        if retained is not None:
            return retained
        retained = _retained_capture_inventory(args[0], args[1], parent=parent, output=output)
        if retained is not None:
            return retained
        if training_admission is None:
            from .red_indoor_departure_plan import native_ship_departure_binding

            departure = native_ship_departure_binding(args[0], args[1])
            if departure is not None:
                blocked = GoalOpportunity(
                    departure.binding_ref + ":settlement-only", GoalKind.ADVANCE_STORY,
                    GoalAvailability.UNAVAILABLE,
                    unavailable_reason=GoalUnavailableReason.TEMPORARILY_BLOCKED,
                )
                return GoalBindingSet((departure.opportunity, blocked), (departure,))
        if "configured_route" in holder:
            runtime, actions, _ = args
            loan = party_loan_return_binding(
                runtime, actions, holder["configured_route"].route_world
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
        flags = dict(configuration.assembly_flags)
        if flags["include_rewards"] and flags["include_supply"]:
            runtime = connect_retained_ordinary_funding(runtime, holder.get("actor"))
        state = controller.save_state_bytes()
        from .red_party import PokemonRedPartyReader

        reader = PokemonRedPartyReader(controller)
        pending_loan = not set(configuration.loanable_specimen_refs) <= set(
            reader.preparation_specimen_refs()
        )
        if pending_loan:
            before, refs = authenticated_preloan_roster(parent, configuration)
            from .red_trainer_evolution import level_evolution_edges

            guard = RedPlayerPartyGuard(
                reader,
                before,
                refs,
                level_evolution_edges(backend.c.ROM.read_bytes()),
                runtime.reader,
                frozenset(configuration.loanable_specimen_refs),
            )
            guard.verify()
        else:
            guard = RedPlayerPartyGuard.from_rom(
                backend.c.ROM.read_bytes(),
                controller,
                loanable_refs=frozenset(configuration.loanable_specimen_refs),
                storage_reader=runtime.reader,
            )
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
        runtime = replace(runtime, adapter=adapter)
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
            evolution_settlement=lambda actions: restore_guarded_party_loan(
                runtime, actions, route.route_world
            ),
        )
        if not pending_loan:
            guard.verify_active_roster_restored()
        if controller.save_state_bytes() != state:
            raise ValueError("configured player construction changed native state")
        holder["runtime"] = runtime
        holder["configuration_sha256"] = configuration.sha256
        return runtime

    return payload, factory, menu, holder, dict(source, configuration_sha256=configuration.sha256)


MAX_PRELOAN_HISTORY_LINKS = 64


def authenticated_preloan_roster(parent, configuration):
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
            and expected - set(refs) == set(configuration.loanable_specimen_refs)
            and len(set(refs) - expected) == 1
        )

    if (
        len(expected_refs) != len(expected) or len(expected) != 6
        or any(not isinstance(ref, str) or not ref for ref in expected_refs)
        or not pending_roster(current)
    ):
        raise ValueError("pending loan does not match its original six-member roster")
    for _ in range(MAX_PRELOAN_HISTORY_LINKS):
        record = json.loads((parent / "PLAN.json").read_bytes())
        prior = Path(record["actual_parent"]).resolve()
        if prior.parent != family or prior in visited:
            raise ValueError("pending loan requires its immediate same-family source")
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
