# Recovery and training-readiness audit — 2026-09-06

## Decision

The project is recoverable through PR 228. Do not restart the old campaign or treat a green CI
result as permission to launch its successor. Repair the two identified execution/readiness seams
and connect campaign admission to the existing fitter before collecting the next lessons.

This audit is maintenance for the active bounded Red goal-learning experiment, not new learning.
It ran no cartridge, teacher, prediction, fit, development evaluation or controller input. Source
under review is `40c847c6f4b71e119cbea5cbe38fd009b30a1d00` (PR 228, including PR 227).

## Mission check

| Question | Answer |
| --- | --- |
| Reusable capability | Preserve a resumable causal training loop for semantic acquisition, party development, storage and resource decisions. |
| Learned authority | None changes in this audit. The named unblock is the next train-only Red option-value update, followed by bounded goal-selection evaluation. |
| Transfer test | Separate Red starting states first; four paired roots provide descriptive engineering evidence, not statistical superiority. Crystal remains deferred, with title-neutral observations/actions preserved. |
| Cheapest falsifier | Re-enter the production command with a root already reserved by this plan; feed the readiness projection a lesson whose actual action differs from its intended focus. |
| Time box | One audit/recovery session. The next repair gets at most four engineering hours before a written reassessment; no gameplay during the audit. |
| Stop condition | Stop publication/execution of a claimed-ready campaign while command recovery, factual-kind accounting or fit admission is unresolved. Preserve evidence; do not add another teacher run or protocol wrapper. |

## Recovered state

GitHub checked at approximately 02:08 UTC on September 6:

| Work | Verified state |
| --- | --- |
| PR 224 — repeatable capacity | Merged. |
| PR 225 — targeted campaign | Merged; executable campaign source `57a2479aea0b6668e834aecfdca156c9dff68b20`. |
| PR 226 — diagnostics/diversity | Merged; current remote main `27432fd9df29d549c9490026422a54f65fad773c`. |
| PR 227 — diverse successor freezer | Open; published/local head `cfac33ebe0966c0f643064b6fb89a9bfef722a4d`. |
| PR 228 — retired-bank train consumer | Open; published/local head `40c847c6f4b71e119cbea5cbe38fd009b30a1d00`; contains PR 227. |

PR 226's branch CI passed. Exact-main CI and the current PR 227/228 checks were still running at
the audit's initial check; their status must be refreshed before any later merge. Neither pending
PR has been represented here as merged or execution-ready.

All 76 registered worktrees were inspected for changes after creating the audit worktree. The only
pre-existing untracked item was an older reviewer patch; it was archived without modification.
No tracked local changes or unavailable worktree directories were reported. An all-refs Git bundle
was created and verified as complete history, including detached worktree heads. The active private
goal-learning store, account-wide root-claim registry and reviewer patch were separately archived.
The private recovery index records exact locations and archive hashes. A second hash-verified
copy of the roughly 24 MB archives is on the internal disk, separate from the external data drive.
This protects against an unavailable external drive as well as accidental edits; it is not an
off-site backup. Public code also remains on GitHub; private data does not.

The production readers authenticated **23 causal train examples**, including the five additional
settled examples from the latest targeted campaign. They also authenticated all **10** targeted
setup terminals: **5 complete, 5 failed**. The existing immutable model record is intact, has
**18 settled training examples**, and hashes to
`cbff99900be566347a1ce3d6ccbe0d0c935eb5c6a9a3f961accdbc96c9442a56`.
The extra five examples have **not** been fitted. Settled negative outcomes remain valid lessons;
setup censors are retained in the campaign denominator, not invented as supervised targets.

The cumulative active-state counter of 111 belongs to the existing evidence-backed multi-family
scorecard. It is not the size of this option model's corpus. This audit leaves learning counters
unchanged rather than adding five without the scorecard's explicit admission/evidence update.

## Findings that change the next steps

### P1 — the new command prevents its core runner from recovering

