"""Fit the existing selected-outcome learner from authenticated player episodes."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from pokemon_red_completion.living_dex_causal_journal import (
    load_living_dex_authenticated_causal_examples,
    restore_living_dex_observed_arm_example,
)
from pokemon_red_completion.living_dex_goal_model_record import LivingDexGoalModelRecord
from pokemon_red_completion.living_dex_option_value import (
    evaluate_living_dex_option_value,
    fit_living_dex_option_value,
    living_dex_option_train_dataset_sha256,
    upgrade_option_value_model_for_economy,
    upgrade_option_value_model_for_optional_recovery,
    upgrade_option_value_model_for_search_history,
)
from pokemon_red_completion.private_artifacts import PrivateArtifactRoot
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_development_measured_choice import (
    RedDevelopmentMeasuredChoiceInput,
    load_red_development_measured_choice_example,
)
from pokemon_red_completion.red_player_model import (
    PLAYER_MODEL_SCHEMA,
    REGISTERED_PLAYER_MODEL_SCHEMA,
    RedPlayerModelRecord,
    load_player_goal_model_record_bytes,
)
from pokemon_red_completion.red_player_training_dataset import load_red_player_training_episode
from pokemon_red_completion.red_player_training_plan import RedPlayerTrainingPlan
from pokemon_red_completion.red_regional_choice_learning import (
    RedRegionalChoiceInput,
    load_red_regional_choice_example,
)


@dataclass(frozen=True, slots=True)
class RedPlayerEpisodeInput:
    plan: RedPlayerTrainingPlan
    episode_id: str
    manifest_sha256: str
    behavior_record: LivingDexGoalModelRecord | RedPlayerModelRecord


def fit_red_player_update(
    store: PrivateArtifactRoot,
    *,
    prior: LivingDexGoalModelRecord | RedPlayerModelRecord,
    episodes: tuple[RedPlayerEpisodeInput, ...],
    source_commit: str,
    source_bundle_sha256: str,
    regional_choices: tuple[RedRegionalChoiceInput, ...] = (),
    measured_choices: tuple[RedDevelopmentMeasuredChoiceInput, ...] = (),
    registered_objective: bool = False,
) -> dict[str, object]:
    """Retain all prior rows; add only validated, executed sampled choices.

    Callers supply the full native episode history, not a success-selected subset.
    The prior checkpoint's row fingerprints prevent forgetting or rewriting old
    examples. Repeated known roots remain correlated training, not evaluation.
    Registered opt-in starts a separate corpus: historical rewards stay archived,
    prior parameters provide behavior/comparison only, and later registered updates
    must retain their own prior rows. Regional labels require the matching
    explicit objective schema and reconstruct their actual terminal outcome.
    Measured choices without an action trace are training-only and survive all fits.
    """
    if (not episodes and not measured_choices) or len(
        {item.episode_id for item in episodes}
    ) != len(episodes):
        raise ValueError("native training episode inventory differs")
    if len({item.choice_id for item in measured_choices}) != len(measured_choices):
        raise ValueError("measured training choice inventory is duplicated")
    if (
        re.fullmatch(r"[0-9a-f]{40}", source_commit) is None
        or re.fullmatch(r"[0-9a-f]{64}", source_bundle_sha256) is None
    ):
        raise ValueError("native fitting source identity differs")
    from .registered_collection import REGISTERED_OBJECTIVE

    if type(registered_objective) is not bool:
        raise ValueError("registered fitting requires explicit opt-in")
    prior_registered = isinstance(prior, RedPlayerModelRecord) and prior.objective is not None
    if (
        isinstance(prior, RedPlayerModelRecord)
        and prior_registered
        and prior.objective != REGISTERED_OBJECTIVE
    ):
        raise ValueError("registered prior objective differs")
    if prior_registered and not registered_objective:
        raise ValueError("legacy fitting cannot consume a registered model")
    base = (
        ()
        if registered_objective
        else tuple(item.example for item in load_living_dex_authenticated_causal_examples(store))
    )
    datasets = tuple(
        load_red_player_training_episode(
            store,
            episode_id=item.episode_id,
            expected_manifest_sha256=item.manifest_sha256,
            plan=item.plan,
            behavior_model=item.behavior_record.model,
        )
        for item in episodes
    )
    if len({item.episode_id for item in regional_choices}) != len(regional_choices):
        raise ValueError("regional training choice inventory is duplicated")
    objective = REGISTERED_OBJECTIVE if registered_objective else None
    if any(dataset.objective != objective for dataset in datasets):
        raise ValueError("fitting cannot pool registered and historical reward objectives")
    regional_rows = tuple(
        load_red_regional_choice_example(store, item, objective=objective)
        for item in regional_choices
    )
    curriculum = tuple(row for dataset in datasets for row in dataset.curriculum_examples)
    prior_measured: list[RedDevelopmentMeasuredChoiceInput] = []
    if isinstance(prior, RedPlayerModelRecord):
        corpus_rec = store.find_sealed_record(
            f"rp-corpus-{prior.corpus_sha256}", expected_kind="red_player_training_corpus"
        )
        if corpus_rec is not None:
            corpus_data = corpus_rec.read()
            measured_list = corpus_data.get("measured_choices", [])
            if isinstance(measured_list, list):
                for raw_item in measured_list:
                    item_dict = cast(Mapping[str, object], raw_item)
                    cid = cast(str, item_dict["choice_id"])
                    if cid not in {m.choice_id for m in measured_choices}:
                        b_sha = cast(str, item_dict["behavior_model_sha256"])
                        b_rec: LivingDexGoalModelRecord | RedPlayerModelRecord
                        if prior.model.model_sha256 == b_sha:
                            b_rec = prior
                        else:
                            m_rec = store.find_sealed_record(
                                f"rpr-model-{b_sha}", expected_kind="red_player_model"
                            )
                            if m_rec is None:
                                m_rec = store.find_sealed_record(
                                    f"rp-model-{b_sha}", expected_kind="red_player_model"
                                )
                            if m_rec is not None:
                                b_rec = load_player_goal_model_record_bytes(
                                    m_rec.read_bytes(), expected_model_sha256=b_sha
                                )
                            else:
                                raise ValueError(
                                    f"cannot resolve prior measured choice behavior model {b_sha}"
                                )
                        prior_measured.append(
                            RedDevelopmentMeasuredChoiceInput(
                                cid, cast(str, item_dict["record_sha256"]), b_rec
                            )
                        )
    all_measured_choices = (*prior_measured, *measured_choices)
    measured_rows = tuple(
        load_red_development_measured_choice_example(store, item, objective=objective)
        for item in all_measured_choices
    )
    if any(row.partition != "train" for row in measured_rows):
        raise ValueError("measured choices must be training-only")
    rows = (
        *base,
        *(row for dataset in datasets for row in dataset.examples),
        *regional_rows,
        *measured_rows,
    )
    hashes = tuple(
        sorted(
            [canonical_sha256(row.public_dict()) for row in rows]
            + [canonical_sha256(row.public_dict()) for row in curriculum]
        )
    )
    if isinstance(prior, RedPlayerModelRecord) and (not registered_objective or prior_registered):
        if not set(prior.retained_example_sha256).issubset(hashes):
            raise ValueError("native training would discard or rewrite prior rows")
    elif not registered_objective and (
        living_dex_option_train_dataset_sha256(base) != prior.model.train_dataset_sha256
    ):
        raise ValueError("historical corpus does not match the starting model")
    settled_count = sum(row.outcome.target_vector is not None for row in rows) + sum(
        row.outcome.target_vector is not None for row in curriculum
    )
    previous_count = (
        prior.model.settled_examples if not registered_objective or prior_registered else 0
    )
    if settled_count <= previous_count:
        raise ValueError("native training has no additional settled experience")
    if registered_objective and settled_count < 2:
        raise ValueError("registered fitting needs two settled choices before publication")
    corpus = {
        "schema": (
            "pokemon.red.registered-player-corpus.v1"
            if registered_objective
            else "pokemon.red.native-player-corpus.v1"
        ),
        **(
            {"objective": objective, "historical_rewards_reused": False}
            if registered_objective
            else {}
        ),
        "examples": [
            row.public_dict() for row in sorted(rows, key=lambda row: row.decision_sha256)
        ],
        "episodes": [
            {
                "episode_id": item.episode_id,
                "manifest_sha256": item.manifest_sha256,
                "plan_sha256": item.plan.plan_sha256,
                "behavior_model_sha256": item.behavior_record.model.model_sha256,
            }
            for item in episodes
        ],
        "prior_model_sha256": prior.model.model_sha256,
        "prior_record_sha256": prior.file_sha256,
        "independent_evaluation": False,
    }
    corpus_sha = canonical_sha256(corpus)
    if curriculum:
        corpus["curriculum_examples"] = [row.public_dict() for row in curriculum]
        corpus["curriculum_contract"] = "forced-singleton-story-outcome-unit-weight-v1"
        corpus_sha = canonical_sha256(corpus)
    if regional_choices:
        corpus["regional_choices"] = [
            {
                "episode_id": item.episode_id,
                "choice_record_sha256": item.choice_record_sha256,
                "outcome_record_sha256": item.outcome_record_sha256,
                "behavior_model_sha256": item.behavior_record.model.model_sha256,
            }
            for item in regional_choices
        ]
        corpus_sha = canonical_sha256(corpus)
    if all_measured_choices:
        corpus["measured_choices"] = [
            {
                "choice_id": item.choice_id,
                "record_sha256": item.record_sha256,
                "behavior_model_sha256": item.behavior_record.model.model_sha256,
            }
            for item in all_measured_choices
        ]
        corpus_sha = canonical_sha256(corpus)
    corpus_record = store.publish_sealed_record(
        f"rp-corpus-{corpus_sha}", kind="red_player_training_corpus", record=corpus
    )
    feature_version = max(
        prior.model.feature_version,
        *(row.menu.feature_version for row in rows),
        *(row.feature_version for row in curriculum),
    )
    fit = fit_living_dex_option_value(
        rows, feature_version=feature_version, curriculum_examples=curriculum
    )
    baseline_model = (
        upgrade_option_value_model_for_economy(prior.model)
        if feature_version == 4
        else upgrade_option_value_model_for_optional_recovery(prior.model)
        if feature_version == 3
        else upgrade_option_value_model_for_search_history(prior.model)
        if feature_version == 2
        else prior.model
    )
    prior_error = evaluate_living_dex_option_value(
        baseline_model, rows, expected_partition="train", curriculum_examples=curriculum
    )
    updated_error = evaluate_living_dex_option_value(
        fit.model, rows, expected_partition="train", curriculum_examples=curriculum
    )
    document = {
        "schema": REGISTERED_PLAYER_MODEL_SCHEMA if registered_objective else PLAYER_MODEL_SCHEMA,
        **({"objective": objective} if registered_objective else {}),
        "authority": "bounded_development_only",
        "model": fit.model.to_dict(),
        "model_sha256": fit.model.model_sha256,
        "source_commit": source_commit,
        "source_bundle_sha256": source_bundle_sha256,
        "corpus_sha256": corpus_sha,
        "prior_model_sha256": prior.model.model_sha256,
        "retained_example_sha256": list(hashes),
    }
    record = store.publish_sealed_record(
        f"{'rpr-model' if registered_objective else 'rp-model'}-{fit.model.model_sha256}",
        kind="red_player_model",
        record=document,
    )
    loaded = load_player_goal_model_record_bytes(
        record.read_bytes(), expected_model_sha256=fit.model.model_sha256
    )
    if loaded.model.train_dataset_sha256 != fit.model.train_dataset_sha256:
        raise ValueError("native player model round trip differs")
    return {
        "schema": (
            "pokemon.red.registered-player-fit-result.v1"
            if registered_objective
            else "pokemon.red.native-player-fit-result.v1"
        ),
        "model": loaded.public_dict(),
        "corpus_record_sha256": corpus_record.summary.record_sha256,
        "fit_report": fit.report.public_dict(),
        "prior_train_error": prior_error.public_dict(),
        "updated_train_error": updated_error.public_dict(),
        "in_sample_only": True,
        "new_settled_examples": fit.model.settled_examples - previous_count,
        "prior_rows_retained": not registered_objective or prior_registered,
        **(
            {
                "historical_rewards_reused": False,
                "parameter_warm_start": False,
                "prior_model_role": "behavior_and_in_sample_comparison_only",
            }
            if registered_objective
            else {}
        ),
        "controller_actions": 0,
        "authority_promotions": 0,
        **(
            {
                "curriculum_outcomes": len(curriculum),
                "comparative_choice_outcomes": len(rows),
                "curriculum_is_comparative_evidence": False,
            }
            if curriculum
            else {}
        ),
        **({"regional_source_examples": len(regional_rows)} if regional_choices else {}),
        **({"measured_source_examples": len(measured_rows)} if all_measured_choices else {}),
    }


def bootstrap_red_player_search_history(
    store: PrivateArtifactRoot,
    *,
    prior: RedPlayerModelRecord,
    source_commit: str,
    source_bundle_sha256: str,
) -> dict[str, object]:
    """Publish an authenticated zero-history-weight initialization, not a fit.

    Preserve every existing example byte/target and the original corpus record.
    This enables prospective collection, not improved history-aware judgment.
    """
    return _bootstrap_red_player_features(
        store,
        prior=prior,
        source_commit=source_commit,
        source_bundle_sha256=source_bundle_sha256,
        optional_recovery=False,
    )


def bootstrap_red_player_optional_recovery(
    store: PrivateArtifactRoot,
    *,
    prior: RedPlayerModelRecord,
    source_commit: str,
    source_bundle_sha256: str,
) -> dict[str, object]:
    """Authenticate and preserve the corpus before initializing optional recovery."""
    return _bootstrap_red_player_features(
        store,
        prior=prior,
        source_commit=source_commit,
        source_bundle_sha256=source_bundle_sha256,
        optional_recovery=True,
    )


def _bootstrap_red_player_features(
    store: PrivateArtifactRoot,
    *,
    prior: RedPlayerModelRecord,
    source_commit: str,
    source_bundle_sha256: str,
    optional_recovery: bool,
    economy: bool = False,
) -> dict[str, object]:
    from .registered_collection import REGISTERED_OBJECTIVE

    allowed_versions = (3,) if economy else (1, 2) if optional_recovery else (1,)
    if (
        not isinstance(prior, RedPlayerModelRecord)
        or prior.model.feature_version not in allowed_versions
    ):
        raise ValueError("bootstrap requires a legacy native player record")
    if economy and prior.objective != REGISTERED_OBJECTIVE:
        raise ValueError("economy bootstrap requires the registered objective")
    if (
        re.fullmatch(r"[0-9a-f]{40}", source_commit) is None
        or re.fullmatch(r"[0-9a-f]{64}", source_bundle_sha256) is None
    ):
        raise ValueError("history bootstrap source identity differs")
    corpus_record = store.find_sealed_record(
        f"rp-corpus-{prior.corpus_sha256}", expected_kind="red_player_training_corpus"
    )
    if corpus_record is None:
        raise ValueError("history bootstrap corpus missing")
    corpus = corpus_record.read()
    if canonical_sha256(corpus) != prior.corpus_sha256:
        raise ValueError("history bootstrap corpus identity differs")
    examples = corpus.get("examples")
    if not isinstance(examples, list) or any(not isinstance(row, Mapping) for row in examples):
        raise ValueError("history bootstrap corpus examples differ")
    rows = tuple(
        restore_living_dex_observed_arm_example(cast(Mapping[str, object], row)) for row in examples
    )
    hashes = tuple(sorted(canonical_sha256(row.public_dict()) for row in rows))
    if (
        hashes != tuple(sorted(prior.retained_example_sha256))
        or (living_dex_option_train_dataset_sha256(rows) != prior.model.train_dataset_sha256)
        or any(row.menu.feature_version > prior.model.feature_version for row in rows)
    ):
        raise ValueError("history bootstrap corpus differs from retained model")
    model = (
        upgrade_option_value_model_for_economy(prior.model)
        if economy
        else upgrade_option_value_model_for_optional_recovery(prior.model)
        if optional_recovery
        else upgrade_option_value_model_for_search_history(prior.model)
    )
    document = {
        "schema": REGISTERED_PLAYER_MODEL_SCHEMA if economy else PLAYER_MODEL_SCHEMA,
        "authority": "bounded_development_only",
        "model": model.to_dict(),
        "model_sha256": model.model_sha256,
        "source_commit": source_commit,
        "source_bundle_sha256": source_bundle_sha256,
        "corpus_sha256": prior.corpus_sha256,
        "prior_model_sha256": prior.model.model_sha256,
        "retained_example_sha256": list(hashes),
        **({"objective": REGISTERED_OBJECTIVE} if economy else {}),
    }
    record = store.publish_sealed_record(
        f"{'rpr' if economy else 'rp'}-model-{model.model_sha256}",
        kind="red_player_model", record=document
    )
    loaded = load_player_goal_model_record_bytes(
        record.read_bytes(), expected_model_sha256=model.model_sha256
    )
    report = {
        "schema": "pokemon.red.search-history-bootstrap.v1",
        "model": loaded.public_dict(),
        "initialization": "retained-head-with-zero-history-coefficients",
        "retained_examples": len(rows),
        "unknown_history_examples": len(rows),
        "new_examples": 0,
        "fits": 0,
        "controller_actions": 0,
        "history_effect_learned": False,
        "authority_promotions": 0,
    }
    if economy:
        report.update({
            "schema": "pokemon.red.economy-bootstrap.v1",
            "initialization": "retained-head-with-zero-economy-coefficients",
            "economy_effect_learned": False,
        })
        del report["unknown_history_examples"]
        del report["history_effect_learned"]
    elif optional_recovery:
        report.update(
            {
                "schema": "pokemon.red.optional-recovery-bootstrap.v1",
                "initialization": "retained-head-with-zero-recovery-coefficients",
                "recovery_effect_learned": False,
            }
        )
        del report["unknown_history_examples"]
        del report["history_effect_learned"]
    return report


def bootstrap_red_player_economy(
    store: PrivateArtifactRoot, *, prior: RedPlayerModelRecord,
    source_commit: str, source_bundle_sha256: str,
) -> dict[str, object]:
    """Preserve registered history while enabling prospective cash observations.

    The six new inputs have zero weights and the economy head is absent. This
    creates no new examples or learned income effect; it is not model fitting.
    """
    return _bootstrap_red_player_features(
        store, prior=prior, source_commit=source_commit,
        source_bundle_sha256=source_bundle_sha256, optional_recovery=False, economy=True,
    )
