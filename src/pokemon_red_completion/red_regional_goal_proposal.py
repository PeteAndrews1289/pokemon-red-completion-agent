"""Unfitted regional proposals below the native resource-aware goal policy.

A proposal does not force acquisition. Only a played acquisition may contribute
source-search effort; resupply/recovery contributes no source attempt or target.
"""

from __future__ import annotations

import json
from collections.abc import Mapping

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.private_artifacts import PrivateArtifactRoot
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_goal_context_profile import (
    RedGoalContextProfile,
    parse_red_goal_context_profile,
)
from pokemon_red_completion.red_player_checkpoint import CHECKPOINT_KIND, checkpoint_record_id

REGIONAL_PROPOSAL_SCHEMA = "pokemon.red.regional-goal-proposal.v1"
REGIONAL_PROPOSAL_KIND = "red_regional_goal_proposal"


def regional_proposal_record_id(episode_id: str) -> str:
    return "rgp-" + canonical_sha256({"episode_id": episode_id, "schema": REGIONAL_PROPOSAL_SCHEMA})


def regional_proposal_seed(training_seed: int) -> int:
    """Separate proposal randomness from the native parent-goal sampling stream."""
    if type(training_seed) is not int or training_seed < 0:
        raise ValueError("regional proposal needs a nonnegative training seed")
    return int(
        canonical_sha256(
            {
                "schema": REGIONAL_PROPOSAL_SCHEMA,
                "stream": "source_proposal",
                "training_seed": training_seed,
            }
        ),
        16,
    )


def load_regional_proposal_profile(
    store: PrivateArtifactRoot,
    episode_id: str,
    expected_record_sha256: str,
    *,
    expected_parent_plan: Mapping[str, object],
) -> RedGoalContextProfile:
    """Load the exact pre-input profile sealed into a regional goal proposal.

    Native support choices can finish under a dynamically retargeted profile
    even when no regional source was selected.  A later continuation must
    authenticate that executed profile rather than reconstruct it from a newer
    collection state.
    """
    record = store.find_sealed_record(
        regional_proposal_record_id(episode_id),
        expected_kind=REGIONAL_PROPOSAL_KIND,
    )
    if record is None or record.summary.record_sha256 != expected_record_sha256:
        raise ValueError("regional proposal record is absent or changed")
    document = record.read()
    if not isinstance(document, Mapping):
        raise ValueError("regional proposal profile binding differs")
    parent_plan = document.get("parent_plan")
    if (
        document.get("schema") != REGIONAL_PROPOSAL_SCHEMA
        or document.get("episode_id") != episode_id
        or document.get("source_proposal_fitted") is not False
        or document.get("controller_input_before_commit") is not False
        or document.get("parent_overridden") is not False
        or document.get("independent_evaluation") is not False
        or not isinstance(parent_plan, dict)
        or parent_plan != expected_parent_plan
        or parent_plan.get("profile_sha256") != document.get("profile_sha256")
        or not isinstance(document.get("profile"), dict)
    ):
        raise ValueError("regional proposal profile binding differs")
    try:
        payload = (
            json.dumps(
                document["profile"],
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
                allow_nan=False,
            )
            + "\n"
        ).encode("ascii")
        profile = parse_red_goal_context_profile(payload)
    except (KeyError, TypeError, UnicodeError, ValueError) as error:
        raise ValueError("regional proposal profile differs") from error
    if profile.profile_sha256 != document["profile_sha256"]:
        raise ValueError("regional proposal profile differs")
    return profile


def regional_proposal_source_effort(
    store: PrivateArtifactRoot,
    episode_id: str,
    checkpoint_sha256: str,
) -> tuple[str, str, bool, int, int] | None:
    """Recover effort from an authenticated proposal only if capture actually ran."""
    proposal = store.find_sealed_record(
        regional_proposal_record_id(episode_id),
        expected_kind=REGIONAL_PROPOSAL_KIND,
    )
    if proposal is None:
        return None
    terminal = store.find_sealed_record(
        checkpoint_record_id(episode_id),
        expected_kind=CHECKPOINT_KIND,
    )
    if terminal is None or terminal.summary.record_sha256 != checkpoint_sha256:
        raise ValueError("regional proposal lacks its declared terminal")
    document, checkpoint = proposal.read(), terminal.read()
    episode = store.open_episode(episode_id)
    metadata = episode.read_header()["metadata"]
    if not isinstance(metadata, dict):
        raise ValueError("regional proposal header metadata differs")
    if (
        document.get("schema") != REGIONAL_PROPOSAL_SCHEMA
        or document.get("episode_id") != episode_id
        or document.get("source_proposal_fitted") is not False
        or document.get("controller_input_before_commit") is not False
        or metadata.get("regional_proposal_record_sha256") != proposal.summary.record_sha256
        or checkpoint.get("trajectory_manifest_sha256") != episode.manifest_sha256
        or checkpoint.get("profile_sha256") != document.get("profile_sha256")
        or metadata.get("player_training_plan") != document.get("parent_plan")
    ):
        raise ValueError("regional proposal terminal/header binding differs")
    result = checkpoint.get("terminal_result")
    steps = result.get("steps") if isinstance(result, dict) else None
    if (
        not isinstance(steps, list)
        or len(steps) != 1
        or not isinstance(steps[0], dict)
        or steps[0].get("status") not in {"succeeded", "failed"}
    ):
        raise ValueError("regional proposal parent did not settle one goal")
    step = steps[0]
    if step["selected_kind"] != "acquire_species":
        return None
    source = document.get("selected_source")
    if source is None and document.get("source_mode") == "no_source":
        # Acquisition families such as fossils can occupy the native
        # acquire_species slot without selecting or attempting a wild source.
        return None
    if not isinstance(source, str) or not source.startswith("wild:"):
        raise ValueError("regional proposal lacks its capture source")
    profile = parse_red_goal_context_profile(
        (
            json.dumps(
                document.get("profile"),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
                allow_nan=False,
            )
            + "\n"
        ).encode("ascii")
    )
    captures = [spec for spec in profile.providers if spec.kind is GoalKind.ACQUIRE_SPECIES]
    if (
        profile.profile_sha256 != document["profile_sha256"]
        or len(captures) != 1
        or captures[0].parameters.get("source_id") != source
    ):
        raise ValueError("regional proposal source/profile differs")
    before = step.get("collection_before")
    objective = (
        before.get("required_registrations_sha256", before.get("required_specimens_sha256"))
        if isinstance(before, dict)
        else None
    )
    actions, frames = step.get("actions_executed"), step.get("frames_executed")
    if (
        not isinstance(objective, str)
        or len(objective) != 64
        or any(character not in "0123456789abcdef" for character in objective)
        or type(actions) is not int
        or actions < 0
        or type(frames) is not int
        or frames < 0
    ):
        raise ValueError("regional proposal source effort differs")
    return (
        source,
        objective,
        step.get("failure_reason") == "search_exhausted",
        actions,
        frames,
    )
