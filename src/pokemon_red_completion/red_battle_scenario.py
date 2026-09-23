"""Pokémon Red adapter for one-turn, outcome-bearing battle scenarios."""

from __future__ import annotations

import math
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


def red_battle_move_is_model_supported(
    move_id: object,
    current_pp: object,
    *,
    catalog: PokemonRedBattleCatalog | None = None,
) -> bool:
    """Return the learner's title-adapter support rule for one Red move slot."""

    return red_battle_move_unsupported_reason(move_id, current_pp, catalog=catalog) is None


def red_battle_move_unsupported_reason(
    move_id: object, current_pp: object, *, catalog: PokemonRedBattleCatalog | None = None
) -> str | None:
    """Explain why one visible move cannot be an attack choice in this segment."""

    if type(move_id) is not int or move_id <= 0:  # noqa: E721
        return "invalid_move"
    if (
        isinstance(current_pp, bool)
        or not isinstance(current_pp, (int, float))
        or not math.isfinite(current_pp)
        or current_pp <= 0
    ):
        return "no_pp"
    resolved_catalog = catalog or PokemonRedBattleCatalog()
    mechanics = resolved_catalog.resolve_move(pokemon_red_move_ref(move_id))
    if mechanics.max_pp <= 0:
        return "no_pp_capacity"
    if "counter" in mechanics.effect_flags:
        return "counter_needs_prior_damage"
    if "self_destruct" in mechanics.effect_flags:
        return "self_destruct_outside_segment"
    if mechanics.power <= 0:
        return "status_or_non_damaging_outside_segment"
    return None


def red_battle_move_is_refreshable_model_supported(
    move_id: object,
    *,
    catalog: PokemonRedBattleCatalog | None = None,
) -> bool:
    """Return whether a full PP restoration can make this move a learner action.

    This deliberately ignores only *current* PP.  It does not broaden the
    learner surface: status moves and Selfdestruct remain unsupported, and the
    cartridge catalog must give the move a positive PP capacity.
    """

    return red_battle_move_unsupported_reason(move_id, 1, catalog=catalog) is None


def red_battle_supported_move_count(
    move_ids: tuple[int, ...],
    current_pp: tuple[int, ...],
) -> int:
    """Count exactly the move slots that can become learner candidates."""

    if (
        not isinstance(move_ids, tuple)
        or not isinstance(current_pp, tuple)
        or len(move_ids) != len(current_pp)
    ):
        raise RedBattleScenarioError("battle move arrays differ")
    catalog = PokemonRedBattleCatalog()
    return sum(
        red_battle_move_is_model_supported(move_id, pp, catalog=catalog)
        for move_id, pp in zip(move_ids, current_pp, strict=True)
    )


def red_battle_refreshable_supported_move_count(move_ids: tuple[int, ...]) -> int:
    """Count learner actions available after a genuine full PP restoration."""

    if not isinstance(move_ids, tuple):
        raise RedBattleScenarioError("battle move array is unavailable")
    catalog = PokemonRedBattleCatalog()
    return sum(
        red_battle_move_is_refreshable_model_supported(move_id, catalog=catalog)
        for move_id in move_ids
    )


@dataclass(frozen=True, slots=True)
class PreparedRedBattleScenario:
    """Policy-visible feature candidates plus their authenticated input digest."""

    initial_observation_sha256: str
    features: BattleFeatureBatch
    allow_no_attack: bool = False
    unsupported_candidate_reasons: tuple[str | None, ...] = ()

    def __post_init__(self) -> None:
        if not any(self.features.legal_mask) and not self.allow_no_attack:
            raise RedBattleScenarioError("battle scenario has no supported damaging candidate")
        if self.unsupported_candidate_reasons and (
            len(self.unsupported_candidate_reasons) != len(self.features.legal_mask)
            or any(
                legal and reason is not None
                for legal, reason in zip(
                    self.features.legal_mask, self.unsupported_candidate_reasons, strict=True
                )
            )
        ):
            raise RedBattleScenarioError("move support reasons differ from legal candidates")

    @property
    def supported_candidate_mask(self) -> tuple[bool, ...]:
        """The experiment mask is the model's exact legal-action mask."""

        return self.features.legal_mask


