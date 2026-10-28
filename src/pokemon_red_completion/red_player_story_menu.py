"""Expose several executable story branches without choosing their order.

One ordinary representative satisfies the existing goal-kind inventory; the
others use the mixed-menu seam. This split is bookkeeping, not a preference.
The mixed menu orders all rows neutrally and the model owns selection.
"""

from collections.abc import Mapping
from contextlib import nullcontext
from dataclasses import replace

from .goal_manager import GoalAvailability, GoalKind, GoalOpportunity, GoalUnavailableReason
from .goal_manager_runtime import ExecutableGoalBinding, GoalBindingSet
from .living_dex_goal_policy import project_living_dex_goal_candidate
from .player_option_challenge import OptionChallenge
from .player_option_preparation import OptionPreparation
from .red_live_option_menu import RedLiveSupplementalOption, supplemental_live_option
from .route_plan import frozen_local_route_inventory


def registered_story_branches(runtime, actions, *, observers):
    """Observe every legal configured native capability, without phase ordering.

    Each observer returns one existing (binding, challenge) pair or None. Missing
    capabilities stay absent; no teacher registry, first-available dispatch or
    fixed destination is substituted. Objective refs are private executor guards,
    not policy features. NativeStoryBranchInventory supplies the mixed menu.
    """
    if not isinstance(observers, Mapping) or any(
        not isinstance(key, str) or not key or not callable(value)
        for key, value in observers.items()
    ):
        raise TypeError("story registry requires objective-keyed native observers")
    for objective in observers:
        runtime.adapter.graph.objective(objective)
    state = runtime.emulator.save_state_bytes()
    frame = runtime.emulator.frame_count
    buttons = runtime.emulator.pressed_buttons
    observation = runtime.adapter.observe()
    legal = {o.id for o in runtime.adapter.graph.available_objectives(observation.game_state)}
    rows = []
    for objective in sorted(legal & observers.keys()):
        row = observers[objective](runtime, actions, observation)
        if (runtime.emulator.save_state_bytes() != state
                or runtime.emulator.frame_count != frame
                or runtime.emulator.pressed_buttons != buttons):
            raise ValueError("story registry observer changed native state")
        if row is None:
            continue
        if (not isinstance(row, tuple) or len(row) != 2
                or not isinstance(row[0], ExecutableGoalBinding)
                or row[0].kind is not GoalKind.ADVANCE_STORY
                or row[0].story_objective_ref != objective
                or not isinstance(row[1], OptionChallenge)):
            raise ValueError("story registry requires its own typed native branch")
        rows.append(row)
    if len({b.binding_ref for b, _ in rows}) != len(rows):
        raise ValueError("story registry repeats a native executor")
    if (runtime.emulator.save_state_bytes() != state
            or runtime.emulator.frame_count != frame
            or runtime.emulator.pressed_buttons != buttons):
        raise ValueError("story registry observer changed native state")
    return tuple(rows)


