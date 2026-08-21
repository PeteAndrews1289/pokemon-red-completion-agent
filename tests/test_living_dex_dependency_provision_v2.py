from __future__ import annotations

from pokemon_red_completion.living_dex_dependency_evaluation_v2 import (
    require_fresh_development_opening_set_v2,
)
from pokemon_red_completion.living_dex_dependency_provision_v2 import (
    provision_v2_development_commitments,
)


def test_provision_v2_development_commitments() -> None:
    openings, roster = provision_v2_development_commitments()
    assert len(openings) == 4
    assert len(roster.rows) == 4

    # Must pass the strict validation
    require_fresh_development_opening_set_v2(openings)

    # Check that payloads match their commitments
    import hashlib

    for opening, row in zip(openings, roster.rows):
        assert opening.scenario_id == row.record_id
        payload_bytes = opening.canonical_private_bytes()
        assert hashlib.sha256(payload_bytes).hexdigest() == row.declared_record_sha256
        assert len(payload_bytes) == row.declared_total_bytes
