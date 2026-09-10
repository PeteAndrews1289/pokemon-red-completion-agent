# Next session — safe travel-budget stopping

## Mission check

1. **Capability:** long travel must end safely when a local budget is exhausted,
   preserving the true game state for later planning instead of discarding it.
2. **Learned authority:** keep model66's real destination choice and costs intact;
   a forced safe stop/recovery is support, never a second learned choice label.
3. **Transfer test:** ROM-free interruption sequences at movement, retry, wait,
   transition and start boundaries; include different limits and exact completion.
4. **Cheapest falsifier:** after the last allowed interruption is resolved, can
   the route stop before another movement triggers an unhandled battle, with an
   exact resumable endpoint and the original failure still reported?
5. **Time box:**90minutes for the bounded control repair and focused qualification.
   Use existing route/episode/recorder machinery, not a new campaign framework.
6. **Stop condition:** lost failure evidence, unsafe or falsely certified state,
   budget overrun, changed selected goal, specimen loss, or a second failed skill.
   Stop and reorient; no cap-increase loop or consumed replay.

## Work order

Session started: adopt the six-part mission check above as the working plan.
Classify this as bounded maintenance unblocking the existing useful-acquisition
lesson, not learned progress. Codex implements directly; no external agent task.
Keep the16-interruption limit unchanged and qualify before any new gameplay.

- Inspect all three route interruption checks and their pre-action boundaries.
  Preserve configured limits and action/frame accounting. A safe stop should
  occur before creating interruption17 when the budget covers16; allow a route
  that genuinely completed at its exact limit to finish.
- Qualify initial-interruption, delayed-after-wait, movement-retry and failed
  handler paths. Never assume field readiness from coordinates alone. Verify
  terminal recording retains the actual endpoint after a controlled stop.
- Review whether unsafe failures retain enough private state for diagnosis and
  explicitly gated recovery without certifying them as safe continuation saves.
  Do not add a broad replay or recovery framework.
- The consumed Route10 attempt has no exact terminal emulator state. Its failed
  trace and selection remain immutable; the earlier Route11 save is historical.
  Choose and explicitly disclose a supported next execution origin after repair.
  A fresh development branch from an older save must not be mislabeled continuous
  play, nor erase the failure or become a resample of the consumed assignment.
- Only after those gates, attempt one useful bounded source choice and fit an
  actually admissible outcome. Do not fit the existing incomplete infrastructure
  failure as if it had an authenticated settled terminal outcome.

## Roles and deliverable

Codex owns implementation, qualification and publication. No external work is
pending. Flash has done enough for the preceding allocation session; use it only
for a separate narrow failure-boundary test challenge if genuinely useful.
Claude is optional for a consequential claim/admission review, not a mandatory
gate. Check five-hour/weekly quotas before and after any external session.

Deliver a measured recovery result or a precise failure stop, update roadmap2/3
only when its third item is actually achieved, preserve Phase3and the Red-first
living-Pokédex/ROM-hack/Crystal sequence, and refresh handoffs and narratives.
Recommended: Astra High, Fast off.

## Implementation qualification

Pre-action guards now stop before movement, retry waits, transition waits and
readiness waits once the configured interruption count is exhausted. An already
acknowledged terminal can complete at the exact limit; mandatory unsettled
transitions are not waived. Typed budget exhaustion stays distinct from an
unrecovered interruption. Failed readiness waits retain prior receipts/counters.

An opt-in private failure-state stream retains exact bytes and held buttons
without input, normalization, safe-checkpoint certification or training admission.
Component failures are saved before recovery; unsafe terminal-boundary failures
are saved before the emulator closes. This does not recover the already-lost
historical Route10 state, and is not a guarantee against a power loss or disk failure.

ROM-free tests cover limits1,2,8,16, initial/same-coordinate/wait/transition
interruptions, exact-limit completion, handler failure, unsafe readiness,
serialization and write-before-close wiring. Next verify the serializer on the
historical authenticated save with zero input; no learned choice or replay.
