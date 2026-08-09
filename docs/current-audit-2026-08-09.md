# Current capability audit — 2026-08-09

## Executive verdict

This is now a strong autonomous-systems research portfolio, but it is not yet an end-to-end learned
Pokémon player. Its best assets are the clean-power expert, semantic observation boundary,
authenticated experiment lineage, fail-closed evaluators, and the willingness to reject runs that
win without demonstrating the intended lesson. Its largest remaining gap is authority: navigation,
menus, route mechanics, and ordinary move selection in the newest causal battle experiment still
depend on authored skills or teacher gating.

The present Red milestone is narrower and measurable: qualify the reserve-aware high-level battle
controller on a fresh full-game rollout, then combine it with teacher-free ordinary move selection.
The counted v95 clean-start campaign remains deliberately unopened at **0/10**. No cross-title or
living-Pokédex result is claimed.

## What changed since the August 8 audit

Three complete feature-v3 teacher lineages now exist. The newest timing/RNG lineage completed
**312/312 checkpoints**, **36/36 objectives**, Champion, and Hall of Fame. It recorded **3,322**
high-level battle labels—3,268 moves, 24 recoveries, 13 boosts, and 17 explicitly targeted switches—
while developing the party through **1,800 battles** to 60/55/55/55/55/55 with zero faints. Agatha's
observed opponent order required seven semantic role switches, and the teacher performed exactly
seven. See the [third-lineage receipt](evidence/battle-control-reserve-matchup-v3-lineage-03-2026-08-09.json).

A replacement controller was fitted on two whole rollout lineages and evaluated on the untouched
third split. Its held-out score is **98.2394% accuracy** and **94.7537% balanced accuracy**, up from
98.0154% and 90.3798% for the previous candidate. The improvement is concentrated where it matters:
rare recovery, boost, and switch classes. Switch-target accuracy is still only 10/13 on validation,
so class accuracy must not be read as complete role understanding. See the
[candidate receipt](evidence/battle-control-reserve-matchup-v3-lineage-candidate-02-2026-08-09.json).

Fresh causal execution then found five policy/interface gaps that ordinary offline accuracy hid:

1. At Rock Tunnel, the controller switched before the declared lead demonstrated its required role.
2. At Lorelei, it attacked while paralyzed because the first status mask covered only one dispatch
   path.
3. At Agatha, a recovery action accidentally satisfied a previous-action-only switch-residency
   check, letting the controller switch away without attacking; the maximum boost budget also did
   not express the required setup before the first attack.
4. The next Agatha replay used both specialists on every assigned target and spent the setup item,
   but made four switches for three observed role transitions. Its one statused Dugtrio attack was
   followed by one Blastoise attack, exposing that Agatha had recovery capability without declaring
   the already-supported status-clear-before-move intent.
5. After that declaration, Agatha passed setup, status safety, real residency, and exactly three
   observed-role switches together. It still failed role coverage because the model chose the
   high-level switch action while a hand-written matchup scorer bound Golbat to Blastoise instead
   of Jolteon.

Each run was rejected and preserved. The repairs add no species, map, or opponent identity. They
express game-neutral plan semantics: an initial move lesson, status clearance before attacking, a
real move between voluntary switches, and a typed bounded setup boost before the first move. The
first Agatha failure is the [attempt 11 receipt](evidence/battle-control-reserve-matchup-v3-causal-11-failure-2026-08-09.json),
the specialist-covering but extra-switch follow-up is preserved as
[attempt 12](evidence/battle-control-reserve-matchup-v3-causal-12-failure-2026-08-09.json),
and the clean target-binding failure is
[attempt 13](evidence/battle-control-reserve-matchup-v3-causal-13-failure-2026-08-09.json).

Attempt 13 changes the architecture rather than the heuristic weights. A new candidate-relative,
permutation-equivariant switch-target head scores every living reserve independently. On two whole
training lineages it fits 28/28 explicit targets; on the untouched third lineage it scores 11/13
(84.6%), improving the existing deterministic resolver's 10/13 (76.9%). It uses no party-slot,
species, move, opponent, map, or objective identity as input. The result is useful but insufficient:
it still chooses Blastoise for the held-out Agatha Golbat target. The
[offline receipt](evidence/battle-switch-target-offline-candidate-2026-08-09.json) therefore records
`deployment_authority: false`, and no new full-game replay is authorized from that model.

The first post-audit data attempt used fresh uncounted timing seed 990003. It reached checkpoint
275, including a distinct six-throw Snorlax capture, then failed closed when Route 11 Drowzee
reapplied sleep three times during team training. Its 469 partial labels are excluded. The repair
threads a venue's bounded battle timing into the generic trainer and applies the existing tested
four-reapplication allowance only to Route 11; the global default remains two.

Fresh seed 990004 then qualified that repair in live execution: it completed balanced development
at 51/52/52/55/51/51, defeated Blaine, and reached checkpoint 284. A required Viridian trainer
legally inflicted poison while the teacher still used the exact required move, survived, and
defeated the exact required party. The receipt had incorrectly treated zero status on every turn as
a controlled policy choice. The 3,123 partial labels remain excluded. The repair accepts observed
opponent status in that local receipt, records it publicly, and retains the immediate Center gate
requiring full HP, clear status, and restored PP before Giovanni. Seed 990004 is retired; the next
emulator qualification must use fresh seed 990005.

Seed 990005 then completed **312/312 checkpoints**, **36/36 objectives**, Champion, and Hall of Fame
from clean power. Its authenticated artifact contains 3,166 labels and 13 explicit switch targets;
the team completed 1,808 development battles and reached 60/55/55/55/55/55. The first frozen target
head scored 11/13 on this lineage, beating the deterministic resolver's 9/13 but repeating one
Bruno miss and the Agatha Golbat miss. After that result was recorded, the lineage was explicitly
opened for development rather than relabeled as an untouched test.

