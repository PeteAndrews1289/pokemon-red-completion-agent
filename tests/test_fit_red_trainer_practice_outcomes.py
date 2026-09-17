from __future__ import annotations

from copy import deepcopy

import pytest

from scripts.fit_red_trainer_practice_outcomes import _validate_root_source_provenance


def _receipt(root: str, source: str) -> dict[str, object]:
    return {"root_lineage_id": root, "source_state_sha256": source}


def test_fit_corpus_requires_consistent_distinct_upstream_states() -> None:
    first = _receipt("root-a", "a" * 64)
    second = _receipt("root-b", "b" * 64)
    _validate_root_source_provenance([first, deepcopy(first), second])
    with pytest.raises(ValueError, match="relabeled"):
        _validate_root_source_provenance([first, _receipt("root-b", "a" * 64)])
    with pytest.raises(ValueError, match="multiple upstream"):
        _validate_root_source_provenance([first, _receipt("root-a", "b" * 64)])
    with pytest.raises(ValueError, match="missing"):
        _validate_root_source_provenance([first, _receipt("root-b", "not-a-hash")])
