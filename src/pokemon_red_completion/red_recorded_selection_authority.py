"""Private pre-input selector inputs; no controller or executable callback codec.

Replay authenticates recorded safety selection and binding identity. It does not
prove native observation truth or that an arbitrary Python executor was honest.
"""

from dataclasses import asdict

from .goal_manager import (
    GoalAvailability,
    GoalKind,
    GoalOpportunity,
    GoalSituation,
    GoalUnavailableReason,
)
from .goal_manager_runtime import ExecutableGoalBinding, GoalBindingSet
from .goal_resource_quote import GoalResourceQuote
from .goal_search_memory import GoalSearchHistory
from .living_dex_goal_policy import DEFAULT_LIVING_DEX_GOAL_UTILITY, living_dex_option_kind_for_goal
from .living_dex_policy_codec import restore_living_dex_policy_menu
from .player_readiness import PlayerReadiness
from .player_sequence_policy import SequenceChoiceContext, SequencePolicy
from .provenance import canonical_sha256
from .red_live_option_menu import RedLiveOptionChoice, RedLiveOptionSet, select_red_live_option
from .red_player_support import RedPlayerSupport, RedPlayerSupportChoice


def _opportunity_document(opportunity):
    return dict(binding_ref=opportunity.binding_ref, policy=opportunity.policy_dict())


def record_selection_authority(options, *, allow_earning_exploration: bool,
                               greedy_selection: bool = False):
    if type(greedy_selection) is not bool:
        raise TypeError("highest-score authority opt-in must be boolean")
    support = isinstance(options, RedPlayerSupport)
    original = options.bindings if support else options.original_bindings
    bindings = original.bindings if support else options.bindings
    return dict(
        schema="pokemon.red.recorded-selection-authority.v1",
        allow_earning_exploration=allow_earning_exploration,
        **({"greedy_selection": True} if greedy_selection else {}),
        situation=None if support else asdict(options.situation),
        opportunities=[_opportunity_document(o) for o in original.opportunities],
        original_binding_refs=[b.binding_ref for b in original.bindings],
        allow_resource_variants=original.allow_resource_variants,
        live_bindings=[_opportunity_document(b.opportunity) for b in bindings],
        ordinary_binding_refs=[] if support else sorted(options.ordinary_binding_refs),
        ordering_seed_sha256=None if support else options.ordering_seed_sha256,
    )


def _restore_opportunity(document):
    p = document["policy"]
    o = GoalOpportunity(
        binding_ref=document["binding_ref"], kind=GoalKind(p["kind"]),
        availability=GoalAvailability(p["availability"]),
        estimated_effort=p["estimated_effort"], estimated_risk=p["estimated_risk"],
        unavailable_reason=None if p["unavailable_reason"] is None
        else GoalUnavailableReason(p["unavailable_reason"]),
        resource_quote=None if "resource_quote" not in p
        else GoalResourceQuote.from_public_dict(p["resource_quote"]),
        search_history=None if "search_history" not in p
        else GoalSearchHistory.from_public_dict(p["search_history"]),
    )
    if canonical_sha256(_opportunity_document(o)) != canonical_sha256(document):
        raise ValueError("recorded opportunity differs")
    return o


def _inert(*args, **kwargs):
    raise RuntimeError("recorded selector replay cannot execute or verify a goal")


def _binding(o):
    return ExecutableGoalBinding(
        o.binding_ref, o.kind, o.estimated_effort, o.estimated_risk,
        _inert, _inert, resource_quote=o.resource_quote, search_history=o.search_history,
    )


def replay_selection_authority(model, intent, decision, *, allow_earning_exploration: bool,
                               sequence_policy: SequencePolicy | None = None):
    """Return the exact selected private ref, without reconstructing callbacks."""
    document = intent["private_selection_authority"]
    greedy_selection = document.get("greedy_selection", False)
    if type(greedy_selection) is not bool or (greedy_selection and sequence_policy is not None):
        raise ValueError("recorded highest-score authority differs")
    context_document = intent.get("sequence_context")
    if (sequence_policy is None) != (context_document is None):
        raise ValueError("recorded sequence selection requires its frozen policy and context")
    context = None
    if sequence_policy is not None:
        if intent.get("model_sha256") != sequence_policy.model_sha256:
            raise ValueError("recorded sequence policy identity differs")
        context = SequenceChoiceContext.from_document(context_document)
    if (type(allow_earning_exploration) is not bool
        or document.get("allow_earning_exploration") is not allow_earning_exploration):
        raise ValueError("recorded earning authority differs")
    opportunities = tuple(_restore_opportunity(o) for o in document["opportunities"])
    refs = document["original_binding_refs"]
    by_ref = {o.binding_ref: o for o in opportunities}
    original = GoalBindingSet(
        opportunities, tuple(_binding(by_ref[r]) for r in refs),
        document["allow_resource_variants"],
    )
    bindings = tuple(_binding(_restore_opportunity(o)) for o in document["live_bindings"])
    menu = intent["menu"]
    options: RedPlayerSupport | RedLiveOptionSet
    choice: RedPlayerSupportChoice | RedLiveOptionChoice
    if menu["schema"] == "pokemon.red.player-support.v1":
        if context is not None:
            raise ValueError("forced support cannot have a sequence query context")
        options = RedPlayerSupport(original, PlayerReadiness.from_public(menu["readiness"]))
        choice = RedPlayerSupportChoice(options)
    else:
        restored = restore_living_dex_policy_menu(
            menu["menu"], binding_refs=tuple(b.binding_ref for b in bindings),
        )
        if any(living_dex_option_kind_for_goal(b.kind, feature_version=restored.feature_version)
               is not c.features.kind for b, c in zip(bindings, restored.candidates, strict=True)):
            raise ValueError("recorded executor kind differs from selected menu")
        options = RedLiveOptionSet(
            GoalSituation(**document["situation"]), original, restored, bindings,
            frozenset(document["ordinary_binding_refs"]), document["ordering_seed_sha256"],
        )
        choice = select_red_live_option(
            model, options, seed=intent["selection_seed"],
            allow_earning_exploration=allow_earning_exploration,
            greedy_selection=greedy_selection,
            sequence_policy=sequence_policy, sequence_context=context,
            utility=(DEFAULT_LIVING_DEX_GOAL_UTILITY if sequence_policy is None
                     else sequence_policy.immediate_utility),
            exploration_mix=.25 if sequence_policy is None else sequence_policy.exploration_mix,
        )
    if (canonical_sha256(record_selection_authority(
            options, allow_earning_exploration=allow_earning_exploration,
            greedy_selection=greedy_selection))
        != canonical_sha256(document)
        or canonical_sha256(options.public_dict()) != canonical_sha256(menu)
        or canonical_sha256(choice.public_dict()) != canonical_sha256(decision)):
        raise ValueError("recorded safety/selection authority does not replay")
    return choice.selected_binding.binding_ref
