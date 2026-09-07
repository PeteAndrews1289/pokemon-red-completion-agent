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
    upgrade_option_value_model_for_search_history,
)
from pokemon_red_completion.private_artifacts import PrivateArtifactRoot
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_player_model import (
    PLAYER_MODEL_SCHEMA,
    RedPlayerModelRecord,
    load_player_goal_model_record_bytes,
)
from pokemon_red_completion.red_player_training_dataset import load_red_player_training_episode
from pokemon_red_completion.red_player_training_plan import RedPlayerTrainingPlan


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
) -> dict[str, object]:
    """Retain all prior rows; add only validated, executed sampled choices.

    Callers supply the full native episode history, not a success-selected subset.
    The prior checkpoint's row fingerprints prevent forgetting or rewriting old
    examples. Repeated known roots remain correlated training, not evaluation.
    """
    if not episodes or len({item.episode_id for item in episodes}) != len(episodes):
        raise ValueError("native training episode inventory differs")
    if (
        re.fullmatch(r"[0-9a-f]{40}", source_commit) is None
        or re.fullmatch(r"[0-9a-f]{64}", source_bundle_sha256) is None
    ):
        raise ValueError("native fitting source identity differs")
    base = tuple(item.example for item in load_living_dex_authenticated_causal_examples(store))
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
    rows = (*base, *(row for dataset in datasets for row in dataset.examples))
    hashes = tuple(sorted(canonical_sha256(row.public_dict()) for row in rows))
    if isinstance(prior, RedPlayerModelRecord):
        if not set(prior.retained_example_sha256).issubset(hashes):
            raise ValueError("native training would discard or rewrite prior rows")
    elif living_dex_option_train_dataset_sha256(base) != prior.model.train_dataset_sha256:
        raise ValueError("historical corpus does not match the starting model")
    if sum(row.outcome.target_vector is not None for row in rows) <= prior.model.settled_examples:
        raise ValueError("native training has no additional settled experience")
    corpus = {
        "schema": "pokemon.red.native-player-corpus.v1",
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
    corpus_record = store.publish_sealed_record(
        f"rp-corpus-{corpus_sha}", kind="red_player_training_corpus", record=corpus
    )
    feature_version = max(prior.model.feature_version, *(row.menu.feature_version for row in rows))
    fit = fit_living_dex_option_value(rows, feature_version=feature_version)
    baseline_model = (
        upgrade_option_value_model_for_search_history(prior.model)
        if feature_version == 2
        else prior.model
    )
    prior_error = evaluate_living_dex_option_value(baseline_model, rows, expected_partition="train")
    updated_error = evaluate_living_dex_option_value(fit.model, rows, expected_partition="train")
    document = {
        "schema": PLAYER_MODEL_SCHEMA,
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
        f"rp-model-{fit.model.model_sha256}", kind="red_player_model", record=document
    )
    loaded = load_player_goal_model_record_bytes(
        record.read_bytes(), expected_model_sha256=fit.model.model_sha256
    )
    if loaded.model.train_dataset_sha256 != fit.model.train_dataset_sha256:
        raise ValueError("native player model round trip differs")
    return {
        "schema": "pokemon.red.native-player-fit-result.v1",
        "model": loaded.public_dict(),
        "corpus_record_sha256": corpus_record.summary.record_sha256,
        "fit_report": fit.report.public_dict(),
        "prior_train_error": prior_error.public_dict(),
        "updated_train_error": updated_error.public_dict(),
        "in_sample_only": True,
        "new_settled_examples": fit.model.settled_examples - prior.model.settled_examples,
        "prior_rows_retained": True,
        "controller_actions": 0,
        "authority_promotions": 0,
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
    if not isinstance(prior, RedPlayerModelRecord) or prior.model.feature_version != 1:
        raise ValueError("history bootstrap requires a legacy native player record")
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
        or any(row.menu.feature_version != 1 for row in rows)
    ):
        raise ValueError("history bootstrap corpus differs from retained model")
    model = upgrade_option_value_model_for_search_history(prior.model)
    document = {
        "schema": PLAYER_MODEL_SCHEMA,
        "authority": "bounded_development_only",
        "model": model.to_dict(),
        "model_sha256": model.model_sha256,
        "source_commit": source_commit,
        "source_bundle_sha256": source_bundle_sha256,
        "corpus_sha256": prior.corpus_sha256,
        "prior_model_sha256": prior.model.model_sha256,
        "retained_example_sha256": list(hashes),
    }
    record = store.publish_sealed_record(
        f"rp-model-{model.model_sha256}", kind="red_player_model", record=document
    )
    loaded = load_player_goal_model_record_bytes(
        record.read_bytes(), expected_model_sha256=model.model_sha256
    )
    return {
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