In `scripts/run_red_living_dex_targeted_bank_retirement_train.py`, `_observe_retired_roots` first
requires `private.root_available`, then requires both root claims to be unused. Its `needed` set
still includes every scheduled root. The core runner deliberately reserves a shared root before
executing the first reset, and supports reopening its own terminal or continuing never-claimed
trials. On command re-entry, those legitimate reservations are rejected before the core recovery
path is reached. A terminal campaign cannot simply be reopened through this command either.

A ROM-free call with a validation-origin context marked unavailable reproduced
`action_free_schedule_replay` before observation. This is a command-seam probe, not a real
power-loss experiment. The existing core recovery test is useful but does not cover this seam.
The four current command tests check source shape/arguments, not a successful invocation followed
by interruption and re-entry.

Repair: accept only unused roots or reservations that match this exact schedule, source, runner
and logical/physical root pair. Read-only preflight must not create claims. Reject foreign or
partial ownership. Test initial entry, own-reservation entry, terminal-only reopen, interruption
and foreign-claim rejection through the command boundary; terminal trials must execute zero new
actions and only never-claimed trials may continue.

### P1 — fit readiness counts intended lessons, not factual actions

`red_living_dex_targeted_train_dashboard_snapshot` counts `assignment.slot.focus_kind`. However,
the behavior policy deliberately has full support: an acquisition-focused lesson may choose a
different legal action. Coverage must use the recorded selected candidate's `features.kind`.
Its `fit_gate_met` expression also lacks a complete-campaign check. Although a final `passed`
snapshot rejects an incomplete campaign, an in-progress snapshot can already say “Fit gate: ready.”

An isolated evaluation of the production counter/gate expressions demonstrated the distinction:
six factual acquisition rows, three of them assigned development focus, report three development
rows and `ready=True`, even with only six of eight terminals present. This probe does not claim
that such a real campaign occurred or that a fit was executed.

Repair: one shared admission result, consumed by dashboard and fit command, must require the
complete frozen denominator, actual selected-kind floors, reset/root caps, train provenance and
censor handling. A truthful negative outcome counts as settled; a missing/interrupted outcome does
not. Add whole-projection regressions for alternate actions and incomplete campaigns.

### P1 — existing fitting is real, but the successor's admission is not connected

`fit_red_living_dex_causal_model_update.py` and `living_dex_causal_model_update.py` already provide
an immutable train-only fitter. Do not build another learner. That fitter currently loads the
complete authenticated corpus and checks that it extends its original integration model, with a
generic nine-settled-example minimum. It accepts no targeted schedule or campaign terminal roster.
The successor's six-new-row floor, actual-kind minima and four-root requirements therefore are not
enforced by this entrypoint. Its prior-record selection also starts from the integration-model ID,
not an explicitly selected current eighteen-example challenger.

Repair: add a bounded admission bridge and an explicit intended-prior binding. Verify the complete
23-row current corpus is retained, then append every admissible successor row with disclosed
shared-root treatment. No filtering by success, silent development import or lost negative row.
Reopening a completed immutable fit must not refit. The planned paired consumer must accept the
same permanently retired/train exclusion identities; that end-to-end connection is not proved by
the train-only PR.

### P2 — recovery documents contradict their own authority order

The generated active state still scheduled the old two-root 10-train/8-paired campaign, while newer
roadmap/handoff entries described four retired training roots, four paired roots and two reserves.
The coordination page opened on an older battle lane. Multiple historical sections called
themselves “active.” This can cause an agent with shortened chat context to repeat completed work.

This audit updates the source active-state configuration and its generated page, puts one current
checkpoint at the top of the roadmap/handoffs, and explicitly marks older checkpoints historical.
Historical evidence is preserved, not rewritten to match the new design.

### Interpretation limit — four paired roots are a small engineering check

Even four non-tied wins out of four independent paired roots give a one-sided exact sign-test
probability of `1/16 = 0.0625` under equal win probability; two-sided is `0.125`. Do not promise a
5% significance result from this bank. Repeated resets are not new independent roots. More actions
or candidate choices do not automatically fix this clustering problem.

