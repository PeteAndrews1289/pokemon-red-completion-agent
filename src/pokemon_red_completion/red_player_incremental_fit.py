"""Extend the recorded training inventory instead of hand-assembling each fit.

All admission, retained-row and outcome checks remain in the existing fitter.
This module only reconstructs its typed inputs from the prior authenticated
corpus and newly executed native goals or a regional choice. No emulator or new policy.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping

from pokemon_red_completion.living_dex_goal_model_record import LivingDexGoalModelRecord
from pokemon_red_completion.private_artifacts import PrivateArtifactRoot
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_player_model import RedPlayerModelRecord
from pokemon_red_completion.red_player_training_dataset import load_red_player_training_episode
from pokemon_red_completion.red_player_training_fit import (
    RedPlayerEpisodeInput,
    fit_red_player_update,
)
from pokemon_red_completion.red_player_training_plan import RedPlayerTrainingPlan
from pokemon_red_completion.red_regional_choice_learning import RedRegionalChoiceInput

BehaviorRecord = LivingDexGoalModelRecord | RedPlayerModelRecord
BehaviorResolver = Callable[[str], BehaviorRecord]


def _mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError("incremental inventory row must be a mapping")
    return value


def _text(row: Mapping[str, object], key: str) -> str:
    value = row[key]
    if not isinstance(value, str) or not value:
        raise ValueError("incremental inventory identifier differs")
    return value


def load_prior_player_inventory(
    store: PrivateArtifactRoot, prior: RedPlayerModelRecord, resolve: BehaviorResolver,
) -> tuple[tuple[RedPlayerEpisodeInput, ...], tuple[RedRegionalChoiceInput, ...]]:
    """Read only the prior's explicit episode/model inventory; never scan roots."""
    record = store.find_sealed_record(
        f"rp-corpus-{prior.corpus_sha256}", expected_kind="red_player_training_corpus",
    )
    if record is None:
        raise ValueError("prior player corpus is missing")
    corpus = record.read()
    if (
        canonical_sha256(corpus) != prior.corpus_sha256
        or corpus.get("schema") != "pokemon.red.native-player-corpus.v1"
        or corpus.get("independent_evaluation") is not False
    ):
        raise ValueError("prior player corpus binding differs")

    def behavior(row: Mapping[str, object]) -> BehaviorRecord:
        expected = _text(row, "behavior_model_sha256")
        model = resolve(expected)
        if model.model.model_sha256 != expected:
            raise ValueError("resolved behavior model differs from recorded choice")
        return model

    native = corpus.get("episodes")
    regional = corpus.get("regional_choices", [])
    if not isinstance(native, list) or not isinstance(regional, list) or not native:
        raise ValueError("prior player episode inventory differs")
    episodes = []
    for item in native:
        row = _mapping(item)
        episode_id = _text(row, "episode_id")
        reader = store.open_episode(episode_id)
        if reader.manifest_sha256 != row.get("manifest_sha256"):
            raise ValueError("prior episode manifest differs")
        metadata = _mapping(reader.read_header()["metadata"])
        plan = RedPlayerTrainingPlan(_mapping(metadata["player_training_plan"]))
        if plan.plan_sha256 != row.get("plan_sha256"):
            raise ValueError("prior episode plan differs")
        episodes.append(RedPlayerEpisodeInput(
            plan, episode_id, reader.manifest_sha256, behavior(row),
        ))
    choices = []
    for item in regional:
        row = _mapping(item)
        choices.append(RedRegionalChoiceInput(
            _text(row, "episode_id"), _text(row, "choice_record_sha256"),
            _text(row, "outcome_record_sha256"), behavior(row),
        ))
    if (
        len({item.episode_id for item in episodes}) != len(episodes)
        or len({item.episode_id for item in choices}) != len(choices)
    ):
        raise ValueError("prior player inventory repeats an episode")
    return tuple(episodes), tuple(choices)


