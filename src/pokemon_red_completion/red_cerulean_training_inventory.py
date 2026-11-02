"""Closed opt-in TRAIN menu assembled from existing native capabilities.

Story attacks and preparation use the declared pool. Travel retains disclosed
wild-flee support, so this does NOT certify whole-player battle-loss coverage.
Capture, evolution and ordinary funding are outside this narrow experiment;
reject a broader runtime instead of silently dropping its alternatives.
"""

from dataclasses import replace

from .observation import MapId
from .party_preparation import PreparationPurpose
from .red_goal_context import RedGoalContextRuntime
from .red_goal_context_profile import RedGoalMechanic
from .red_party_preparation import observe_preparation_members
from .red_player_cerulean_branches import cerulean_story_options
from .red_player_field_goals import enumerate_routed_player_goals
from .red_player_story_menu import NativeStoryBranchInventory
from .red_resource_goal_router import RedResourceGoalRouter
from .red_scoped_training_battlers import ScopedTrainingBattlers

_MECHANICS = frozenset({
    RedGoalMechanic.CENTER_RESTORE, RedGoalMechanic.MART_RESUPPLY,
    RedGoalMechanic.CONTROL_RECOVERY,
})
_FORBIDDEN_CALLBACKS = (
    "boxed_level_evolution_executor", "party_level_evolution_executor",
    "boxed_level_evolution_readiness", "evolution_stop_requested",
    "boxed_item_evolution_executor", "boxed_item_evolution_readiness",
    "trainer_battle_runner", "league_battle_controller", "league_story_battle_controller",
    "trainer_funding_event_sink", "trainer_story_world",
    "trainer_battle_model_sha256", "trainer_battle_qualification_sha256",
)
_FORBIDDEN_FLAGS = (
    "boxed_level_evolution_cross_box", "boxed_item_evolution_cross_box",
    "remaining_acquisition_demand", "trainer_funding_ledges",
    "trainer_funding_indoor_departure", "safari_indoor_departure", "safari_departure_surf",
    "safari_complete_paid_session", "scripted_gifts", "npc_trades", "moving_npc_trades",
    "npc_trade_dependencies", "trainer_funding_roster_preparation",
)


class CeruleanTrainingInventory:
    """Trusted native adapters, not a sandbox for arbitrary Python callbacks.

Construct before input with an explicit limited profile. All three native-player
callbacks belong to the same cached inventory. Bindings recheck the runtime and
pool again before execution, not only while building a menu.
"""

    def __init__(self, runtime, *, pool, route, plan, corridor, record, hideout_timing,
                 maximum_battles=8):
        if type(runtime) is not RedGoalContextRuntime or type(pool) is not ScopedTrainingBattlers:
            raise TypeError("training inventory needs the concrete runtime and declared pool")
        if type(maximum_battles) is not int or not 1 <= maximum_battles <= 8:
            raise ValueError("training inventory battle dose must be1..8")
        if not callable(record):
            raise TypeError("training inventory requires a retained preparation recorder")
        self.runtime, self.pool, self.route, self.plan = runtime, pool, route, plan
        self.corridor, self.record, self.hideout_timing = corridor, record, hideout_timing
        self.maximum_battles = maximum_battles
        self._runtime_refs = tuple(id(getattr(runtime, name)) for name in (
            "emulator", "reader", "observer", "adapter", "profile", "registration_policy",
        ))
        self._scope_sha256 = pool.declaration_sha256
        self._check(runtime)
        self._menu = NativeStoryBranchInventory(self._base, self._branches)

    def _check(self, runtime):
        if runtime is not self.runtime or self._runtime_refs != tuple(
            id(getattr(runtime, name)) for name in (
                "emulator", "reader", "observer", "adapter", "profile", "registration_policy",
            )
        ):
            raise ValueError("training inventory runtime identity changed")
        if (runtime.registration_policy is None
            or {s.mechanic for s in runtime.profile.providers} != _MECHANICS
            or any(getattr(runtime, name) is not None for name in _FORBIDDEN_CALLBACKS)
            or any(getattr(runtime, name) is not False for name in _FORBIDDEN_FLAGS)
            or runtime.level_evolution_acquisition_edges
            or any(s.parameters.get(key, False) for s in runtime.profile.providers for key in (
                "composable_trainer_funding", "funding_sale", "fly_transport",
                "indoor_fly_departure", "indoor_funding_departure", "mart_funding_departure",
                "funding_fly_transport",
            ))):
            raise ValueError("training inventory has an undeclared capability or combat callback")
        if (self.pool.declaration_sha256 != self._scope_sha256
            or self.pool.wild.session is not runtime.emulator):
            raise ValueError("training inventory actor bypasses its declared guarded runtime")

    def _guard(self, binding):
        def execute():
            self._check(self.runtime)
            return binding.execute()

        def verify(report):
            self._check(self.runtime)
            return binding.verify(report)

        return replace(binding, execute=execute, verify=verify)

    def _current_route(self, runtime):
        return replace(self.route, route_world=self.route.route_world.with_current_observation(
            runtime.reader,
        ))

    def _base(self, runtime, actions, observation):
        self._check(runtime)
        route = self._current_route(runtime)

        def resources(rt, port, observed):
            return RedResourceGoalRouter(
                rt, port, route.route_world, quote_resource_costs=True,
                prepare_capture_party=False, prepare_capture_escort=False,
                include_recovery_offers=False, trainer_funding=False,
            ).enumerate(observed)

        result = enumerate_routed_player_goals(
            runtime, actions, observation, home_map=int(MapId.CERULEAN_POKECENTER),
            route=route, enumerate_base=resources, preparation=dict(
                battler=self.pool.wild, plan=self.plan, corridor=self.corridor,
                record=self.record, hideout_timing=self.hideout_timing,
                maximum_battles=self.maximum_battles,
            ),
        )
        return replace(result, bindings=tuple(self._guard(b) for b in result.bindings))

    def _branches(self, runtime, actions, observation):
        self._check(runtime)
        levels = tuple(m.observation.level for m in observe_preparation_members(
            runtime.emulator, self.plan,
        ) if m.purpose is PreparationPurpose.COMBAT)
        options = cerulean_story_options(
            runtime, actions, route=self._current_route(runtime), battler=self.pool,
            combat_levels=levels,
        )
        return tuple((self._guard(o.binding), o.challenge) for o in options)

    def enumerate(self, runtime, actions, observation):
        self._check(runtime)
        return self._menu.enumerate(runtime, actions, observation)

    def supplements(self, runtime, actions, observation, bindings):
        self._check(runtime)
        return self._menu.supplements(runtime, actions, observation, bindings)

    def challenges(self, runtime, bindings, supplements, boundary):
        self._check(runtime)
        return self._menu.challenges(runtime, bindings, supplements, boundary)
