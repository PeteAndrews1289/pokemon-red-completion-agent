"""Fresh starts carry the same explicitly declared training recovery setting."""

from copy import deepcopy

import pytest
from run_fresh_red_player import realized_configuration

from pokemon_red_completion.red_player_configuration import ASSEMBLY_FLAGS


@pytest.mark.parametrize("enabled", [None, False, True])
def test_fresh_start_preserves_training_recovery_declaration(enabled):
    template = dict(
        goal_model_sha256="a" * 64,
        assembly_flags=tuple((flag, False) for flag in ASSEMBLY_FLAGS),
        excluded_profiles=(),
        quote_capture_route_work=True,
    )
    if enabled is not None:
        template["evolution_recover_wild_faints"] = enabled
    before = deepcopy(template)
    config = realized_configuration(
        template, origin_sha256="b" * 64, origin_id="fresh-unit",
        starter_ref="observed-starter", teacher_profiles=(),
    )
    assert config.evolution_recover_wild_faints is (enabled is True)
    assert config.loanable_specimen_refs == ("observed-starter",)
    assert template == before


@pytest.mark.parametrize("invalid", [1, "true", None])
def test_fresh_start_cannot_coerce_a_recovery_flag(invalid):
    template = dict(
        goal_model_sha256="a" * 64,
        assembly_flags=tuple((flag, False) for flag in ASSEMBLY_FLAGS),
        excluded_profiles=(), quote_capture_route_work=True,
        evolution_recover_wild_faints=invalid,
    )
    with pytest.raises(ValueError, match="faint recovery"):
        realized_configuration(
            template, origin_sha256="b" * 64, origin_id="fresh-unit",
            starter_ref="observed-starter", teacher_profiles=(),
        )
