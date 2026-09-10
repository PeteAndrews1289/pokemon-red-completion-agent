# Lance integration: engineering checkpoint

## Current — dialogue recovered; first Dragonair retained

The qualified introduction worked: support recovery defeated Gyarados and reached
the first Dragonair. It then stopped safely because ordinary reserve-entry screening
does not support Dragon Rage. This consumed56 actions/5,652 frames in addition to
the original69 actions/4,452 frames. Exact stateaa40123d and manifest81106c49 are
retained; all six party members are alive, money17,845 and bag unchanged. No new
query, fit or admitted checkpoint; model79 remains unchanged. No Lance victory.

The bounded survival actor now qualifies constant20/40 damage and pure stat boosts'
immediate HP effect. Other special-damage/indirect effects still abstain. It rereads
live stats each decision and remains conservative about critical hits, residual
damage and every available move. Ordinary type-only entry screening is unchanged.
Recovery explicitly opts into zero-item survival; both preflight and execution
receive a zero healing budget and authenticate retained switch history.

Read-only qualification of the exact battle produced incoming bounds
143/190/252/87/837/190 against HP172/118/71/129/34/139: attack with active Jolteon.
No frame or input advanced.136 focused tests passed. Independent review found no
blocker and requested fresh-live-stat and no-heal-after-switch discriminators;
both are present. Three completed CI runs since the fingerprint repair are green;
the latest source run is pending. This remains an engineering unblock, not learned
story progress. Next: one continuation from this exact retained battle, never a
Gyarados replay, then reorient on actual model-directed story experience.

