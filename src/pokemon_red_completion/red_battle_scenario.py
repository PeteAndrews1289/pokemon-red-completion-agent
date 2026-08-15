"""Pokémon Red adapter for one-turn, outcome-bearing battle scenarios."""

from __future__ import annotations

from dataclasses import dataclass

from pokemon_red_completion.battle_outcome_learning import (
    BattleOutcomeLearningError,
    BattleTurnOutcome,
)
from pokemon_red_completion.battle_runtime import BattleTurnExecution
from pokemon_red_completion.battle_semantics import (
    BattleFeatureBatch,
    BattleFeatureProjector,
)
from pokemon_red_completion.observation import RawGameState
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_battle_catalog import (
    PokemonRedBattleCatalog,
    pokemon_red_move_ref,
)
from pokemon_red_completion.red_trajectory import PokemonRedObservationEncoder


class RedBattleScenarioError(ValueError):
    """Raised when a Red state cannot support the bounded outcome experiment."""


@dataclass(frozen=True, slots=True)
class PreparedRedBattleScenario:
    """Policy-visible feature candidates plus their authenticated input digest."""

    initial_observation_sha256: str
    features: BattleFeatureBatch

    def __post_init__(self) -> None:
        if not any(self.features.legal_mask):
            raise RedBattleScenarioError("battle scenario has no supported damaging candidate")

    @property
    def supported_candidate_mask(self) -> tuple[bool, ...]:
        """The experiment mask is the model's exact legal-action mask."""

        return self.features.legal_mask


def prepare_red_battle_scenario(
    encoder: PokemonRedObservationEncoder,
    initial_state: RawGameState,
) -> PreparedRedBattleScenario:
    """Project an active MAIN-menu state and admit observable attack moves only."""

    if not isinstance(initial_state, RawGameState) or initial_state.battle_state != 1:
        raise RedBattleScenarioError("the first outcome family requires an active wild battle")
    snapshot = encoder.snapshot_from_raw(initial_state)
    payload = snapshot.to_dict()
    catalog = PokemonRedBattleCatalog()
    projector = BattleFeatureProjector(catalog)
    projected = projector.project(payload)
    moves = initial_state.battler_moves
    if moves is None:
        raise RedBattleScenarioError("battle move identities do not match projected candidates")
    supported_values: list[bool] = []
    for slot_index, legal, pp in zip(
        projected.slot_indices,
        projected.legal_mask,
        projected.current_pp,
        strict=True,
    ):
        if slot_index >= len(moves) or moves[slot_index] == 0:
            raise RedBattleScenarioError(
                "battle move identities do not match projected candidates"
            )
        mechanics = catalog.resolve_move(pokemon_red_move_ref(moves[slot_index]))
        supported_values.append(
            legal
            and pp > 0
            and mechanics.power > 0
            and "self_destruct" not in mechanics.effect_flags
        )
    supported = tuple(supported_values)
    features = BattleFeatureBatch(
        feature_names=projected.feature_names,
        candidate_vectors=projected.candidate_vectors,
        legal_mask=supported,
        current_pp=projected.current_pp,
        slot_indices=projected.slot_indices,
        schema_id=projected.schema_id,
    )
    return PreparedRedBattleScenario(
        initial_observation_sha256=canonical_sha256(payload),
        features=features,
    )


def project_red_battle_turn_outcome(
    execution: BattleTurnExecution,
) -> BattleTurnOutcome:
    """Measure one turn from cartridge state without consulting the actor."""

    before = execution.initial_state
    after = execution.final_state
    if before.battle_state != 1:
        raise RedBattleScenarioError("the first outcome family requires a wild battle")
    if after.battle_state not in {0, before.battle_state}:
        raise RedBattleScenarioError("battle outcome changed to an unsupported battle kind")
    if before.map_id != after.map_id:
        raise RedBattleScenarioError("battle outcome crossed a map boundary")

    before_enemy_hp = _required_hp(before.enemy_hp, name="initial opponent HP", positive=True)
    before_enemy_max = _required_hp(
        before.enemy_max_hp,
        name="initial opponent maximum HP",
        positive=True,
    )
    before_player_hp = _required_hp(before.battler_hp, name="initial player HP", positive=True)
    before_player_max = _required_hp(
        before.battler_max_hp,
        name="initial player maximum HP",
        positive=True,
    )
    if before_enemy_hp > before_enemy_max or before_player_hp > before_player_max:
        raise RedBattleScenarioError("initial battle HP exceeds its maximum")

    move_executed = execution.move_executed

    battle_exited = after.battle_state == 0
    player_changed = after.active_party_index != before.active_party_index
    player_fainted = bool(
        (after.battler_hp == 0)
        or (
            not battle_exited
            and player_changed
            and before.active_party_index is not None
        )
    )
    if player_fainted:
        player_damage = before_player_hp / before_player_max
    elif after.battler_hp is None:
        raise RedBattleScenarioError("outcome lacks final player HP")
    else:
        player_damage = max(0, before_player_hp - after.battler_hp) / before_player_max

    # This is an action-value outcome rather than causal damage attribution.
    # If a faster opponent faints from recoil or Selfdestruct before the
    # selected move spends PP, the terminal cartridge state is still the
    # consequence observed after choosing that candidate.
    opponent_fainted = after.enemy_hp == 0
    if opponent_fainted:
        opponent_damage = before_enemy_hp / before_enemy_max
    elif after.enemy_hp is None:
        raise RedBattleScenarioError("nonterminal outcome lacks final opponent HP")
    else:
        opponent_damage = max(0, before_enemy_hp - after.enemy_hp) / before_enemy_max

    try:
        return BattleTurnOutcome(
            move_executed=move_executed,
            opponent_damage_fraction=min(float(opponent_damage), 1.0),
            player_damage_fraction=min(float(player_damage), 1.0),
            opponent_fainted=opponent_fainted,
            player_fainted=player_fainted,
            battle_exited=battle_exited,
            actions_executed=execution.actions_executed,
            frames_executed=execution.frames_executed,
            pre_attack_frames=execution.pre_attack_frames,
        )
    except BattleOutcomeLearningError as error:
        raise RedBattleScenarioError("Red turn outcome is internally inconsistent") from error


def _required_hp(value: int | None, *, name: str, positive: bool) -> int:
    if type(value) is not int or value < int(positive):  # noqa: E721
        raise RedBattleScenarioError(f"{name} is unavailable")
    return value
