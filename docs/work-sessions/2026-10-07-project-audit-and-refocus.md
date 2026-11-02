# Project audit and next work order

Date: October 7, 2026. This audit supersedes earlier next-session proposals.
The user requested a project audit, an explanation of repeated work, clear next
steps and cleanup of unnecessary documentation. No gameplay or model fitting was
authorized or performed by this audit.

## Decision

Keep the current earned Silph save and the existing battler. The immediate work
is durable player configuration and automatic recovery from an interrupted
collection loan, followed by Sabrina through that same player. Do not restart Red,
rebuild the battle trainer or finish the deferred sequence learner now.

There is real integration progress, but progress in game coverage has repeatedly
been reported alongside unfinished strategic ownership and session-specific
operational repairs. Those are different deliverables.

These are not all new discoveries. The [October 6 audit](2026-10-06-post-run-autonomy-audit.md)
already identified zero added readiness weights and private whole-player
composition. Since then, shared menus and genuinely model-selected story play
have improved: the current Silph choices are not the older supplied phase order.
But the configuration and recovery weaknesses were not closed, so ordinary play
continues to uncover seams requiring another helper. Repeating the diagnosis
without making those fixes durable would repeat the same process failure.

## Verified position

The earlier assisted new-save lineage completed all 36 story objectives,
Champion/Hall of Fame and the declared 124 registrations. Its preparation, phase
ordering and recovery included substantial supplied support. Keep that result as
mechanical coverage and a source of checkpoints, not final autonomous acceptance.

The current shared-player lineage independently authenticates at
`red-model-selected-silph-20261007-v1/runs/segment-011`:

- Six badges, 27 of 36 story objectives and 13 registrations.
- Silph rival, eleventh-floor guard, Giovanni and Master Ball reward flags set.
- One Master Ball, 9,085 cash, field-ready Saffron Pokémon Center.
- Gloom 28, Blastoise 36, Pidgeotto 31, Doduo 26, Raticate 37 and Spearow 17.
- Original six with full HP, PP and clear status; no held controller inputs.
- State SHA: `08f7dc316e66d18595659ffe63ad283aa7628027a22b38a1e301015c89726d73`.
- Context SHA: `846927c5c7bb7b405249c82d27801a74d4c0d9ed09486d4ec937b812d896ad74`.

The latest Silph block recorded 30 model-selected and six support goals, 388
learned combat choices and seven failed goals. Three rival losses, a failed
training return and the boxed-Ekans interruption remain real costs, not erased
attempts. These counts come from the authenticated closing evidence; this audit
did not replay every frame or independently reconstruct the entire ancestry.

The audit independently loaded the terminal through a read-only controller,
verified protected pins, reward flags, recovery and unchanged bytes, and inspected
the unwrapped shared menu. It offered 11 real options; the frozen parent selected
Sabrina. It also offered the exact previously failed boxed-evolution profile.
No game inputs or emulator frames were advanced.

## Findings in priority order

### 1. The shared configuration forgets a known execution failure

The failed boxed-evolution profile
`ccbbecd095f501884443967f49e22e20eb0040047327d9cd6e35b19301a7b501`
is excluded only by the closed Silph session's wrapper. It reappears in the
ordinary shared assembly. Read-only runtime inspection finds neither a party
guard nor an evolution-settlement callback attached.

The public [boxed-evolution executor](../../src/pokemon_red_completion/red_native_boxed_evolution.py)
already supports settlement. The [party guard](../../src/pokemon_red_completion/red_player_party_guard.py)
and continuation contracts already exist. The current private assembly does not
connect those pieces. Last session needed a bespoke ordinary-PC return to recover
the original roster. Another session can encounter the same failure even though
the prior report called it handled.

Priority: repair the connection and persist its capability state. Until verified,
carry the exact failed-profile exclusion into the shared configuration. Do not
disable all collection or force Sabrina by deleting legitimate alternatives.

### 2. Working behavior is still assembled by dated operational scripts

The integrated `run_native_continuous_player` implementation exists in
[the public runtime](../../src/pokemon_red_completion/red_native_player.py), but
there is no invocation of this current loop in public scripts/source outside its
definition. Older public autonomous-player and collection launchers do exist;
they are not the current shared stack.