Primary damage implementation: [cartridge battle engine](https://github.com/pret/pokered/blob/a1a22aaf84d1675bcdbaeb194592379d586d838e/engine/battle/core.asm).

## Historical — retained dialogue repair before its execution

The single Lance02 attempt is consumed. It reached Lance's actual automatic text
trigger, then failed after69 actions/4,452 frames because the intro text appeared
before the expected pending trainer latch. No battle occurred. The exact retained
statea3d29985 and failed manifest0740f527 were reopened without input; currency,
bag and party HP are preserved, with Jolteon prepared as lead. Model79 is unchanged.
The failed curriculum event remains in its aborted episode; no fit or completed
checkpoint is claimed. Never return to the preceding Agatha state to repeat it.

The primary trainer engine proves the causal ordering: `TalkToTrainer` calls
`PrintText` before `EngageMapTrainer`/`StartTrainerBattle`. The pending observer
was correct; the story handoff assumed the latch appeared too early. A distinct
validator now binds the cartridge's automatic text branch, text-table thunk and
trainer header to visible live text. It checks the stable text sprite and
high-byte-first header pointer, not the text-ID byte that aliases an arrow-blink
counter. Wrong pending/active identity, resources, party, position and event changes
still abort. Each pre-latch acknowledgement is revalidated; text loss gets no blind
confirmation and no repeated movement/interaction.

The existing failed-state recovery driver has an explicit zero-item Lance-text
mode. It restores only an authenticated retained failure, logs support costs, and
does not resample a choice or create a fit row. This is tested engineering awaiting
one prospective recovery, not a successful Lance fight.520 focused tests and
configured typing of436 source files passed; this is not a full-suite claim.
One read-only report initially used an incorrect reward attribute; correcting it
changed only report serialization, with no inputs or overwritten output.

Independent review confirmed the causal ordering and caught a `MapId` enum crossing
an exact-integer decoder boundary; the fix has an explicit regression. No new
external-model session or quota observation occurred during this repair. Earlier
Flash usage below remains historical. The next operation is retained-text recovery,
then a useful actual model choice; Phase4 and its2/3 sub-checklist remain open.

Sources: [trainer engine](https://github.com/pret/pokered/blob/a1a22aaf84d1675bcdbaeb194592379d586d838e/home/trainers.asm),
[text scrolling](https://github.com/pret/pokered/blob/a1a22aaf84d1675bcdbaeb194592379d586d838e/home/joypad2.asm),
[symbols](https://github.com/pret/pokered/blob/3f618d59edf43918f48f5e558c34e04cb2fc5619/pokered.sym).

## Historical — pre-execution engineering checkpoint

## Scope and current truth

This is the first sub-session of the authorized eight-hour Phase4 block. Model79
and the retained Agatha endpoint remain unchanged. No new gameplay, fit, completion
or comparative advantage is claimed by these engineering checks.

Lance is an explicit cartridge trainer objective. Its actual battle-defeat flag
differs from the later story-completion flag; the operator verifies both through
the existing battle receipt and final semantic fact. High-level model features and
the79-row corpus are unchanged. Buttons remain deterministic specialist authority.

## Script and control boundary

The supported Red revision gate precedes all public decoding. The distinct corridor
grammar follows the script table, coordinate branch, event gates, movement list and
queue-drain script. Actual cartridge inspection with zero controller input derives
37 movements ending at the declared door-lock trigger. Unknown revisions, malformed
branches, consumed arrivals and out-of-bank pointers fail closed.

The simulated queue executes in reverse storage order. The pure RLE decoder retains
storage order; the arrival adapter reverses it and limits expansion to100 steps to
avoid the pinned queue-index byte. Tests independently vary movement, placement,
events and bank pointers; no ROM bytes or private artifacts are published.

Navigation stops before the automatic trainer-text trigger. The battle specialist
owns exactly one final movement and bounded waits, requires the exact pending
trainer identity, and cannot retry the entry. Ordinary navigation readiness and
drift assertions remain intact. Pending dialogue is an explicit battle-entry mode,
not a blanket readiness bypass; default callers retain their existing checks.

References: [Lance map script](https://github.com/pret/pokered/blob/master/scripts/LancesRoom.asm)
and [overworld queue consumer](https://github.com/pret/pokered/blob/master/home/overworld.asm).
These explain the supported adapter, not cross-game or modified-ROM competence.

## Review adjudication

The isolated Flash3.8 High draft was blocked by a headless command permission and
produced no edits. A single no-tools fallback returned a small RLE proposal. Codex
corrected its mutable-byte acceptance, invalid test import and miscounted127-step
fixture, then implemented and independently tested the integration. No broad
permission bypass, emulator access, fitting or publication was delegated.

A read-only code reviewer found reverse queue consumption, unsafe maximum expansion
and flat-file pointers outside the CPU ROM window. All three findings were accepted
and received discriminating tests. This is targeted review, not a complete mutation
score or proof of live behavior. Claude was not used in this slice.

Flash reported76,368 total tokens for the blocked session and19,716 for the fallback.
These are reported token counts, not subscription consumption. The CLI has no quota
command; bounded authorized-app inspection did not expose a fresh quota display.
Five-hour/weekly remaining and reset times are unavailable, not inferred from tokens.

## Phase4 exit remains open

Verification before publication:310 combined focused tests passed, including the
previous CI golden, route executor, profile/command integration and new mechanics.
Configured typing passed all435 source files; lint, product-focus, public-artifact,
documentation and regenerated-registry checks passed. A broader manually requested
typing scan of every historical script reported104 errors in23 unchanged files;
those scripts are outside the configured CI typing scope and were not silently
fixed or described as passing. The prior published head's CI34304092996 is green.
No full-suite pass is inferred for this new source from these targeted checks.

### First saved-state preflight and bounded correction

The first published-source preflight sent zero inputs and found no available goal:
the trainer decoder deliberately refused final class47 because it has no following
class pointer. Its guard was not simply widened. An explicit exact-Red opt-in now
admits only the first set, with a14-byte/six-member/bank bound; ordinary callers
retain the previous refusal and a second final-class set remains unsupported.
The actual cartridge quote is five opponents and6,138 reward, not a copied roster.

A separate working-tree diagnostic used an input-forbidden controller and made no
predictions, fits or execution declaration. It found one available story goal,
14 computed route steps and37 cartridge-controlled entrance movements. Source
publication checks were skipped only inside that diagnostic process to batch the
repair; this is not execution qualification. The final new attempt must revalidate
clean published source normally. The Agatha endpoint and all79 rows are unchanged.

This boundary will therefore produce a guided curriculum row if it settles, not a
comparative policy-choice row. The final Full Restore remains reserved. Neither
preflight failure nor the static working-tree result advances a training counter.
After this correction,348 combined focused tests passed. Configured435-file
typing, lint, documentation, public-artifact and product-focus checks also passed;
the prospective source registry was regenerated before publication.

The2/3 income-to-story checklist is a submilestone, not a percentage of Phase4.
Two additional guided boss wins cannot establish model-directed completion.
Any retained endgame result must disclose learned choices versus forced steps and
deterministic controls, preserve all failures, and verify concurrent Champion and
Hall-of-Fame evidence. It would still be a bounded development continuation, not
official clean-start completion under the unchanged completion contract.

Next: publish qualified source, inspect the actual model79 menu without input, and
execute at most one newly declared bounded outcome before reorienting. Preserve the
final recovery item unless genuinely needed; do not fabricate alternatives merely
to turn a singleton lesson into comparative evidence.