def prepare_red_battle_scenario(
    encoder: PokemonRedObservationEncoder,
    initial_state: RawGameState,
    *,
    allow_no_attack: bool = False,
    allow_stranded_accuracy_move: bool = False,
    allow_status_moves: bool = False,
) -> PreparedRedBattleScenario:
    """Project an active MAIN-menu state and admit observable attack moves only."""

    if type(allow_stranded_accuracy_move) is not bool or type(allow_status_moves) is not bool:
        raise ValueError("stranded accuracy move opt-in must be boolean")
    if not isinstance(initial_state, RawGameState) or initial_state.battle_state not in {1, 2}:
        raise RedBattleScenarioError("battle scenario requires an active wild or trainer battle")
    snapshot = encoder.snapshot_from_raw(initial_state)
    payload = snapshot.to_dict()
    catalog = PokemonRedBattleCatalog()
    projector = BattleFeatureProjector(catalog, mask_counter_without_prior_damage=True)
    projected = projector.project(payload)
    moves = initial_state.battler_moves
    if moves is None:
        raise RedBattleScenarioError("battle move identities do not match projected candidates")
    supported_values: list[bool] = []
    reasons: list[str | None] = []
    for slot_index, legal, pp in zip(
        projected.slot_indices,
        projected.legal_mask,
        projected.current_pp,
        strict=True,
    ):
        if slot_index >= len(moves) or moves[slot_index] == 0:
            raise RedBattleScenarioError("battle move identities do not match projected candidates")
        reason = red_battle_move_unsupported_reason(moves[slot_index], pp, catalog=catalog)
        if (
            allow_status_moves
            and reason == "status_or_non_damaging_outside_segment"
            and catalog.status_move_supported(pokemon_red_move_ref(moves[slot_index]))
        ):
            reason = None
        if reason is None and not legal:
            reason = "disabled_or_mechanically_illegal"
        reasons.append(reason)
        supported_values.append(reason is None)
    if (
        allow_stranded_accuracy_move
        and not any(supported_values)
        and initial_state.party_hp is not None
        and not any(
            hp > 0
            for i, hp in enumerate(initial_state.party_hp)
            if i != initial_state.active_party_index
        )
    ):
        # A disabled last attack is NOT necessarily cartridge Struggle. Admit
        # the visible legal Sand-Attack only in this explicit DEVELOPMENT seam.
        # The frozen head chooses the move; no teacher fallback or trained-status claim.
        for i, (slot, legal, pp) in enumerate(
            zip(projected.slot_indices, projected.legal_mask, projected.current_pp, strict=True)
        ):
            if moves[slot] == 28 and legal and pp > 0:
                supported_values[i] = True
                reasons[i] = None
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
        allow_no_attack=allow_no_attack,
        unsupported_candidate_reasons=tuple(reasons),
    )


def project_red_battle_turn_outcome(
    execution: BattleTurnExecution,
) -> BattleTurnOutcome:
    """Measure one turn from cartridge state without consulting the actor."""

    before = execution.initial_state
    after = execution.final_state
    if before.battle_state not in {1, 2}:
        raise RedBattleScenarioError("turn outcome requires a wild or trainer battle")
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
    final_player_hp = after.battler_hp
    if battle_exited and after.active_party_index is None:
        # Outside battle the observation adapter's battler convenience fields
        # describe the party leader, not necessarily the member that acted.
        # In particular, a living reserve can win while the leader is fainted.
        slot = before.active_party_index
        if slot is None or after.party_hp is None or not 0 <= slot < len(after.party_hp):
            raise RedBattleScenarioError("terminal outcome lacks the acting party member HP")
        final_player_hp = _required_hp(
            after.party_hp[slot], name="terminal acting member HP", positive=False
        )
    player_fainted = bool(
        (final_player_hp == 0)
        or (not battle_exited and player_changed and before.active_party_index is not None)
    )
    if player_fainted:
        player_damage = before_player_hp / before_player_max
    elif final_player_hp is None:
        raise RedBattleScenarioError("outcome lacks final player HP")
    else:
        player_damage = max(0, before_player_hp - final_player_hp) / before_player_max

    # This is an action-value outcome rather than causal damage attribution.
    # If a faster opponent faints from recoil or Selfdestruct before the
    # selected move spends PP, the terminal cartridge state is still the
    # consequence observed after choosing that candidate.
    opponent_fainted = after.enemy_hp == 0
    if before.battle_state == 2:
        after_roster_hp = after.enemy_party_hp or execution.terminal_enemy_roster_hp
        if (
            before.enemy_party_position is None
            or before.enemy_party_hp is None
            or not 0 <= before.enemy_party_position < len(before.enemy_party_hp)
            or after_roster_hp is None
            or before.enemy_party_position >= len(after_roster_hp)
        ):
            raise RedBattleScenarioError("trainer outcome lacks enemy roster evidence")
        opponent_fainted = after_roster_hp[before.enemy_party_position] == 0
    if opponent_fainted:
        opponent_damage = before_enemy_hp / before_enemy_max
    elif after.enemy_hp is None:
        raise RedBattleScenarioError("nonterminal outcome lacks final opponent HP")
    elif before.battle_state == 2 and after.enemy_party_position != before.enemy_party_position:
        assert after.enemy_party_hp is not None
        assert before.enemy_party_position is not None
        opponent_damage = (
            max(
                0,
                before_enemy_hp - after.enemy_party_hp[before.enemy_party_position],
            )
            / before_enemy_max
        )
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