The current private Silph driver has a static import closure of 168 private
helper modules, with an 18-module longest shortest dependency path. This is an
AST dependency count, including conditional imports, not a runtime module count.
The central shared inventory file is 1,836 lines. Some inherited helpers restore
shared module globals around imports. Active behavior depends on exact flags,
dated roots, candidate identities and session-specific wrappers.

Priority: create one stable configuration/resume interface for the existing
working assembly. Preserve explicit actor scope, capability exclusions, costs and
source identity. Do not merely add another date-stamped wrapper. Do not make
rewriting all 168 helpers a prerequisite: retain and disclose legacy dependencies
behind the first stable entry point, then extract only code needed for correctness.
This remains private-asset-dependent until further packaging is genuinely done.

### 3. The added preparation observations do not influence the base model

The actual deployed parent is `06f6493d05b6ce41dc17028e77e59b545c21d1886d2bdfa6055f7ef5b3203d87`,
with 141 settled examples, feature version 7 and 356 feature rows.

| Added feature group | Rows | Nonzero outcome coefficients |
| --- | ---: | ---: |
| Party readiness | 252 | 0 of 2,268 |
| Opponent/challenge | 54 | 0 of 486 |
| Preparation | 13 | 0 of 117 |

The 319 added rows are all zero after the existing version upgrades in
[the option-value model](../../src/pokemon_red_completion/living_dex_option_value.py).
Older coarse party-risk/resource features can still affect choices. This is not
proof that the model ignores every party fact, nor a claim that 90% of its ability
is missing. It does prove that merely exposing richer preparation observations
does not make this parent learn to use them.

A separate 36-row consequence head has learned scoped readiness behavior. Its
Silph reuse selected training but overprepared and failed its return, so it was
rolled back. Recent Silph progress used existing weights; ordinary gameplay does
not automatically fit either model.

Priority: reuse the current parent where it already chooses usefully. If the next
play exposes bad preparation, teach targeted TRAIN contrasts through the existing
learner/head, covering both need-to-train and ready-to-stop. Do not fit the current
DEVELOPMENT save, assume any loss means underleveling, or launch a general refit
before observing a policy failure.

### 4. Interrupted evolution can lose its local healing count

The bounded evolution loop accumulates battle and healing totals locally.
Its 600-second path raises a generic error instead of a counted partial-training
result. The outer action/frame meter survives, but those local counters are not
attached to that exception. Existing tests expect the generic wall-limit failure;
they do not prove automatic loan return or complete nested-heal reporting.

Connect the existing settlement path in a finally-safe manner, retain partial
outcomes/costs, and test interruption after actual partial progress. Do not invent
a historical nurse count or silently rewrite old sealed receipts. The earlier
inner-healing count remains explicit accounting debt unless independently recovered.

### 5. Documentation and scoreboards exaggerate clarity

Before cleanup there were 747 Markdown files, including 431 work-session reports,
53 chronicle files and 139 documents directly under docs/. Volume alone is not
the defect. Live policy files contained old gameplay histories and contradictory
next assignments. The drive index emphasized an older protected save, and the
handoff simultaneously called Silph complete and active.

The active board also displayed an old 135-of-12 TRAIN target and a completed
September 21 experiment checklist during current integration work. Those are
historical results, not the percentage of an autonomous player completed.

Current instructions are consolidated. Historical results remain historical.
The active integration task claims no new learning output, and the current
delivery checklist describes unfinished integration rather than an old 100% trial.
Final Red exits and their unpassed status are unchanged.

## What is reusable

- Semantic cartridge/emulator observation, legal controller execution and route graphs.
- The battle classroom, fitted battlers, switching support and scoped story bindings.
- The frozen goal selector, existing consequence learner and real-option menus.
- Native gym/story/League, capture, gift, trade, fishing, Safari and evolution skills.
- Registration memory, physical-stock verification, party guards and continuation costs.
- Earned checkpoints, failures and past training evidence.

These are substantial assets. The recommendation is to connect and stabilize them,
not replace them. The immediate battle wins show that lack of a brand-new combat
model is not the first obstacle.

## Next session work order