def fit_incremental_regional_result(
    store: PrivateArtifactRoot, *, prior: RedPlayerModelRecord,
    result: Mapping[str, object], resolve: BehaviorResolver,
    source_commit: str, source_bundle_sha256: str,
) -> dict[str, object]:
    """One real destination choice adds one row; its forced parent adds none."""
    if (
        result.get("schema") != "pokemon.red.regional-acquisition-result.v1"
        or result.get("model_sha256") != prior.model.model_sha256
        or type(result.get("eligible_examples")) is not int
        or result.get("eligible_examples") != 1
        or type(result.get("parent_learning_examples")) is not int
        or result.get("parent_learning_examples") != 0
        or result.get("independent_evaluation") is not False
    ):
        raise ValueError("incremental source result scope differs")
    episodes, choices = load_prior_player_inventory(store, prior, resolve)
    episode_id = _text(result, "episode_id")
    prior_ids = {item.episode_id for item in episodes} | {item.episode_id for item in choices}
    if episode_id in prior_ids:
        raise ValueError("incremental source outcome was already included")
    reader = store.open_episode(episode_id)
    if reader.manifest_sha256 != result.get("manifest_sha256"):
        raise ValueError("incremental source episode identity differs")
    metadata = _mapping(reader.read_header()["metadata"])
    plan = RedPlayerTrainingPlan(_mapping(metadata["player_training_plan"]))
    episode = RedPlayerEpisodeInput(plan, episode_id, reader.manifest_sha256, prior)
    choice = RedRegionalChoiceInput(
        episode_id, _text(result, "choice_record_sha256"),
        _text(result, "outcome_record_sha256"), prior,
    )
    fitted = fit_red_player_update(
        store, prior=prior, episodes=(*episodes, episode), regional_choices=(*choices, choice),
        source_commit=source_commit, source_bundle_sha256=source_bundle_sha256,
    )
    if (
        fitted.get("new_settled_examples") != 1 or fitted.get("prior_rows_retained") is not True
        or _mapping(fitted["model"]).get("settled_examples") != prior.model.settled_examples + 1
    ):
        raise ValueError("incremental fitter returned an unexpected inventory")
    return fitted


def fit_incremental_goal_results(
    store: PrivateArtifactRoot, *, prior: RedPlayerModelRecord,
    results: tuple[Mapping[str, object], ...], resolve: BehaviorResolver,
    source_commit: str, source_bundle_sha256: str,
) -> dict[str, object]:
    """Retain native goals and intervening support; never credit source proposals.

    Zero-row support is authenticated but cannot trigger a fit on its own. The
    caller retains those results and includes them with the next learned goal.
    All supplied new episodes must have used the unchanged prior model.
    """
    if not results:
        raise ValueError("incremental goals require completed episode results")
    episodes, choices = load_prior_player_inventory(store, prior, resolve)
    seen = {item.episode_id for item in episodes} | {item.episode_id for item in choices}
    added = []
    expected_rows = 0
    for result in results:
        if (
            result.get("schema") != "pokemon.red.regional-goal-step-result.v1"
            or result.get("model_sha256") != prior.model.model_sha256
            or type(result.get("eligible_examples")) is not int
            or result["eligible_examples"] not in (0, 1)
            or type(result.get("eligible_source_examples")) is not int
            or result.get("eligible_source_examples") != 0
            or result.get("source_proposal_fitted") is not False
            or result.get("parent_overridden") is not False
            or result.get("model_fitted") is not False
            or result.get("independent_evaluation") is not False
        ):
            raise ValueError("incremental native result scope differs")
        episode_id = _text(result, "episode_id")
        if episode_id in seen:
            raise ValueError("incremental native outcome was already included")
        seen.add(episode_id)
        reader = store.open_episode(episode_id)
        if reader.manifest_sha256 != result.get("manifest_sha256"):
            raise ValueError("incremental native episode identity differs")
        metadata = _mapping(reader.read_header()["metadata"])
        if metadata.get("regional_choice_record_sha256") is not None:
            raise ValueError("regional source authority cannot be relabelled as a native goal")
        plan = RedPlayerTrainingPlan(_mapping(metadata["player_training_plan"]))
        dataset = load_red_player_training_episode(
            store, episode_id=episode_id, expected_manifest_sha256=reader.manifest_sha256,
            plan=plan, behavior_model=prior.model,
        )
        if len(dataset.examples) != result["eligible_examples"]:
            raise ValueError("incremental native eligible count differs from recorded decisions")
        expected_rows += len(dataset.examples)
        added.append(RedPlayerEpisodeInput(plan, episode_id, reader.manifest_sha256, prior))
    if not expected_rows:
        return {
            "status": "support_retained_without_fit", "model_fitted": False,
            "model_sha256": prior.model.model_sha256, "new_settled_examples": 0,
            "pending_support_episodes": [item.episode_id for item in added],
        }
    fitted = fit_red_player_update(
        store, prior=prior, episodes=(*episodes, *added), regional_choices=choices,
        source_commit=source_commit, source_bundle_sha256=source_bundle_sha256,
    )
    if (
        fitted.get("new_settled_examples") != expected_rows
        or fitted.get("prior_rows_retained") is not True
        or _mapping(fitted["model"]).get("settled_examples")
        != prior.model.settled_examples + expected_rows
    ):
        raise ValueError("incremental native fitter returned an unexpected inventory")
    return fitted
