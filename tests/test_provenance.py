from __future__ import annotations

from pathlib import Path

import pytest

from pokemon_red_completion.provenance import (
    EvaluationIdentityError,
    SourceIdentity,
    build_evaluation_identity,
    canonical_sha256,
    file_sha256,
    require_clean_source,
)


def test_canonical_digest_is_independent_of_mapping_order() -> None:
    assert canonical_sha256({"b": 2, "a": 1}) == canonical_sha256({"a": 1, "b": 2})
    assert canonical_sha256({"a": [1, 2]}) != canonical_sha256({"a": [2, 1]})


def test_official_identity_requires_known_clean_source() -> None:
    with pytest.raises(EvaluationIdentityError, match="unavailable"):
        require_clean_source(SourceIdentity(None, None))
    with pytest.raises(EvaluationIdentityError, match="clean worktree"):
        require_clean_source(SourceIdentity("a" * 40, True))


def test_build_evaluation_identity_hashes_all_influencing_inputs(tmp_path: Path) -> None:
    model = tmp_path / "model.bin"
    model.write_bytes(b"weights")

    identity = build_evaluation_identity(
        source=SourceIdentity("a" * 40, False),
        rom_sha1="b" * 40,
        rom_sha256="c" * 64,
        objective_graph={"route": ["start", "hall-of-fame"]},
        configuration={"seed": 7},
        model_paths=(model,),
    )

    assert identity.source.git_commit == "a" * 40
    assert identity.model_sha256 == (file_sha256(model),)
    assert identity.public_dict()["source"]["worktree_dirty"] is False
    assert str(tmp_path) not in str(identity.public_dict())
