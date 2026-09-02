from __future__ import annotations

from pokemon_red_completion.repeatable_battle_curriculum import (
    build_repeatable_red_battle_curriculum,
    fit_repeatable_battle_curriculum,
)


def test_repeatable_curriculum_is_deterministic_and_partitioned() -> None:
    first = build_repeatable_red_battle_curriculum(
        training_examples=12,
        development_examples=6,
        seed=1289,
    )
    second = build_repeatable_red_battle_curriculum(
        training_examples=12,
        development_examples=6,
        seed=1289,
    )

    assert first.sha256 == second.sha256
    assert first.training == second.training
    assert first.development == second.development
    assert not (
        {item.semantic_state_sha256 for item in first.training}
        & {item.semantic_state_sha256 for item in first.development}
    )
    assert first.public_dict()["authentic_outcomes"] == 0


def test_repeatable_fit_learns_held_out_mechanics_preferences() -> None:
    curriculum = build_repeatable_red_battle_curriculum(
        training_examples=160,
        development_examples=80,
        seed=7,
    )

    model, report = fit_repeatable_battle_curriculum(
        curriculum,
        seed=7,
        hidden_units=16,
        epochs=80,
        learning_rate=0.02,
    )

    assert model.feature_names == curriculum.training[0].features.feature_names
    assert report.training_accuracy >= 0.85
    assert report.development_accuracy >= 0.75
    assert report.development_accuracy > report.zero_weight_development_accuracy
    assert report.public_dict()["gameplay_authority"] is False


def test_red_catalog_exposes_complete_canonical_inventories() -> None:
    from pokemon_red_completion.red_battle_catalog import PokemonRedBattleCatalog

    catalog = PokemonRedBattleCatalog()
    assert len(catalog.move_ids) == catalog.move_count == 165
    assert len(catalog.species_ids) == catalog.species_count == 151
    assert catalog.move_ids == tuple(sorted(catalog.move_ids))
    assert catalog.species_ids == tuple(sorted(catalog.species_ids))
