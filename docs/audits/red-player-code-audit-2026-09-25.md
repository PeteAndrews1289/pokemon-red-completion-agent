# Red player code audit — September 25, 2026

Baseline: `d8db5f80`. Pete designated this audit the current engineering source of
truth and authorized completing **steps 1 and 2 only**, then a stocktake. This
document remains subordinate to MISSION.md and NORTH_STAR.md. Later verified
results supersede findings explicitly; they do not rewrite this baseline.

## Product and evidence boundary

First deliver a fresh, model-directed Red story and 124 native-route registrations
in the same save. Then test a compatible unfamiliar hack; Crystal follows Red.
Keep the existing battler, goal learner, adapters, qualified mechanics and history.
Development story completion and separate collection copies are not that final run.
Primary collection is 109/124; a separate trade-development copy is 111/124.
Model141 retains 141 outcomes, 96 successes and 58 economy-qualified outcomes.
The audit added no learning, gameplay, registration, source claim or promotion.

## Findings

1. **High — disconnected player stacks.** `clean_start_player.py` uses older
   objective/battle interfaces. The current option learner and battler use bounded
   runners. `red_league_story_chain.py` binds a historical checkpoint chain, not any
   future fresh save. A unified declared stack remains necessary.
2. **High — recovery stops continuity.** `red_autonomous_player.py` stops for most
   recovery/safety boundaries. `red_integrated_play.py` admits continuous paid
   Safari/native-exchange mechanics only. General loss/heal/train/replan is open.
3. **High — reuse readiness, do not recreate it.** `post_battle_strategy.py` already
   has level-gap, HP/PP/status, aftermath and budget features with kind interactions,
   but its diagnostic scorer is separate from Model141 inference. Bridge existing
   semantic observations to a versioned actual policy projection and fitting path.
4. **High — missing player training connection.** The 137 ordinary fitted rows are
   55 acquisition, 34 resupply, 28 restore, 19 evolution and 1 exploration; four
   native acquisition rows bring 141. No fitted story/development rows occur in
   this high-level corpus (not a statement about the battler). V3 native lesson
   import/verification exists; live snapshot recording is not wired to a runner.
   Known source inventory does not establish independent whole-player evaluation.
5. **Medium — collection dependencies.** Game Corner quotes/coin observation exist,
   procurement/prize/storage execution does not. Jynx child-chain qualification
   precedes its composite-wrapper native trial. Finite-resource opportunity costs,
   including the single Master Ball, remain incomplete.
6. **Medium — verification debt.** Historical source contracts and several tests
   disagree with current behavior; the broad verification baseline is not green.

## Verification retained from the audit

- ROM-free broad run: 16,727 passed, 58 failed, 2 errors, 1 skipped, 1 expected
  failure; interrupted after 1,283.91 seconds with 15 collected cases unfinished.
  This is not a complete-suite pass.
- Rechecked 33 failures/errors with an explicit package import path: 28 passed,
  5 failed. The other 27 reported failures shared the historical Route 11
  `red.run-team-balancing` source-compatibility rejection.
- Five persistent mismatches: three fainted-Cut expectations, historical Vermilion
  timing, and the Cave source-drift expectation. Earlier session evidence already
  documented these families; do not silently rewrite historical receipts.
- Separate comparison-runner file: 81 passed, with and without explicit import
  path. An interim suspicion of test-order contamination was **not established**;
  the slow tail was Route 11 source attestation, not this runner.
- Typing: 35 errors in 8 files. Lint: 205 issues in 28 files. These counts are not
  counts of demonstrated runtime defects.
- Documentation/product-focus and collection-registry checks passed. Public-artifact
  scan: 87 false positives in 13 files, all embedded in `risk-` identifiers, not keys.
- No ROM integration was performed. The checkout remained clean. Broad automated
  checks plus critical-path inspection are not a manual proof of every source line.

## Ordered next work

1. Repair verification: current-source/historical evidence compatibility, stale
   expectations, reproducible local imports, typing/lint and artifact scanner.
   Preserve safety checks; review semantic drift rather than blessing new hashes.
2. Reuse readiness features and wire live native lessons through actual inference,
   recording, verification, fitting and reload. Preserve old model/schema behavior.
3. Assemble continuous story/preparation/recovery/resource execution.
4. Collect the bounded native TRAIN pilot, fit and compare once on eligible sources.
5. Qualify connected model-selected play with a retained setback and recovery.
6. Close collection dependencies and prepare the separately authorized fresh exam.

**Current goal stops after 1–2.** Steps 3–6 are context, not authorization for this
packet. No production fit, gameplay, campaign, external agent or publication.

## Mission check and acceptance for steps 1–2

- Capability: reusable state-grounded readiness and auditable live player lessons.
- Learned authority: engineering enables, but does not itself claim, learned
  story/development/recovery selection; Model141 stays frozen.
- Transfer test: ROM-free varied parties, levels, budgets and renamed private
  identities; shared inference/training vectors and reload. No cross-title claim.
- Cheapest falsifier: ready/unready story-versus-preparation contrasts must differ
  through the actual model projection; a fabricated success or stale boundary must
  fail lesson admission. Old frozen representations must remain unchanged.
- Time box: reassess each 90-minute slice; do not stop merely at a session boundary.
- Stop condition: step 1 and step 2 acceptance verified, or a material new source,
  architecture or authority issue requiring Pete's decision. Preserve partial work.

Step 1 requires a completed reproducible ROM-free suite and checks, or an explicitly
adjudicated historical-only lane with its original safety assertions still tested;
no unexplained baseline failures or newly suppressed typing modules.
Step 2 requires a callable live-boundary recorder connected to existing execution
interfaces, observed outcomes only, retained partial/failure evidence, versioned
readiness inputs, fit/serialization/reload tests and no legacy corpus reinterpretation.
Native qualification and model-quality claims remain future work, not fabricated
from synthetic tests.

## Resolution: steps 1–2

Completed under the [follow-through record](../work-sessions/2026-09-25-audit-steps-1-2.md).
The full ROM-free sweep completed with16904passes and2stale test expectations;
both were corrected,then327relevant tests passed. No executable source changed
after the full sweep. This is explicitly adjudicated combined verification,not a
single all-green full invocation. Lint,typing,docs,artifact and registry checks pass.

Existing post-battle readiness now reaches V5 actual option inference and fitting.
New live native lessons use the existing bindings,snapshot verifier,registered
fitter and model reloader. Old schemas,rows and models retain their meaning.
Source compatibility,partial failures and no-input verification remain guarded.

This resolves the requested engineering packet,not the missing production lessons,
independent evaluation or connected whole-player run. Findings1,2and5 remain next
work;findings3–4have software connections,but their native learning/qualification
deficits remain. Stop for Pete's stocktake before step3. Model141 and saves unchanged.

## Subsequent authorization: steps 3–4

Pete completed the stocktake and explicitly set the next goal to steps 3 and 4.
The [integration plan](../player-integration-steps-3-4.md) now governs that work.
Earlier stop-after-step-2 language describes the completed packet, not a continuing
prohibition. Original findings, evidence and unresolved native/source gates remain.
