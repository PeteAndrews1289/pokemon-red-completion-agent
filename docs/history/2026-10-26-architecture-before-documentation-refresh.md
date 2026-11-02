> Historical snapshot, archived October 26, 2026. Not current instructions.
> Follow [the current handoff](../../HANDOFF.md) and latest user direction.

# Architecture and current integration boundaries

This is a hierarchical player, not an end-to-end visual network or an LLM choosing
buttons. Small learned models select semantic goals and battle actions. Explicit
game-control skills execute those actions and verify their consequences.

## Runtime and learning

Observe state → offer executable goals → model selects → skill executes →
verify outcome → retain the actual continuation.

Learning is a separate admitted TRAIN-and-fit process. Running the frozen player
does not automatically update weights. Native XP improves its Pokémon, not its
decision model. The model receives semantic cartridge/emulator information rather
than pixels alone.

| Component | Existing responsibility | Current limitation |
| --- | --- | --- |
| Goal model | Rank real story, collection, preparation and resource alternatives | Stored151 has useful healing learning but thin capture/readiness/resource coverage and clipping |
| Consequence head | Learn scoped responses to defeat and preparation | 36-row head overprepared during Silph reuse and was rolled back |
| Battlers | Learned moves, attack/switch control and replacements | Exact scopes and model identities matter; no general mastery claim |
| Cartridge skills | Navigation, HMs, menus, capture, evolution, storage and recovery | Execution support, not learned strategy |
| Continuous player | Counted actions, fresh menus, typed outcomes and configured continuation | Stable launcher still depends on explicit private legacy assembly |
| Party and stock guards | Preserve actual identities, loans and resources | Loan return and separate in-party reserve/nurse tests pass; combined boxed-loan hard interruption remains open |
| Registry and records | Separate shared credit, local flags, physical stock and costs | Different saves and diagnostic wins must never be merged |

## What the latest player actually does

The current earned DEVELOPMENT continuation verifies124 native registrations,
36 story objectives and same-ancestry concurrent Champion/Hall-of-Fame proof.
Its two recent collection blocks add91 entries (87 during model goals/four support)
with434 receipts and unchanged151 weights. All original individuals are restored,
all four legendary specimens retained, and protected main141/32 is unchanged.
Normal earning, buying, capture, evolution and physical consuming dependencies
are connected; adaptive source repairs and operator resumptions still prevent
final frozen-autonomy acceptance.

The stable configuration retains the exact failed evolution exclusion, individual
guard and settlement callback. A fresh process rebuilds five alternatives without
input and selects Victory Road. The actual failed-loan copy returns through normal
PC inputs without stock/XP loss; diagnostic progress never transfers into play.

The older completed story/124-registration lineage remains proof of broad
mechanical coverage with substantial supplied strategy. Do not combine its
ownership counts with the newer lineage or call either a final fresh evaluation.

## Current composition debt

The public continuous loop now has a repository-owned configured launcher. Its
private legacy assembly remains explicit. The audited Silph driver's static closure
reaches 168 private helper modules; the central inventory file is 1,836 lines.
Those are static dependency observations, not executed-module counts.

The stable interface carries the current goal-model pin, composition flags, exact
capability exclusions, loan identity and authenticated cumulative-cost continuation.
Existing scoped actors remain in the private assembly. It is not a self-contained
export. Rewriting every old helper is not required before the next gameplay test.

The safe evolution stop checks actual remaining action/frame/time headroom; inner
nursing is counted once by the native session. A production in-party copy preserves
24 battles,one nurse and earned XP,then reloads its typed partial result. Arbitrary
hard stops inside battle/PC macros and the combined interrupted boxed-loan case
remain unqualified; the known failed profile stays quarantined.
Do not replace the existing storage system or weaken identity checks.

## Model boundaries

The historical Model141 V4-to-V7 upgrade appended319 rows with2,871 zero coefficients.
Readiness contributes 252 rows, challenge/opponent state 54 and preparation 13.
Older coarse party-risk and resource features remain active. Exposing a feature
is not learning how to use it. The subsequent151 fit learns scoped PP/healing
interactions, not broad mastery. Its151 rows have weighted design rank37; the
latest audit finds out-of-classroom joint readiness and frequent clipped scores.

Use existing models where they work. A demonstrated preparation failure should
lead to informative TRAIN contrasts, including when to stop training, through
the existing learner. DEVELOPMENT outcomes must not be relabeled as fit data.
The battle classroom and existing trained battlers remain reusable.

## Code map

| Concern | Starting points in the Python package |
| --- | --- |
| Continuous loop and menus | red_native_player.py, red_player_story_menu.py, red_live_option_menu.py |
| Goal model | living_dex_option_value.py, red_player_model.py |
| Consequence decisions | red_consequence_choice.py, player_option_preparation.py |
| Party and continuations | red_player_party_guard.py, red_player_continuation.py |
| Configured resume and loan return | red_player_configuration.py, red_player_party_loan.py; scripts/run_configured_red_player.py |
| Boxed evolution | red_native_boxed_evolution.py, red_player_collection_options.py |
| Trainer and story battle bridge | red_learned_trainer.py, red_story_battle.py |
| Battle practice and fitting | red_trainer_practice_episode.py, red_trainer_practice_fit.py |
| Native story skills | red_player_gym.py, red_player_silph.py, red_player_story_travel.py |
| Capture and registration | red_routed_static_capture.py, registered_collection.py, registration_memory.py |

[Current audit and work order](../work-sessions/2026-10-09-earned-collection-completion-and-audit.md) ·
[Setup](../getting-started.md) · [Remaining delivery work](../model-first-roadmap.md) ·
[Historical architecture](architecture-through-2026-09-10.md)