class NativeStoryBranchInventory:
    """Keep the native player's callbacks on one freshly observed menu.

    The base supplies preparation/recovery/resources; the branch observer supplies
    (executor, semantic challenge) pairs. Optional preparation supplies distinct
    member executors. Default enumeration has no strategic priority or game input.
    An explicit medicine-reserve callback is the user-approved temporary support
    rule: it emits one quoted purchase without querying or crediting the model.
    Its explicit pre-entry healing companion uses only the native free nurse.
    A subsequent boundary must enumerate again before using its peers.
    """

    def __init__(self, enumerate_base, enumerate_branches, *, enumerate_preparation=None,
                 enumerate_resources=None, enumerate_medicine_reserve=None,
                 enumerate_collection=None, reuse_local_route_queries=False,
                 enumerate_league_healing=None, enumerate_league_capacity=None,
                 enumerate_owned_machines=None, observe_matchups=None, observe_preparation_party=None,
                  enumerate_empty_recovery=None):
        if not callable(enumerate_base) or not callable(enumerate_branches):
            raise TypeError("native branch inventory needs callable observers")
        self.enumerate_base = enumerate_base
        self.enumerate_branches = enumerate_branches
        if enumerate_preparation is not None and not callable(enumerate_preparation):
            raise TypeError("preparation inventory observer must be callable")
        self.enumerate_preparation = enumerate_preparation
        if enumerate_resources is not None and not callable(enumerate_resources):
            raise TypeError("resource inventory observer must be callable")
        self.enumerate_resources = enumerate_resources
        if enumerate_medicine_reserve is not None and not callable(enumerate_medicine_reserve):
            raise TypeError("medicine reserve must be an explicit support observer")
        self.enumerate_medicine_reserve = enumerate_medicine_reserve
        if enumerate_league_healing is not None and not callable(enumerate_league_healing):
            raise TypeError("League healing must be an explicit support observer")
        self.enumerate_league_healing = enumerate_league_healing
        if enumerate_league_capacity is not None and not callable(enumerate_league_capacity):
            raise TypeError("League medicine capacity must be an explicit support observer")
        self.enumerate_league_capacity = enumerate_league_capacity
        if enumerate_collection is not None and not callable(enumerate_collection):
            raise TypeError("collection inventory observer must be callable")
        self.enumerate_collection = enumerate_collection
        if enumerate_owned_machines is not None and not callable(enumerate_owned_machines):
            raise TypeError("owned-machine observer must be callable")
        self.enumerate_owned_machines = enumerate_owned_machines
        if enumerate_empty_recovery is not None and not callable(enumerate_empty_recovery):
            raise TypeError("empty-menu recovery must be a callable observer")
        self.enumerate_empty_recovery = enumerate_empty_recovery
        if observe_matchups is not None and not callable(observe_matchups):
            raise TypeError("matchup observer must be callable")
        self.observe_matchups = observe_matchups
        if observe_preparation_party is not None and not callable(observe_preparation_party):
            raise TypeError("party-count observer must be callable")
        self.observe_preparation_party=observe_preparation_party
        if type(reuse_local_route_queries) is not bool:
            raise TypeError("local route reuse must be an explicit boolean")
        self.reuse_local_route_queries = reuse_local_route_queries
        self.last_route_reuse_counts = None
        self._observed = None

    def enumerate(self, runtime, actions, observation):
        """Optional per-menu pure-route reuse; never retained during execution."""
        scope = frozen_local_route_inventory() if self.reuse_local_route_queries else nullcontext()
        try:
            with scope as cache:
                result = self._enumerate(runtime, actions, observation)
                self.last_route_reuse_counts = (
                    None if cache is None else {"hits": cache.hits, "misses": cache.misses}
                )
                return result
        except BaseException:
            self._observed = None
            self.last_route_reuse_counts = None
            raise

    def _enumerate(self, runtime, actions, observation):
        self._observed = None
        state = runtime.emulator.save_state_bytes()
        base = self.enumerate_base(runtime, actions, observation)
        if self.enumerate_league_healing is not None and not any(
            b.kind is GoalKind.RECOVER_CONTROL for b in base.bindings
        ):
            binding = self.enumerate_league_healing(runtime, actions, observation)
            if binding is not None:
                if (not isinstance(binding, ExecutableGoalBinding)
                        or binding.kind is not GoalKind.RESTORE_TEAM
                        or binding.maximum_cash_debit != 0
                        or not binding.binding_ref.startswith("league-pre-entry-healing:")):
                    raise ValueError("temporary League healing requires its free native nurse")
                blocked = tuple(GoalOpportunity(
                    "league-healing-safeguard:" + kind.value, kind, GoalAvailability.UNAVAILABLE,
                    unavailable_reason=GoalUnavailableReason.TEMPORARILY_BLOCKED,
                ) for kind in GoalKind if kind is not GoalKind.RESTORE_TEAM)
                ordinary = GoalBindingSet((binding.opportunity,) + blocked, (binding,))
                if runtime.emulator.save_state_bytes() != state:
                    raise ValueError("League healing observer changed native state")
                self._observed = (runtime, state, ordinary, (), {}, {})
                return ordinary
        if self.enumerate_league_capacity is not None and not any(
            b.kind is GoalKind.RECOVER_CONTROL for b in base.bindings
        ):
            binding = self.enumerate_league_capacity(runtime, actions, observation)
            if binding is not None:
                if (not isinstance(binding, ExecutableGoalBinding)
                        or binding.kind is not GoalKind.MANAGE_STORAGE
                        or binding.maximum_cash_debit != 0
                        or not binding.binding_ref.startswith("league-medicine-capacity:")):
                    raise ValueError("temporary League capacity requires free native key storage")
                blocked = tuple(GoalOpportunity(
                    "league-capacity-safeguard:" + kind.value, kind, GoalAvailability.UNAVAILABLE,
                    unavailable_reason=GoalUnavailableReason.TEMPORARILY_BLOCKED,
                ) for kind in GoalKind if kind is not GoalKind.MANAGE_STORAGE)
                ordinary = GoalBindingSet((binding.opportunity,) + blocked, (binding,))
                if runtime.emulator.save_state_bytes() != state:
                    raise ValueError("League capacity observer changed native state")
                self._observed = (runtime, state, ordinary, (), {}, {})
                return ordinary
        if self.enumerate_medicine_reserve is not None and not any(
            b.kind is GoalKind.RECOVER_CONTROL for b in base.bindings
        ):
            binding = self.enumerate_medicine_reserve(runtime, actions, observation)
            if binding is not None:
                if not isinstance(binding, ExecutableGoalBinding):
                    raise ValueError("temporary medicine support requires a quoted native purchase")
                quote = binding.resource_quote
                if (binding.kind is not GoalKind.RESUPPLY or quote is None
                        or not quote.purchase_cost or quote.funding_proceeds
                        or quote.expected_income
                        or len(quote.reserves) != 1 or quote.reserves[0].resource != "recovery"):
                    raise ValueError("temporary medicine support requires a quoted native purchase")
                blocked = tuple(GoalOpportunity(
                    "medicine-safeguard:" + kind.value, kind, GoalAvailability.UNAVAILABLE,
                    unavailable_reason=GoalUnavailableReason.TEMPORARILY_BLOCKED,
                ) for kind in GoalKind if kind is not GoalKind.RESUPPLY)
                ordinary = GoalBindingSet((binding.opportunity,) + blocked, (binding,))
                if runtime.emulator.save_state_bytes() != state:
                    raise ValueError("medicine reserve observer changed native state")
                self._observed = (runtime, state, ordinary, (), {}, {})
                return ordinary
        branches = () if any(b.kind is GoalKind.RECOVER_CONTROL for b in base.bindings) else (
            self.enumerate_branches(runtime, actions, observation)
        )
        if (not isinstance(branches, tuple) or any(
            not isinstance(row, tuple) or len(row) != 2
            or not isinstance(row[1], OptionChallenge) for row in branches
        )):
            raise ValueError("native branches need immutable executor/challenge pairs")
        ordinary, extra = plural_story_bindings(
            base, tuple(b for b, _ in branches), observation.situation,
        )
        preparations = ()
        if self.enumerate_preparation is not None and not any(
            b.kind is GoalKind.RECOVER_CONTROL for b in ordinary.bindings
        ):
            preparations = self.enumerate_preparation(runtime, actions, observation)
            if (not isinstance(preparations, tuple) or any(
                not isinstance(row, tuple) or len(row) != 2
                or not isinstance(row[1], OptionPreparation) for row in preparations
            )):
                raise ValueError("preparation needs immutable executor/descriptor pairs")
            ordinary, additional = plural_preparation_bindings(
                ordinary, tuple(b for b, _ in preparations), observation.situation,
            )
            extra += additional
        if self.enumerate_collection is not None and not any(
            b.kind is GoalKind.RECOVER_CONTROL for b in ordinary.bindings
        ):
            collection = self.enumerate_collection(runtime, actions, observation)
            if (not isinstance(collection, tuple) or any(
                not isinstance(row, RedLiveSupplementalOption)
                or row.binding.kind not in {GoalKind.ACQUIRE_SPECIES, GoalKind.EVOLVE_SPECIES}
                for row in collection
            )):
                raise ValueError("collection needs immutable acquisition/evolution supplements")
            refs = [b.binding_ref for b in ordinary.bindings] + [
                s.binding.binding_ref for s in extra + collection
            ]
            if len(refs) != len(set(refs)):
                raise ValueError("collection repeats a native executor")
            extra += collection
        if self.enumerate_resources is not None and not any(
            b.kind is GoalKind.RECOVER_CONTROL for b in ordinary.bindings
        ):
            resources = self.enumerate_resources(runtime, actions, observation)
            if (not isinstance(resources, tuple) or any(
                not isinstance(row, (ExecutableGoalBinding, RedLiveSupplementalOption))
                or (row.binding.kind if isinstance(row, RedLiveSupplementalOption)
                    else row.kind) is not GoalKind.RESUPPLY for row in resources
            )):
                raise ValueError("resource peers need immutable typed resupply options")
            # Some providers already carry genuine prospective economy facts.
            # Do not erase those descriptors by extracting the bare executor
            # and rebuilding a generic OTHER/zero-spend candidate.
            described = tuple(row for row in resources
                              if isinstance(row, RedLiveSupplementalOption))
            resources = tuple(row for row in resources
                              if isinstance(row, ExecutableGoalBinding))
            resources = _resource_peers_without_base_duplicates(ordinary, resources)
            ordinary, additional = plural_resource_bindings(
                ordinary, resources, observation.situation,
            )
            refs = ([b.binding_ref for b in ordinary.bindings]
                    + [s.binding.binding_ref for s in extra + additional + described])
            if len(refs) != len(set(refs)):
                raise ValueError("resource peers repeat a native executor")
            extra += additional + described
        if runtime.emulator.save_state_bytes() != state:
            raise ValueError("branch inventory changed native state")
        machine_rows = ()
        if self.enumerate_owned_machines is not None and not any(
            b.kind is GoalKind.RECOVER_CONTROL for b in ordinary.bindings
        ):
            machine_rows = self.enumerate_owned_machines(runtime, actions, observation)
            if not isinstance(machine_rows, tuple) or any(
                not isinstance(row, RedLiveSupplementalOption)
                or row.binding.kind is not GoalKind.DEVELOP_TEAM for row in machine_rows
            ):
                raise ValueError("owned machines need immutable team-development supplements")
            refs = [b.binding_ref for b in ordinary.bindings] + [
                s.binding.binding_ref for s in extra + machine_rows
            ]
            if len(refs) != len(set(refs)):
                raise ValueError("owned machines repeat a native executor")
            if runtime.emulator.save_state_bytes() != state:
                raise ValueError("owned-machine observer changed native state")
            extra += machine_rows
        if not ordinary.bindings and not extra and self.enumerate_empty_recovery is not None:
            recovery = self.enumerate_empty_recovery(runtime, actions, observation)
            if recovery is not None:
                if (not isinstance(recovery, ExecutableGoalBinding)
                        or recovery.kind is not GoalKind.RECOVER_CONTROL
                        or recovery.maximum_cash_debit != 0
                        or not recovery.binding_ref.startswith("pokemon.red:empty-indoor-departure:")):
                    raise ValueError("empty-menu recovery requires its bounded indoor departure")
                ordinary = GoalBindingSet(
                    tuple(o for o in ordinary.opportunities if o.kind is not GoalKind.RECOVER_CONTROL)
                    + (recovery.opportunity,), (recovery,),
                )
            if runtime.emulator.save_state_bytes() != state:
                raise ValueError("empty-menu recovery observer changed native state")
        self._observed = (runtime, state, ordinary, extra,
                          {**{b.binding_ref: challenge for b, challenge in branches},
                           **{s.binding.binding_ref: s.candidate.challenge for s in machine_rows
                              if s.candidate.challenge is not None}},
                          {b.binding_ref: facts for b, facts in preparations})
        return ordinary

    def _current(self, runtime):
        if (self._observed is None or self._observed[0] is not runtime
            or runtime.emulator.save_state_bytes() != self._observed[1]):
            raise ValueError("native branch inventory is absent or stale")
        return self._observed

    def supplements(self, runtime, actions, observation, bindings):
        _, _, ordinary, extra, _, _ = self._current(runtime)
        if bindings is not ordinary:
            raise ValueError("supplements do not belong to the observed inventory")
        return extra

    def challenges(self, runtime, bindings, supplements, boundary):
        return self._descriptors(runtime, bindings, supplements, boundary, 4)

    def preparations(self, runtime, bindings, supplements, boundary):
        return self._descriptors(runtime, bindings, supplements, boundary, 5)

    def matchups(self, runtime, bindings, supplements, boundary):
        # Reuse exact executor identity and state guards, not objective matching.
        self._descriptors(runtime, bindings, supplements, boundary, 4)
        if self.observe_matchups is None:
            return None
        result = self.observe_matchups(runtime, bindings, supplements, boundary)
        self._current(runtime)
        return result

    def preparation_party(self,runtime,bindings,supplements,boundary):
        self._descriptors(runtime,bindings,supplements,boundary,4)
        result=self.observe_preparation_party(runtime,bindings,supplements,boundary)
        self._current(runtime)
        return result

    def native_callbacks(self):
        """Keep enumeration and descriptors together for the existing native loop."""
        callbacks = dict(enumerate_bindings=self.enumerate,
                         enumerate_supplements=self.supplements,
                         observe_challenges=self.challenges,
                         observe_preparations=self.preparations)
        if self.observe_matchups is not None:
            callbacks["observe_matchups"] = self.matchups
        if self.observe_preparation_party is not None:
            callbacks["observe_preparation_party"]=self.preparation_party
        return callbacks

    def _descriptors(self, runtime, bindings, supplements, boundary, index):
        current = self._current(runtime)
        _, state, ordinary, extra, _, _ = current
        descriptors = current[index]
        expected = {b.binding_ref: b for b in ordinary.bindings}
        expected.update((s.binding.binding_ref, s.binding) for s in extra)
        actual = (*bindings.bindings, *(s.binding for s in supplements))
        if boundary.state != state or any(expected.get(b.binding_ref) is not b for b in actual):
            raise ValueError("challenges do not belong to the observed executors")
        refs = {b.binding_ref for b in actual}
        return {ref: value for ref, value in descriptors.items() if ref in refs}


