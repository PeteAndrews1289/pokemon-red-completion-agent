"""Deduplicate actually encountered opponents without assuming knockout order.

Retained battle logs may include the active opponent's semantic roster position.
That identity is used only to join repeated observations, never as a policy
feature or to fill unseen levels from a roster. Legacy sequential-only records
remain supported and conflicting evidence still refuses.
"""


def observed_opponent_position(decision):
    battle = decision["observation"]["features"]["battle"]
    count = battle.get("opponent_party_count")
    remaining = battle.get("opponent_remaining_count")
    if type(count) is not int or type(remaining) is not int or not 1 <= remaining <= count <= 6:
        raise ValueError("battle lacks observed opponent position")
    state = decision.get("state_before", {})
    if not isinstance(state, dict):
        raise ValueError("malformed observed battle state")
    if "opponent_party_position" in state:
        position = state["opponent_party_position"]
        if type(position) is not int or not 0 <= position < count:
            raise ValueError("invalid active opponent position")
        return position
    return count - remaining
