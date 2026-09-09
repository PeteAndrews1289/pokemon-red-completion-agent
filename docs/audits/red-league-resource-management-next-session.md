# Next session: manage battle resources before the party is stranded

## September 9 implementation checkpoint

The prospective integration is implemented, not yet live-qualified. A profile
may explicitly select a one/two-owned-Full-Restore damage-aware controller from
the start of a story battle. Default zero-item behavior is unchanged. The real
story and Champion callers bind the budget before input and verify exact actual
item decrement, including Champion's battle exit and epilogue. Finite healing
and switch counters survive battle-loop restarts; no risk controller is enabled.

The title-neutral V4 resource quote exposes maximum consumption/available stock
as a conservative cost allowance, not predicted actual expenditure. Existing
observed outcomes still charge actual use. A new economic-plan contract is
declared before collection; native admission rejects V4 quotes under old plans.
The read-only reviewer identified this admission gap and the implementation
repaired it with real sealed-episode round-trip/rejection tests.

The focused integration suite passed 583 tests; an additional multi-turn case
then passed in the 28-test survival suite. Mypy checked 453 source files and Ruff
passed. These are targeted checks, not a new full-suite result. No gameplay,
model fitting, authority promotion, or phase-exit claim follows from these checks.

Operational cautions: each new cartridge story objective drops a previous
recovery allowance unless explicitly reapplied; tests cover this transition.
A two-item allowance cannot remain available after field healing leaves only
one item. The next live plan must match actual stock and reserve behavior, not
assume that an item budget guarantees enough resources to finish the League.

## Verified starting point

The separately declared `89d03dd5` continuation passed the repaired Lance text
boundary and entered battle. It consumed345actions/31,944frames/one field item:
one genuine native82 healing choice, then one forced story continuation. It
stopped at Aerodactyl with all six members alive, all30specimens retained and no
Champion attempt. The original prebattle failure remains preserved separately.
Neither failure was resumed, fitted, or turned into an admitted checkpoint.

The [path-free evidence](../evidence/red-model-led-league-resource-stop-2026-09-09.json)
includes whole-trace quarantine verification and zero-input retained-state analysis.

The new stop is not generic PP exhaustion. Jolteon has83/172HP, Blastoise66/217HP
and Farfetch'd8/139HP, all below the ordinary half-HP screen but with damaging PP.
Active Dugtrio has73/118HP and passes the health/level screen, but its Ground
attacks cannot damage Aerodactyl. Electrode and Drowzee fail level/offense gates.
The controller has no in-battle item authority.

Simply reducing the HP floor is not a supported fix. Actual critical-inclusive
incoming bounds are201,297,354,122,999,266HP by party slot; the zero-item survival
controller still refuses, even with switch history optimistically empty. Ordinary
bounds are105,170,185,64,613,139. Blastoise66HP barely exceeds ordinary64, not
critical122; that is risk exposure, not proven-safe survival. Incoming moves are
Supersonic, Bite, Take Down and Hyper Beam. This does not prove the game is
unwinnable—only that the current conservative recovery contract cannot qualify
this endpoint. No new critical-risk allowance is authorized by this diagnosis.

## Six-part mission check for the next implementation

1. **Capability:** earlier, damage-aware management of attacks, switches and
   legitimate healing items within a reusable bounded story skill.
2. **Learned authority:** native82 still selects the high-level goal; battle
   support stays deterministic. Expose the declared resource cost before goal
   selection and charge actual spending to its outcome. No battle-model promotion.
3. **Transfer test:** varied HP, moves, opponent changes, inventory and remaining
   budgets in ROM-free multi-turn tests; then one prospective correlated Red
   continuation. No cross-game or independent-evaluation claim.
4. **Cheapest falsifier:** first show a multi-turn case where early switching/healing
   preserves a useful attacker but waiting for the half-HP screen strands it.
   Include a case where even the declared resources cannot help and stopping is
   the correct outcome. Do not start a boss cohort before this passes.
5. **Time box:** one focused engineering session, roughly60–90minutes for the
   smallest integration and tests; this is an estimate, not a deadline promise.
   Reassess before gameplay if the existing components cannot compose cleanly.
6. **Stop condition:** unsupported mechanics, unaccounted item use, hidden actor
   substitution, stale identity/party state, or no plausible resource envelope.
   No automatic risk mode, same-plan retry, failed-state resume, or replacement win.

## Smallest implementation seam

- Reuse `red_trainer_survival.py`, `red_trainer_damage.py` and
  `red_trainer_healing.py`. Do not create another boss-specific controller.
- Make any small in-battle Full Restore budget explicit in the selected story
  capability/profile and immutable execution contract. Default ordinary behavior
  stays zero-item and unchanged. The existing recovery controller is currently
  reserved for explicit active-battle recovery; it is not already wired into
  freshly selected story execution.
- Qualify that controller from the beginning of the battle, while recoverable
  options remain. Do not wait for a generic exception and silently substitute it.
- Reconcile `run_prepared_trainer_funding`'s active-recovery-only item restriction,
  the outer story bag-equality check, the runtime guards and the receipt together.
  A broad `battle_runner_override` must not itself grant spending authority.
- Preserve exact trainer/event/position identity, living-specimen ledger, item
  claims before input, fresh damage observations and finite switch/action budgets.
  Emit actual items spent, not the old unconditional zero-item receipt.
- Capture the selected story's total resource consumption in existing outcome
  records. Old forward-head fits retain their old controller/resource contracts;
  changing this actor must not relabel their targets or promote them.

## Required evidence before another live attempt

Test active immunity despite healthy HP; below-half survivable switches;
equal/lethal damage boundaries; enemy changes; unsupported incoming effects;
exactly bounded healing; zero-item mode; stale source/state/target rejection;
item failure retaining its claim; and resource exhaustion that genuinely stops.
Exercise the real story caller plus outer bag/party guards, not only a mocked
successful battle runner. Independent review should attack authority and resource
accounting, not demand another statistical campaign.

If an actual prospective state cannot support the declared battle envelope,
choose useful party development or earned supplies instead of repeatedly attacking
the same boss. Keep temporary fainting policy separate from permanent specimen
loss: the current controllers stop on any faint. Do not silently change that
contract or claim a living Pokédex inherently requires a no-faint playthrough.

## Reorientation

Phase4 is still open. The current three-item continuation checklist remains1/3:
shared fixed-damage entry qualified; a completed model-choice-to-story continuation
and concurrent Champion/Hall-of-Fame evidence remain unverified. This is not an
overall phase percentage or a completion-time estimate. Training has already
produced bounded models; this blocker concerns reliable execution of their
selected goals, not the absence of training infrastructure.

The independent internal reviewer agreed with the resource diagnosis and this
direction after inspecting both the code and exact retained-state bounds.
Claude/Antigravity were not invoked during this session; their quota windows were
not queried and no external audit is claimed.