def plural_story_bindings(base, branches, situation):
    """Replace only the story inventory; retain preparation/resources/recovery."""
    return _plural_bindings(base, branches, situation, GoalKind.ADVANCE_STORY, "story")


def plural_preparation_bindings(base, branches, situation):
    """Replace only development; each supplied executor owns its own trainee."""
    return _plural_bindings(base, branches, situation, GoalKind.DEVELOP_TEAM, "preparation")


def plural_resource_bindings(base, additions, situation):
    """Keep every existing resource choice and expose additional quoted orders.

    The ordinary goal-manager's earning/purchase pair contract is unchanged.
    Additional concrete orders use the existing mixed-menu seam, just like
    multiple story branches or training doses; no order is selected here.
    """
    if not isinstance(base, GoalBindingSet) or not isinstance(additions, tuple):
        raise TypeError("typed inventory and immutable resource additions required")
    existing = tuple(b for b in base.bindings if b.kind is GoalKind.RESUPPLY)
    return _plural_bindings(
        base, existing + additions, situation, GoalKind.RESUPPLY, "resource",
    )


def merge_resource_observer_bindings(rows):
    """Merge repeated concrete offers from independent resource observers.

    A shop observer and a medicine-income observer can quote the same trainer.
    Retain one executor only when all non-callable guards and quotes agree.
    Described supplements retain their separate strict duplicate checks.
    This only normalizes observer output; it neither selects nor runs an offer.
    """
    if not isinstance(rows, tuple):
        raise TypeError("resource observer rows must be immutable")
    seen = {}
    result = []
    for row in rows:
        if isinstance(row, RedLiveSupplementalOption):
            result.append(row)
            continue
        if not isinstance(row, ExecutableGoalBinding) or row.kind is not GoalKind.RESUPPLY:
            raise ValueError("resource observer rows need typed resupply bindings")
        prior = seen.get(row.binding_ref)
        if prior is None:
            seen[row.binding_ref] = row
            result.append(row)
        elif replace(row, execute=prior.execute, verify=prior.verify) != prior:
            raise ValueError("resource observers conflict on one executor")
    return tuple(result)


