"""Explicit consequence-only context sharing; legacy option vectors stay exact.

Shared columns add no observations. The declared ridge geometry favors common
effects while retaining the original action-dependent columns. It is a learning
hypothesis, not a guarantee that preparation has the same value in every state.
"""

from functools import lru_cache

from .living_dex_option_value import LivingDexOptionKind, option_feature_names
from .player_option_challenge import CHALLENGE_NAMES
from .player_readiness import READINESS_NAMES

from .player_preparation_party_context import PARTY_PROJECTION, TAIL_NAMES, PreparationPartyCounts

SHARED_CONTEXT = "shared_context_v1"
PROSPECTIVE_CONTEXT = "prospective_context_v1"
# Readiness object presence is not battle-history presence. Preserve current
# measurements/knownness; both level-gap fields refer to the LAST opponent.
PROSPECTIVE_READINESS_NAMES = (
    "observed", "current.combat_level_spread", "current.hp_fraction",
    "current.fainted_fraction", "current.status_fraction", "current.pp_known",
    "current.pp_fraction",
)


@lru_cache(maxsize=1)
def _prospective_indices(feature_version):
    if type(feature_version) is not int or feature_version != 15:
        raise ValueError("prospective consequence context requires explicit raw V15 features")
    names = option_feature_names(feature_version)
    return tuple(i for i, name in enumerate(names)
        if not name.startswith("readiness.")
        or name.split("_x_", 1)[-1] in PROSPECTIVE_READINESS_NAMES)

INTERACTION_SCALE_MULTIPLIER = 4.0
MINIMUM_CONTEXT_SCALE = 0.1


def consequence_feature_names(feature_version, context_projection="identity"):
    raw = option_feature_names(feature_version)
    if context_projection == "identity":
        return raw
    if context_projection == PARTY_PROJECTION:
        return consequence_feature_names(feature_version,PROSPECTIVE_CONTEXT)+TAIL_NAMES
    if context_projection == PROSPECTIVE_CONTEXT:
        return tuple(raw[i] for i in _prospective_indices(feature_version))
    if type(context_projection) is not str or context_projection != SHARED_CONTEXT or feature_version not in (10, 15):
        raise ValueError("shared consequence context requires explicit raw V10 or V15 features")
    return raw + tuple(
        f"shared_{family}.{name}"
        for family, names in (("readiness", READINESS_NAMES), ("challenge", CHALLENGE_NAMES))
        for name in names
    )


@lru_cache(maxsize=2)
def _shared_indices(feature_version):
    names = option_feature_names(feature_version)
    return tuple(
        tuple(names.index(f"{family}.{kind.value}_x_{name}") for kind in LivingDexOptionKind)
        for family, members in (("readiness", READINESS_NAMES), ("challenge", CHALLENGE_NAMES))
        for name in members
    )


def project_consequence_features(features, *, feature_version, context_projection="identity", party_context=None):
    consequence_feature_names(feature_version, context_projection)
    if len(features) != len(option_feature_names(feature_version)):
        raise ValueError("consequence projection requires raw feature width")
    raw = tuple(features)
    if context_projection == PARTY_PROJECTION:
        if type(party_context) is not PreparationPartyCounts:
            raise ValueError("party-count consequence projection requires complete observed counts")
        names=option_feature_names(feature_version)
        develop=raw[names.index("kind.develop")];preparation=raw[names.index("preparation.present")]
        if develop not in (0,1) or preparation not in (0,1) or preparation and not develop:
            raise ValueError("party-count projection requires a genuine level-preparation kind")
        return project_consequence_features(raw,feature_version=feature_version,context_projection=PROSPECTIVE_CONTEXT)+(party_context.vector() if preparation else (0.0,)*4)
    if party_context is not None:
        raise ValueError("legacy consequence projections do not consume party-count side context")
    if context_projection == "identity":
        return raw
    if context_projection == PROSPECTIVE_CONTEXT:
        return tuple(raw[i] for i in _prospective_indices(feature_version))
    return raw + tuple(sum(raw[index] for index in indices) for indices in _shared_indices(feature_version))


def consequence_normalization_scale(x, *, feature_version, context_projection="identity"):
    names = consequence_feature_names(feature_version, context_projection)
    if x.ndim != 2 or x.shape[1] != len(names):
        raise ValueError("consequence normalization requires projected feature width")
    scale = x.std(axis=0)
    scale[scale == 0.0] = 1.0
    if context_projection == SHARED_CONTEXT:
        for index, name in enumerate(names):
            gated = name.startswith(("readiness.", "challenge."))
            shared = name.startswith(("shared_readiness.", "shared_challenge."))
            if gated or shared:
                scale[index] = max(scale[index], MINIMUM_CONTEXT_SCALE)
            if gated:
                scale[index] *= INTERACTION_SCALE_MULTIPLIER
    return scale


def context_projection_metadata(context_projection):
    if context_projection == PARTY_PROJECTION:
        return dict(context_projection=PARTY_PROJECTION,context_projection_parameters=dict(
            raw_feature_version=15,raw_feature_width=len(option_feature_names(15)),
            prefix_projection=PROSPECTIVE_CONTEXT,prefix_width=len(consequence_feature_names(15,PROSPECTIVE_CONTEXT)),
            side_context_schema="pokemon.core.preparation-party-counts.v1",tail_names=list(TAIL_NAMES),
            gate="genuine_level_preparation",missing_context="reject",normalization="existing_standard_deviation_v1",constant_scale=1.0))
    if context_projection == "identity":
        return {}
    if context_projection == PROSPECTIVE_CONTEXT:
        return dict(context_projection=context_projection, context_projection_parameters=dict(
            raw_feature_version=15,
            raw_feature_width=len(option_feature_names(15)),
            selected_indices=list(_prospective_indices(15)),
            retained_readiness_names=list(PROSPECTIVE_READINESS_NAMES),
            normalization="existing_standard_deviation_v1",
            constant_scale=1.0,
        ))
    if context_projection != SHARED_CONTEXT:
        raise ValueError("unsupported consequence context projection")
    return dict(context_projection=context_projection, context_projection_parameters=dict(
        interaction_scale_multiplier=INTERACTION_SCALE_MULTIPLIER,
        minimum_context_scale=MINIMUM_CONTEXT_SCALE,
        constant_scale=1.0,
    ))
