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
The target-binding layer now has canonical shadow and isolated causal Hall-of-Fame completion. The
first two six-role compositions exposed and repaired S.S. Anne typed-recovery and Route 11
live-capability mismatches. Their fresh replay qualified both repairs and reached a Lorelei win,
where a missing typed HP-floor intent produced the next fail-closed result.
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
deployment authority remains false.

Fresh seed 990006 did not reach the model test. It progressed through checkpoint 275 and 1,500
zero-faint balanced-team wins, ending with four members at level 55 and two at 54. The old finite
1,250-trip recovery budget expired before Bruno or Agatha emitted switch-target rows. Its 3,118
partial labels are excluded from training and evaluation, the seed is retired, and the frozen
candidate remained untested. Commit `edfa676` retained the 90% retreat and zero-faint contracts while
setting a measured 2,000-trip ceiling.

Fresh seed 990007 crossed that failure point, completed the curriculum, defeated Agatha, and
produced a task-complete prefix containing 17 switch targets. The exact frozen model scored 17/17
with 0.07965 cross-entropy versus 12/17 for the deterministic resolver, including Bruno 2/2,
Agatha 7/7, and all three Golbat targets. It was evaluated once without refitting. The route stopped
at 306/312 because its terminal receipt reconstructed five role changes from move turns even though
seven correct specialist switches executed around opponent changes. Commit `a5e92f0` records each
live switch and validates its target directly.

The missing runtime seam is now implemented and ROM-free verified. A write-once publisher rebuilds
the exact frozen model from the original authenticated lineages and refuses any digest other than
`bd1ba4…`. Its loader authenticates the manifest, exact stream roster, canonical JSONL, feature
schema, model payload, disjoint development lineages, and separate perfect prospective test. The
live policy records target agreement and confidence in shadow, then supports an explicitly
uncounted isolated trial where the teacher decides *when* to switch and the learned head alone binds
the living reserve. This is causal-trial authority, not deployment authority. The exact `bd1ba4…`
payload is now published under a complete write-once manifest and has passed an independent loader
round trip; see the [sanitized receipt](evidence/battle-switch-target-runtime-artifact-2026-08-09.json).
Canonical shadow seed `990009` completed all 36 objectives with 13/13 agreement, 95.66% mean
confidence, and no unavailable target. Fresh causal seed `990010` completed the identical
45,819,749-frame route through Hall of Fame while the target model rebound all 13 switch requests
with zero fallback. The [runtime qualification](evidence/battle-switch-target-canonical-runtime-qualification-2026-08-09.json)
therefore qualifies isolated target binding, while keeping ordinary moves and switch timing
teacher-gated.

Fresh uncounted seed `990011` then ran all six learned roles together with teacher battle queries
forbidden. It reached the S.S. Anne rival with 158 battle decisions, seven executed learned HP
recoveries, two learned target bindings, and zero teacher fallback before failing closed. The
chapter matched the eighth complete learned recovery request, then incorrectly required its
teacher-only exception subclass. This was an executor ownership mismatch, not a target-head miss.
The repair accepts only learned HP recovery for the executable lead and retains the existing exact
item, HP, menu, and reserve proofs; see the [preserved failure](evidence/portable-clean-start-six-role-rehearsal-01-failure-2026-08-09.json).

Seed `990012` qualified that S.S. Anne repair and advanced to the pre-Mart Route 11 supply Gambler.
After 169 teacher-free battle decisions, eight HP recoveries, two status recoveries, and two learned
target bindings, it failed because every Lavender intent advertised all recovery effects even when
the local HP allowance was zero and only protected final status-item copies existed. The executor
correctly refused the item; authorization had received a false capability mask. The repair
recomputes capabilities from live surplus and remaining allowance before every dispatch. See the
[second preserved failure](evidence/portable-clean-start-six-role-rehearsal-02-failure-2026-08-09.json).

Seed `990013` advanced through Lorelei with no battle-teacher query: 3,265 battle decisions, 13/13
learned target rebindings, 64,337 training-control choices, and 125,800 trainee/venue choices. The
chapter still rejected its win because the learned controller attacked at 59 HP beneath the
existing 70-HP per-turn contract. This exposed two missing evaluator inputs rather than a route
failure: the executable intent did not publish the HP floor, and the controller selected first and
masked unavailable action classes afterward. The repair adds a typed positive HP floor, ranks the
model over only live executable affordances, records masked top classes separately, and upgrades
the final clean-start contract to require positive authority from all requested roles. See the
[third preserved failure](evidence/portable-clean-start-six-role-rehearsal-03-failure-2026-08-09.json).

