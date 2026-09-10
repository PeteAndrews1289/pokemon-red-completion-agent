"""Restore the already chosen failed destination without another policy query."""

from typing import Any

from .red_goal_context_profile import _canonical_line, parse_red_goal_context_profile
from .red_regional_choice_learning import REGIONAL_CHOICE_KIND, regional_choice_record_id


def committed_failed_source_profile(store: Any, episode_id: str) -> Any:
    episode = store.open_failed_episode(episode_id)
    metadata = episode.read_header()["metadata"]
    expected = metadata.get("regional_choice_record_sha256")
    if expected is None:
        return None
    record = store.find_sealed_record(
        regional_choice_record_id(episode_id),
        expected_kind=REGIONAL_CHOICE_KIND,
    )
    if record is None or record.summary.record_sha256 != expected:
        raise ValueError("failed regional choice binding differs")
    document = record.read()
    index = document["selection"]["selected_candidate_index"]
    candidates = document["candidates"]
    if (
        document.get("episode_id") != episode_id
        or type(index) is not int
        or not isinstance(candidates, list)
        or not 0 <= index < len(candidates)
    ):
        raise ValueError("failed regional choice selection differs")
    selected = candidates[index]
    profile = parse_red_goal_context_profile(_canonical_line(selected["profile"]))
    if not profile.profile_sha256 == selected["profile_sha256"] == metadata["profile_sha256"]:
        raise ValueError("failed regional choice profile differs")
    return profile
