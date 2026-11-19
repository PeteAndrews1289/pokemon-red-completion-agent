"""Version only explicit training-faint recovery;legacy identity remains exact."""

import json
from dataclasses import replace

import pytest
from test_red_player_configuration import config

from pokemon_red_completion.red_player_configuration import (
    WILD_TRAIN_RECOVERY_SCHEMA,
    RedPlayerConfiguration,
)


@pytest.mark.parametrize("loan", [False, True])
@pytest.mark.parametrize("route", [False, True])
@pytest.mark.parametrize("quantum", [None, 2])
def test_explicit_recovery_roundtrip_preserves_all_prior_configuration(loan, route, quantum):
    base = replace(
        config(),
        loanable_specimen_refs=("reserve-individual",) if loan else (),
        quote_capture_route_work=route,
        preparation_encounter_quantum=quantum,
    )
    before = base.to_dict()
    assert "evolution_recover_wild_faints" not in before
    opted = replace(base, evolution_recover_wild_faints=True)
    doc = json.loads(json.dumps(opted.to_dict()))
    assert (
        doc["schema"] == WILD_TRAIN_RECOVERY_SCHEMA and doc["evolution_recover_wild_faints"] is True
    )
    assert RedPlayerConfiguration.from_dict(doc) == opted
    assert opted.sha256 != base.sha256
    assert replace(opted, evolution_recover_wild_faints=False).to_dict() == before


@pytest.mark.parametrize("value", [1, None, "yes"])
def test_recovery_rejects_coercion(value):
    with pytest.raises(ValueError):
        replace(config(), evolution_recover_wild_faints=value)


def test_legacy_schema_cannot_smuggle_new_recovery_flag():
    doc = config().to_dict()
    doc["evolution_recover_wild_faints"] = True
    with pytest.raises(ValueError):
        RedPlayerConfiguration.from_dict(doc)