The second target candidate gives each battle plan equal total loss weight so a seven-switch timing
trace cannot dominate a two-switch trace, and reduces L2 from 0.03 to 0.003. With no identity added
to model inputs, the selected two-unit model scores 54/54 across the four opened
leave-one-whole-lineage-out folds, fits 41/41 development targets, and scores 13/13 on the existing
whole-lineage validation set. Because those settings were selected after opening all four lineages,
deployment authority remains false. Fresh seed 990006 is the one-time unopened test.

## Capability scorecard

| Capability | Rating | Evidence and boundary |
| --- | ---: | --- |
| Deterministic Red teacher/referee | 9/10 | Repeated clean-power 312/312, 36/36, Hall-of-Fame runs with strict chapter contracts. This is an expert oracle, not learned autonomy. |
| Experiment integrity | 9/10 | Source/model/root hashes, whole-lineage splits, private artifact boundaries, preserved failures, one-attempt accounting, and 0/10 counted roots consumed. |
| Learned battle moves | 7/10 | A nonlinear ranker has prior live completion evidence, but the current reserve-controller causal lane keeps ordinary moves teacher-gated. The combined teacher-free stack remains unqualified. |
| Learned high-level battle control | 7/10 | Strong held-out class balance, causal progress through Agatha, and 54/54 target accuracy across opened whole-lineage folds; seed 990006 and runtime target authority remain. |
| Learned objective selection | 6/10 | Clean start selects registered composite goals from semantic state, but most candidate sets are singleton and fixed authored skills perform the mechanics. |
| Learned trainee/venue strategy | 7/10 | The identity-free candidate ranker beat its shape baseline and completed a clean-power curriculum with real disagreements. It remains Red-only evidence. |
| Navigation and menu autonomy | 3/10 | Reusable local planning exists, but the completion path is still dominated by authored chapter routes and menu executors. |
| Multi-seed reliability | 3/10 | Perturbed demonstrations exist, but the official frozen 8-of-10 learned-stack campaign remains 0/10. |
| Cross-title transfer | 2/10 | A bounded Crystal benchmark is designed; no Crystal adapter, dataset, or result exists yet. |
| Living Pokédex / level 100 | 2/10 | Target and planning foundations exist; generic collection execution still contains explicit unimplemented adapter operations. |

## Code and test health

- 122 source modules and 131 test modules cover roughly 87,000 source lines and 51,000 test lines.
- The current full gate passes **2,110 tests** with 3 emulator-integration tests deselected, plus
  Ruff, source mypy, public-artifact scanning, documentation links, and collection-registry
  regeneration.
- The repository is evidence-rich but too large for its current capability surface. Route chapters,
  receipts, historical protocol versions, and long narratives make orientation expensive.
- Forty-four legacy source modules remain under mypy `ignore_errors` overrides. The register is
  documented and must only shrink, but a green top-level mypy result therefore does not mean the
  entire source tree is strictly typed.
- `collection_chapter.py` still raises `NotImplementedError` for generic encounter seeking,
  capture, flee, and PC navigation. Those are honest markers of the gap between a Red completion
  teacher and a portable living-Pokédex player.

## Architecture boundary that must stay explicit

The current stack is layered rather than monolithic:

1. semantic observers convert revision-specific emulator state into portable facts;
2. learned rankers choose objectives, trainees/venues, moves, or high-level battle action classes;
3. the new offline listwise head can learn a party target, but it has no runtime authority yet;
4. typed constraints and deterministic target resolvers turn deployed choices into executable
   affordances;
5. authored chapter and menu skills still carry out most long-horizon mechanics; and
6. an independent referee verifies progress and rejects behavior that wins without satisfying the
   declared lesson.

This is a credible hybrid agent architecture. It becomes misleading only if the authored skills or
teacher-gated move layer are described as learned. Public material should say exactly which model
owned each decision and which deterministic component executed it.

## Dependency-ordered next steps

1. Collect additional complete, timing/RNG-varied teacher lineages with explicit switch targets,
   especially at Bruno and Agatha. Preserve whole lineages as train, validation, and unopened test;
   test party-order permutations offline and do not use counted v95 roots for development data.
2. Refit the switch-target head and require improvement over the deterministic baseline, reserve
   permutation equivariance, counterfactual matchup sensitivity, and the held-out Golbat target
   before granting runtime authority.
3. Rerun the fresh power-on reserve-controller gate only after the target head qualifies. Preserve
   either its Hall-of-Fame receipt or its next causal rejection.
4. If it passes, separate typed intent enforcement from true model safety fallbacks in the strict
   report, then run the combined stack with teacher queries disabled for ordinary move selection.
5. Run at least one uncounted timing perturbation with the same frozen source and artifacts. Only
   after canonical and perturbation gates pass should v95's ten one-attempt roots open.
6. Build Crystal as a thin adapter plus three bounded tasks: one reserve-choice battle, one local
   navigation round trip, and one trainee/venue decision. Compare the frozen Red model zero-shot,
   few-shot, and from scratch before writing a complete Crystal teacher.
7. If transfer is measurable, expand the adapter and route graph. If it is not, use the failure to
   revise the semantic schema before adding more Red-specific logic.

## Portfolio narrative

The strongest story is not “an AI beat Pokémon.” It is: **a completion script became an
authenticated teacher, then a sequence of learned controllers repeatedly fooled weak metrics until
causal, role-aware evaluators exposed what they had not learned.** The engineering contribution is
the system that makes those distinctions measurable: semantic interfaces, whole-lineage evaluation,
artifact authentication, typed authority boundaries, and preserved negative results. Crystal is
the falsification test that will determine whether those abstractions are actually portable.