**Outcome:** an unchanged, reusable player configuration continues from 011
through model-selected Sabrina and ordinary recovery, without a bespoke operator
helper. A failed battle is acceptable if the player can recover and select its
next useful action; a hidden supplied win is not.

1. Declare the current 011 state/context and existing actor/configuration in one
   reusable resume path. Carry the exact boxed-evolution exclusion until repaired.
   Preserve other choices and never hard-code Sabrina as the selected action.
2. Connect existing party-loan settlement and counted partial evolution. Add
   regression cases for wall-limit interruption, roster/stock preservation,
   continuation reload and inherited costs. Use retained failure/checkpoint copies
   for this local seam; do not replay the story or copy diagnostic progress forward.
3. Verify that rebuilding the same configuration still offers real story,
   collection and recovery alternatives. Recheck the previous failure cannot
   silently re-enter through a missing wrapper flag.
4. Run that configuration from actual 011, retaining every failure. The read-only
   baseline chooses Sabrina; let the model choose. If it selects another legitimate
   useful goal, retain that result rather than overriding it. Confirm the normal
   loop reaches a new meaningful outcome and can resume from its own checkpoint.
5. If a preparation decision, rather than execution, blocks play, make one focused
   correction with the existing learner and distinct TRAIN fixtures. Check both
   underprepared and prepared conditions before continuing the same ancestry.
   Do not initiate sequence learning or redesign the battler.

**Acceptance:** source/configuration is reproducible; temporary loans settle or
resume safely; actual costs survive interruption; native Sabrina reward and healthy
return are verified if reached; no per-segment helper, hidden tactical override,
source reset or copied victory is needed. A durable same-worker recovery and useful
continued choice is partial progress, not a claim Sabrina is complete.

**Firm reassessment:** within 45 minutes decide whether the extraction is genuinely
bounded. If it expands into migrating the old helper tree, retain the working
assembly behind an explicitly documented interface and focus on the demonstrated
recovery defect. Reassess any local tactic after 15 minutes/two equivalent failures.
Default aggregate block: up to 3 hours, including tests and closeout. Report the
actual achieved outcome, not “ready” based solely on unit tests.

No fresh game, broad fit, new subsystem, historical save merge, external agent,
GitHub publication or ROM-hack/Crystal work is included.

## After that session

Continue the same player through Viridian Giovanni, Victory Road, the League and
postgame registration. Use the older complete lineage as reusable evidence and
checkpoints, not another completion task. Only after this configuration handles
story, recovery and collection without operator repairs should it be frozen for
the final genuinely fresh run. There is no evidence-backed completion date yet:
Sabrina's no-helper continuation is the next measurement needed to estimate it.

## Audit verification and cleanup

278 focused ROM-free tests independently pass for boxed evolution, settlement,
party identity/continuations, Silph bindings and model-record integrity.
This is a risk-focused integration/learning audit, not a claim that every function
or the entire test suite was reviewed.

The final documentation/focus/roadmap check adds 192 passing tests; all local
Markdown links, generated projections and targeted lint pass. The cleanup corrected
three relocated links and changed a roadmap test fixture to supply existing
evidence before checking the unchanged Red-before-hack gate. No safety gate was
weakened. Rendering tests now cover the short policy pages and generated roadmap,
and reject a stale learning quota during integration work.

The read-only terminal checks pass with zero controller inputs, zero advanced
frames and unchanged save bytes. Two offline model selections occurred across
menu-inspection attempts; no selection was executed and no weights changed.
One import typo and one output-field typo in the inspection command were corrected;
neither was a gameplay failure or a product fix.

Thirty-eight obsolete dated plans/audits/reviewer handoffs were moved into
[the retired-plan archive](../history/retired-plans-2026-10-07/README.md), with relative
links repaired. Current policy, handoff, roadmap, introduction, narrative and drive
index were simplified. Original documents/configuration were backed up under the
drive's Recovery folder before editing. Unique history, evidence, source code,
models and saves were not deleted. Documentation cleanup is not model progress.

Machine-readable findings: [audit evidence](../evidence/red-project-audit-2026-10-07.json).
The handoff is the sole current dispatch; this report preserves the rationale.