The audit also found and repaired three foundations that would have invalidated later transfer and
living-Pokédex claims. The Red target omitted Pinsir, the Blue target omitted Scyther, and the shared
gap calculation intersected Blue with itself. One canonical Generation I facts module now derives
the reciprocal eleven-species tables. Campaigns require explicit compatible trade links rather than
inventing trade ability from two concurrent saves. Encounter-condition labels now filter both
teacher selection and exact live trainee/venue binding, preventing a future Crystal day table from
silently acting at night.

## Capability scorecard

| Capability | Rating | Evidence and boundary |
| --- | ---: | --- |
| Deterministic Red teacher/referee | 9/10 | Repeated clean-power 312/312, 36/36, Hall-of-Fame runs with strict chapter contracts. This is an expert oracle, not learned autonomy. |
| Experiment integrity | 9/10 | Source/model/root hashes, whole-lineage splits, private artifact boundaries, preserved failures, one-attempt accounting, and 0/10 counted roots consumed. |
| Learned battle moves | 7/10 | A nonlinear ranker has prior live completion evidence, but the current reserve-controller causal lane keeps ordinary moves teacher-gated. The combined teacher-free stack remains unqualified. |
| Learned high-level battle control | 8/10 | Strong held-out class balance, 17/17 fresh offline targets, 13/13 canonical shadow, and 13/13 causal target bindings through Hall of Fame; the combined teacher-free stack still needs a terminal replay. |
| Learned objective selection | 6/10 | Clean start selects registered composite goals from semantic state, but most candidate sets are singleton and fixed authored skills perform the mechanics. |
| Learned trainee/venue strategy | 7/10 | The identity-free candidate ranker beat its shape baseline and completed a clean-power curriculum with real disagreements. It remains Red-only evidence. |
| Navigation and menu autonomy | 3/10 | Reusable local planning exists, but the completion path is still dominated by authored chapter routes and menu executors. |
| Multi-seed reliability | 3/10 | Perturbed demonstrations exist, but the official frozen 8-of-10 learned-stack campaign remains 0/10. |
| Cross-title transfer | 2/10 | A bounded Crystal benchmark is designed; no Crystal adapter, dataset, or result exists yet. |
| Living Pokédex / level 100 | 2/10 | Target and planning foundations exist; generic collection execution still contains explicit unimplemented adapter operations. |

## Code and test health

- 127 source modules and 135 test modules cover roughly 88,000 source lines and 52,500 test lines.
- The current full gate passes **2,156 tests** with 3 emulator-integration tests deselected and 1
  expected failure, plus
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
3. the listwise target head has completed canonical shadow and isolated causal Hall-of-Fame gates,
   but does not yet have combined or perturbation authority;
4. typed constraints and deterministic or authenticated learned target resolvers turn choices into
   executable
   affordances;
5. authored chapter and menu skills still carry out most long-horizon mechanics; and
6. an independent referee verifies progress and rejects behavior that wins without satisfying the
   declared lesson.

This is a credible hybrid agent architecture. It becomes misleading only if the authored skills or
teacher-gated move layer are described as learned. Public material should say exactly which model
owned each decision and which deterministic component executed it.

## Dependency-ordered next steps

1. Complete the full ROM-free gate for the HP-intent, legal-action-mask, and clean-start report-v2
   repair; commit and push the regenerated source identity.
2. Run a fresh uncounted canonical six-role replay with teacher battle queries disabled; preserve
   either its Hall-of-Fame receipt or its next fail-closed integration defect.
3. If it passes, freeze the exact combined artifact set. Typed intent enforcement and live
   affordance masking are now separate from true safety fallback in the report.
4. Run at least one uncounted timing perturbation with the same frozen source and artifacts. Only
   after canonical and perturbation gates pass should v95's ten one-attempt roots open.
5. Build Crystal as a thin adapter plus three bounded tasks: one reserve-choice battle, one local
   navigation round trip, and one trainee/venue decision. Compare the frozen Red model zero-shot,
   few-shot, and from scratch before writing a complete Crystal teacher.
6. If transfer is measurable, expand the adapter and route graph. If it is not, use the failure to
   revise the semantic schema before adding more Red-specific logic.

## Portfolio narrative

The strongest story is not “an AI beat Pokémon.” It is: **a completion script became an
authenticated teacher, then a sequence of learned controllers repeatedly fooled weak metrics until
causal, role-aware evaluators exposed what they had not learned.** The engineering contribution is
the system that makes those distinctions measurable: semantic interfaces, whole-lineage evaluation,
artifact authentication, typed authority boundaries, and preserved negative results. Crystal is
the falsification test that will determine whether those abstractions are actually portable.
