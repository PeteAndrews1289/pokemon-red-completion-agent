"""Honest view of the completion-aware party learner before outcome collection."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from pokemon_red_completion.progress_dashboard import (
    DashboardExperimentState,
    DashboardLearningComponent,
    DashboardModelState,
    DashboardSnapshot,
    ProgressDashboardError,
)

PARTY_DEVELOPMENT_READINESS_EVIDENCE_SCHEMA = (
    "pokemon-party-development-v2-readiness-evidence-v2"
)
PARTY_DEVELOPMENT_READINESS_STATUS = (
    "two_venue_priors_pp_preparation_ready_catalog_unfrozen"
)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def party_development_readiness_dashboard_snapshot(
    evidence: Mapping[str, object],
) -> DashboardSnapshot:
    """Project a path-free readiness receipt without calling it model training."""

    if not isinstance(evidence, Mapping):
        raise TypeError("party-development readiness evidence must be a mapping")
    if evidence.get("schema") != PARTY_DEVELOPMENT_READINESS_EVIDENCE_SCHEMA:
        raise ProgressDashboardError(
            "party-development readiness evidence schema is unsupported"
        )
    if evidence.get("status") != PARTY_DEVELOPMENT_READINESS_STATUS:
        raise ProgressDashboardError(
            "party-development readiness evidence status is unsupported"
        )

    prior = _mapping(evidence, "prior")
    inventory = _mapping(evidence, "checkpoint_inventory")
    reservation = _mapping(evidence, "reservation")
    venue_priors = _mapping(evidence, "venue_priors")
    pp_preparation = _mapping(evidence, "pp_preparation")
    first_fit = _mapping(evidence, "first_fit_gate")
    protected = _mapping(evidence, "protected_access")
    if prior.get("bound") is not True:
        raise ProgressDashboardError("party-development historical prior is not bound")
    if (
        first_fit.get("prospective_catalog_frozen") is not False
        or first_fit.get("candidate_adapter_ready") is not True
        or first_fit.get("venue_prior_registry_frozen") is not True
        or first_fit.get("model_fit") is not False
        or first_fit.get("authority_promoted") is not False
    ):
        raise ProgressDashboardError(
            "party-development readiness evidence overstates the first-fit gate"
        )

    protected_counts = {
        key: _count(protected, key)
        for key in (
            "controller_actions",
            "teacher_queries",
            "sealed_red_cases_opened",
            "crystal_cases_opened",
            "full_game_replays",
        )
    }
    if any(protected_counts.values()):
        raise ProgressDashboardError(
            "party-development readiness cannot include protected execution"
        )

    train_pool, development_pool = _partition_counts(inventory, "partition_counts")
    train_semantics, development_semantics = _partition_counts(
        inventory, "unique_semantic_contexts"
    )
    train_ready, development_ready = _partition_counts(
        inventory, "ready_multi_candidate_contexts"
    )
    checkpoint_count = _count(inventory, "checkpoint_count")
    if checkpoint_count != train_pool + development_pool:
        raise ProgressDashboardError(
            "party-development inventory partition counts do not reconcile"
        )
    if (
        train_semantics > train_pool
        or development_semantics > development_pool
        or train_ready > train_pool
        or development_ready > development_pool
    ):
        raise ProgressDashboardError(
            "party-development inventory diversity exceeds its checkpoint pool"
        )

    required_train = _positive_count(first_fit, "minimum_train_outcomes")
    required_development = _positive_count(
        first_fit, "minimum_development_outcomes"
    )
    collected_train = _count(first_fit, "collected_train_outcomes")
    collected_development = _count(
        first_fit, "collected_development_outcomes"
    )
    if collected_train or collected_development:
        raise ProgressDashboardError(
            "unfrozen party-development catalog cannot report collected outcomes"
        )
    total_required = required_train + required_development

    reserved_train, reserved_development = _partition_counts(
        reservation, "reserved_roots"
    )
    prepared_train, prepared_development = _partition_counts(
        pp_preparation, "materialized_sources"
    )
    pp_train, pp_development = _partition_counts(
        pp_preparation, "reserved_sources"
    )
    if (
        reserved_train != required_train
        or reserved_development != required_development
        or _count(reservation, "frozen_menus") != 0
        or _count(reservation, "direct_roots_preflighted") != 12
        or _count(venue_priors, "entries") != 2
        or venue_priors.get("frozen") is not True
        or pp_train != 1
        or pp_development != 1
        or prepared_train != 0
        or prepared_development != 0
        or pp_preparation.get("contract_qualified") is not True
        or pp_preparation.get("controller_authorization_granted") is not False
        or pp_preparation.get("ordinary_battle_consumption") is not True
        or pp_preparation.get("healing_allowed") is not False
        or pp_preparation.get("party_switching_allowed") is not False
        or pp_preparation.get("memory_edit_allowed") is not False
        or pp_preparation.get("teacher_or_model_allowed") is not False
    ):
        raise ProgressDashboardError(
            "party-development PP preparation gate is inconsistent"
        )
    maximum_battles = _positive_count(
        pp_preparation, "maximum_completed_battles_per_source"
    )
    maximum_steps = _positive_count(
        pp_preparation, "maximum_encounter_steps_per_source"
    )
    maximum_actions = _positive_count(
        pp_preparation, "maximum_controller_actions_per_source"
    )
    maximum_frames = _positive_count(
        pp_preparation, "maximum_frames_per_source"
    )

    prior_train_examples = _positive_count(prior, "train_examples")
    prior_validation_examples = _positive_count(prior, "validation_examples")
    prior_validation_correct = _count(prior, "validation_correct")
    prior_baseline_correct = _count(prior, "shape_baseline_correct")
    if (
        prior_validation_correct > prior_validation_examples
        or prior_baseline_correct > prior_validation_examples
    ):
        raise ProgressDashboardError(
            "party-development prior validation counts are inconsistent"
        )
    if _count(prior, "outcome_updates") != 0:
        raise ProgressDashboardError(
            "party-development initial prior cannot contain outcome updates"
        )
    prior_sha256 = _digest(prior, "v1_model_canonical_sha256")
    initial_sha256 = _digest(prior, "v2_initial_model_canonical_sha256")
    validation_lineages = _positive_count(
        prior, "independent_validation_lineages"
    )

    hp_bins = _partition_text(inventory, "hp_bins")
    pp_bins = _partition_text(inventory, "pp_bins")
    routes = _partition_text(inventory, "evolution_routes")
    goals = _partition_text(inventory, "goal_hints")

    return DashboardSnapshot(
        game="Pokémon Red",
        run_status="waiting",
        stage="Completion-aware party learner · pre-collection gate",
        message=(
            f"Two venue priors and {reserved_train + reserved_development} source roots are "
            f"reserved. Two natural middle-PP states remain unmaterialized; outcome collection "
            f"is 0/{total_required} and model fitting has not begun."
        ),
        stage_progress=0.0,
        location="Natural PP preparation gate · controller authorization absent",
        collection_target=124,
        model=DashboardModelState(
            mode="waiting",
            candidate="Completion-aware party scorer v2 · authenticated prior only",
            choice="No live decisions · no completion-aware outcome fit",
            decisions=0,
            teacher_queries=0,
            fallbacks=0,
        ),
        experiment=DashboardExperimentState(
            phase="catalog",
            zero_shot_completed=1,
            zero_shot_total=1,
            adaptation_completed=0,
            adaptation_total=total_required,
            sealed_completed=0,
            sealed_total=1,
            predictions_committed=False,
            heading="Party learner readiness",
            eyebrow="Red curriculum · transferable completion policy",
            counter_labels=(
                "Historical prior bound",
                "Prospective outcomes",
                "Authority promotions",
            ),
        ),
        learning_components=(
            DashboardLearningComponent(
                name="Historical team ranker prior",
                scope="Identity-free Red trainee and venue rankings; no live authority",
                status="passed",
                authority="offline",
                train_examples=prior_train_examples,
                validation_examples=prior_validation_examples,
                validation_correct=prior_validation_correct,
                baseline_correct=prior_baseline_correct,
                model_sha256=prior_sha256,
                independent_validation_units=validation_lineages,
                baseline_id="shape_only",
            ),
            DashboardLearningComponent(
                name="Completion-aware party scorer v2",
                scope=(
                    "Balance, evolution, living collection, roles, survival and venue cost; "
                    "new features remain at zero weight"
                ),
                status="offline",
                authority="offline",
                train_examples=0,
                validation_examples=0,
                validation_correct=0,
                baseline_correct=None,
                model_sha256=initial_sha256,
                independent_validation_units=0,
            ),
        ),
        events=(
            (
                f"Read-only pool: {train_pool} train / {development_pool} development "
                f"checkpoints; controller actions 0"
            ),
            (
                f"Reserved curriculum roots: {reserved_train} train / "
                f"{reserved_development} development · frozen menus 0"
            ),
            "Compatible venue priors 2/2 · Route 11 and Cave evidence frozen",
            (
                "Natural middle-PP preparations 0/2 · one train and one development "
                "source · authorization absent"
            ),
            (
                f"Distinct semantic contexts: {train_semantics} train / "
                f"{development_semantics} development"
            ),
            (
                f"Multi-candidate-ready contexts: {train_ready} train / "
                f"{development_ready} development"
            ),
            f"Health bins · train {_join(hp_bins[0])} · development {_join(hp_bins[1])}",
            f"PP bins · train {_join(pp_bins[0])} · development {_join(pp_bins[1])}",
            f"Evolution routes · train {_join(routes[0])} · development {_join(routes[1])}",
            f"Goal hints · train {_join(goals[0])} · development {_join(goals[1])}",
            (
                f"First descriptive fit requires {required_train} train + "
                f"{required_development} untouched development outcomes"
            ),
            (
                "Title-neutral candidate adapter ready · direct roots preflighted 12/14 · "
                "concrete frozen Red menus 0"
            ),
            (
                f"Per-source hard bounds · battles {maximum_battles} · encounter steps "
                f"{maximum_steps} · controller actions {maximum_actions} · frames {maximum_frames}"
            ),
            (
                "Preparation policy · ordinary battles only · no healing, switching, capture, "
                "memory edit, teacher, model or learner outcome"
            ),
            "Prospective outcomes 0 · completion-aware model updates 0",
            "Teacher 0 · sealed Red 0 · Crystal 0 · full-game replays 0 · authority zero",
            (
                "Next: independent plan review, explicit authorization for each single-use "
                "preparation, then read-only freeze and review of the exact 8+6 catalog"
            ),
        ),
    )


def _mapping(source: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = source.get(key)
    if not isinstance(value, Mapping):
        raise ProgressDashboardError(
            f"party-development {key.replace('_', ' ')} is invalid"
        )
    return value


def _count(source: Mapping[str, object], key: str) -> int:
    value = source.get(key)
    if type(value) is not int or value < 0:  # noqa: E721
        raise ProgressDashboardError(
            f"party-development {key.replace('_', ' ')} is invalid"
        )
    return value


def _positive_count(source: Mapping[str, object], key: str) -> int:
    value = _count(source, key)
    if value < 1:
        raise ProgressDashboardError(
            f"party-development {key.replace('_', ' ')} must be positive"
        )
    return value


def _digest(source: Mapping[str, object], key: str) -> str:
    value = source.get(key)
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ProgressDashboardError(
            f"party-development {key.replace('_', ' ')} is invalid"
        )
    return value


def _partition_counts(
    source: Mapping[str, object], key: str
) -> tuple[int, int]:
    counts = _mapping(source, key)
    if set(counts) != {"train", "development"}:
        raise ProgressDashboardError(
            f"party-development {key.replace('_', ' ')} partitions are invalid"
        )
    return _count(counts, "train"), _count(counts, "development")


def _partition_text(
    source: Mapping[str, object], key: str
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    values = _mapping(source, key)
    if set(values) != {"train", "development"}:
        raise ProgressDashboardError(
            f"party-development {key.replace('_', ' ')} partitions are invalid"
        )
    return _text_sequence(values, "train"), _text_sequence(values, "development")


def _text_sequence(source: Mapping[str, object], key: str) -> tuple[str, ...]:
    value = source.get(key)
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes, bytearray))
        or not value
        or any(not isinstance(item, str) or not item for item in value)
    ):
        raise ProgressDashboardError(
            f"party-development {key.replace('_', ' ')} values are invalid"
        )
    result = tuple(value)
    if len(result) != len(set(result)) or result != tuple(sorted(result)):
        raise ProgressDashboardError(
            f"party-development {key.replace('_', ' ')} values are not canonical"
        )
    return result


def _join(values: tuple[str, ...]) -> str:
    return ", ".join(value.replace("_", " ") for value in values)


__all__ = [
    "PARTY_DEVELOPMENT_READINESS_EVIDENCE_SCHEMA",
    "PARTY_DEVELOPMENT_READINESS_STATUS",
    "party_development_readiness_dashboard_snapshot",
]