The four-root check can still guide ordinary bounded Red development. Report paired successes,
failures, interventions, ledger progress and costs descriptively. Larger independent supply is
needed for a strong superiority claim, not as a reason to prohibit useful, disclosed development.

## Next sequence and exit criteria

1. **Repair the seams, then publish once.** Command-level recovery tests, factual-action coverage,
   complete-denominator admission and explicit current-prior selection. First make the shortest
   synthetic counterexamples pass; then run relevant tests and one coherent CI qualification.
   Do not merge PR 228 as ready merely because its existing tests pass.
2. **Verify the prospective 4/4/2 allocation without input.** The four training roots must be
   permanently excluded from future evaluation, with original provenance retained. Authenticate
   four separate paired roots and two reserves. Freeze eight lessons, at most two per training
   root, with acquisition and development each spanning multiple roots. Verify restart ownership
   and preserve a path-free receipt. There is no successor private freeze claimed by this audit.
3. **Collect the fixed eight lessons.** Keep all terminals, with no reroll of a claimed trial.
   Require at least six new settled factual rows including acquisition >=1 and development >=3,
   plus the frozen diversity constraints. Stop on a real admission failure and publish its cause;
   do not spend reserve evaluation roots replacing disappointing results.
4. **Refit the existing option scorer once.** Authenticate and retain the 23 existing train rows,
   append all admitted successor rows, bind the intended prior and preserve the new immutable
   model, complete denominator and fit diagnostics. If six to eight new rows settle, this means
   29–31 rows, not a new large-scale general player. Update only supported counters.
5. **Run a descriptive paired Red check.** Freeze challenger/control choices before either arm;
   exclude every trained lineage; retain all four paired outcomes. Inspect calibration, factual
   goal success, completion-ledger change, action/frame cost and safety interventions. No sealed
   Red benchmark, broad model superiority or full-player authority follows automatically.
6. **Give the model a small, useful playing loop.** Use several semantic decisions per bounded
   episode: acquire a missing species, make storage room, replenish supplies or develop/evolve the
   party, with model replanning after a typed failure. Deterministic skills still own mechanics.
   Measure new retained specimens, dependency completion and recovery, rather than CI counts.
7. **Grow Red competence, then transfer.** Expand reusable capture/evolution/storage/resource and
   puzzle/dependency tasks. Declare solo/version/trade/event limitations truthfully; do not claim
   151 living specimens on one ordinary cartridge. Integrate cross-version/trade inputs later.
   After useful sustained Red behavior, implement/adapt the Crystal observation and mechanics
   layer and compare transferred initialization with learning from scratch on bounded tasks.

The remaining distance to the **next small fit** is a recovery/admission repair plus one eight-slot
collection, not another story walkthrough. A calendar promise is not supported until the real
preflight succeeds; previous setup failures show why. Full autonomous play and a multi-game living
Pokédex remain substantially larger milestones.

## Resume contract

Focused ROM-free verification passed **19 tests in 198.17 seconds** across the retired-bank
command, strict reader, targeted core runner and dashboard modules. This is a regression baseline,
not proof the open findings are fixed. The two new probes deliberately exposed gaps outside that
suite's coverage. No production source was changed during this audit.

All **100 product-focus tests** also pass after updating the expected time box from eight to four
hours. Documentation, public-artifact, lint and all three registry reproduction checks pass.

Read `MISSION.md`, `NORTH_STAR.md`, `ACTIVE_PRODUCT_STATE.md`, then the current roadmap checkpoint.
Resolve exact GitHub/main/PR heads and the private recovery index; never assume a generic project
shortcut or a local branch named `main` is current. Reauthenticate retained artifacts before use.
Keep historical terminals and root claims immutable. At each stopping point record source, tests,
artifact/claim status, the next executable action, unresolved findings and explicit non-claims.