def _resource_peers_without_base_duplicates(base, additions):
    """The same state/profile quote can be found by both resource observers.

    Retain the base executor only when every non-callable guard/quote agrees.
    Conflicting identities and duplicates inside the peer list still fail;
    distinct shops/orders stay model-visible and no executor runs here.
    """
    if not isinstance(additions, tuple) or any(
        not isinstance(b, ExecutableGoalBinding) or b.kind is not GoalKind.RESUPPLY
        for b in additions
    ):
        raise ValueError("resource peers need immutable typed resupply bindings")
    existing = {b.binding_ref: b for b in base.bindings if b.kind is GoalKind.RESUPPLY}
    result = []
    for binding in additions:
        prior = existing.get(binding.binding_ref)
        if prior is None:
            result.append(binding)
        elif replace(binding, execute=prior.execute, verify=prior.verify) != prior:
            raise ValueError("resource peer conflicts with the base executor")
    return tuple(result)


def _plural_bindings(base, branches, situation, kind, label):
    if not isinstance(base, GoalBindingSet) or not isinstance(branches, tuple):
        raise TypeError("typed inventory and immutable story branches required")
    if any(
        not isinstance(b, ExecutableGoalBinding) or b.kind is not kind
        for b in branches
    ):
        raise ValueError(f"plural {label} inventory contains a non{label} binding")
    if len({b.binding_ref for b in branches}) != len(branches):
        repeated = sorted({
            b.binding_ref for b in branches
            if sum(other.binding_ref == b.binding_ref for other in branches) > 1
        })
        raise ValueError(f"duplicate {label} binding: {repeated}")
    if any(b.kind is GoalKind.RECOVER_CONTROL for b in base.bindings):
        return base, ()
    others = tuple(b for b in base.bindings if b.kind is not kind)
    if {b.binding_ref for b in branches} & {b.binding_ref for b in others}:
        raise ValueError("story binding collides with another goal")
    unavailable = GoalOpportunity(
        label + ":no-current-executor",
        kind,
        GoalAvailability.UNAVAILABLE,
        unavailable_reason=GoalUnavailableReason.NO_LEGAL_TARGET,
    )
    opportunities = tuple(o for o in base.opportunities if o.kind is not kind)
    primary = branches[:1]
    ordinary = GoalBindingSet(
        opportunities + ((primary[0].opportunity if primary else unavailable),),
        others + primary,
        allow_resource_variants=base.allow_resource_variants,
    )
    supplements = []
    for binding in branches[1:]:
        # Project each through exactly the ordinary story feature contract.
        masked = GoalOpportunity(
            "story:projection-mask",
            GoalKind.EXPLORE,
            GoalAvailability.UNAVAILABLE,
            unavailable_reason=GoalUnavailableReason.NO_LEGAL_TARGET,
        )
        question = GoalBindingSet((binding.opportunity, masked), (binding,)).question(situation)
        candidate = project_living_dex_goal_candidate(
            question,
            0,
            feature_version=5,
            binding_ref=binding.binding_ref,
        )
        supplements.append(supplemental_live_option(binding, candidate))
    return ordinary, tuple(supplements)
