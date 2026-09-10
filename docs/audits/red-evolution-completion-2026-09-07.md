# Evolution throughput and retained-state audit

## Verdict

Ponyta advanced from level 32 / 33,276 XP to **level 35 / 42,882 XP**, gaining **9,606 XP**.
All 17 specimens and 14 living species survive. The actual throughput is sufficient to make
this development operation practical on the current machine; a larger trainer or new venue
is not justified by this result. **Full evolution still did not complete.** Model `1b26aa44`
remains at 35 examples, with no fit or new model-selected outcome. Checklist stays 2/5.

## Two closed component attempts

The first continuation returned 18 four-battle quanta: 72 reported completed training battles,
9,500 XP, and two healing trips in those returned reports. Its terminal contains another 106 XP
earned before a later failure. The complete trace has 74 battle entry/exit intervals; do not
label all 74 wins because the last two are outside a returned quantum report.

The run stopped after 4,277 actions / 348,071 frames in 17.619 seconds. At the new level, the
highest-minimum-level venue heuristic selected the Mansion. Its old travel routine tried Dig
from outdoor Route 11 and failed. Generic movement readiness remained true, but action-free
inspection of the retained terminal found a standard dialogue box still visible.

The narrow code correction keeps the current venue for a quantum when cartridge type/level
eligibility and the existing measured fightable-share guard both permit it. This avoids changing
locations just because the trainee levels up. It neither lowers battle safety nor claims an
optimal XP policy. ROM-free tests distinguish local eligible, local ineligible and non-local
cases, including a local Mansion case rather than a Route 11 special case.

One prospectively declared successor used the retained terminal without reset. It stopped after
40 actions / 500 frames, before training: the swap intended to put Ponyta in front instead
exchanged it with Farfetch'd in slot two. The exact-order verifier caught that wrong mutation.
No XP or species were lost. **The local-venue correction has not yet been live-qualified** because
the successor never reached its training loop. Both attempts are closed, not candidates to retry.

## Recovery truth

Both terminal saves were SHA-verified and reloaded with no controller inputs or advanced frames.
Party and every box matched the retained observations. The final terminal has Ponyta in slot two,
91/93 HP, no battle, no held button and no detected standard dialogue box. These facts do not
prove that every party-menu state is settled. The swap's selected member and target still need
observational verification, rather than inferring menu ownership from a shared cursor counter.
The exact cause of the incorrect source selection is not claimed as proven from the terminal.

[Evidence](../evidence/red-evolution-completion-2026-09-07.json) distinguishes returned quanta from
the failed prefix and preserves both terminal identities. No diagnostic state replaced official
player checkpoint `b64023f4`; no diagnostic rows may silently become fitting data.

## Reorientation

The prior concern about grinding duration was largely falsified: meaningful XP accrued in
seconds. The bottleneck is now reliable state-dependent menu interaction, not battle speed.

Next session must stay narrow: inspect the retained party-menu boundary, verify selected source
and destination before confirming a swap, and test multiple party orders / residual menu states.
Then qualify the complete evolution under a fresh bounded continuation and return to a
model-selected lesson. Do not rebuild travel, add features, replay the game or move to Crystal.
Partial XP is still an incomplete goal, not a learned success. Its eventual credit must remain
separate from exact evolution verification.

No stage exit or milestone was weakened. No external reviewer was invoked; a further attempt
was not launched after the declared successor's stop condition.

## Checks

110 focused native-evolution, party-training, goal-context and resource-routing tests passed,
plus 157 collection/navigation/goal-protocol, focus and roadmap tests (267 across these disjoint
selections). Type checking passed for 400 source files. Current source registries and their
goldens were regenerated without touching historical outcome evidence. Lint, documentation,
active-focus, public-artifact and diff checks passed; the roadmap graphic was refreshed.
No full-suite or learned-performance claim is made.
