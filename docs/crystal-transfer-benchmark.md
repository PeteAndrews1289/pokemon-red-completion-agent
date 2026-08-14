# Crystal transfer benchmark

## Current decision

The first Crystal experiment tests one portable component before anyone writes a full Crystal
walkthrough. Red has supplied a genuine nine-goal manager fitted from 54 teacher-labeled examples
and given authority over 27 bounded, previously opened contexts. That is not a complete learned
Red-playing agent, and no learned model has completed Red. Crystal now asks the next falsifiable
question: do those narrow learned weights reduce the amount of new teaching required in a
different generation?

The exact public plan is
[`configs/crystal-goal-manager-transfer-v2.json`](../configs/crystal-goal-manager-transfer-v2.json),
with SHA-256 `e07ef52b1146f4c0ee05d003eea2f10f949e41a84398bb071def37f43ebd720b`.
It contains no capture, teacher label, prediction, private path, or ROM bytes. The older twelve-case
Red destination test remains 0/12 opened and is not reused.

V1 named international Crystal 1.0. The owner later supplied 1.1 while every Crystal counter was
still zero. V1 is preserved as a superseded preregistration; it was never booted and opened no
context, label, or prediction. V2 uses fresh experiment and slot identities, so evidence from the
two targets cannot be combined accidentally.

## What is implemented before cartridge access

The ROM-free transfer gate is no longer a design note:

- Crystal projects story, registration, living ownership, level-cap ownership, evolution, team
  readiness, safety, supplies, storage, control, and world knowledge into the same nine normalized
  pressures used in Red.
- Its model-facing projection contains no title, species, move, map, coordinate, item, RAM address,
  capability identity, private binding, or candidate position.
- A private capability vocabulary covers ordinary play plus Gen II completion mechanics: capture,
  storage, level/item/happiness/time/trade evolution, breeding, time of day, field moves, static and
  roaming encounters, and puzzle interaction.
- Unknown and missing capabilities hard-mask a goal before its private resolver can advertise
  executable authority. Every unavailable kind remains visible with a portable reason.
- The revision-specific reader is bank-aware and uses a public allowlist derived from generated
  symbols. It coherently double-reads party and Pokédex state, decodes Gen II party structs and
  status bits, masks PP-Up bits, verifies the separate party species list and terminator, and
  rejects torn or contradictory snapshots. Eggs fail closed until the later breeding-aware shared
  observation contract can represent them without exposing their hidden species.
- Pokédex progress covers the 250 non-event national targets and excludes event-only Celebi. That
  does **not** mean one Crystal cartridge can obtain all 250: the later multi-cartridge collection
  contract must account for version exclusives, trades and trade evolutions explicitly.
- The read-only storage layer follows Crystal's actual fourteen-box layout across SRAM banks two
  and three while substituting the live active-box copy from bank one for its stale saved copy. It
  coherently re-reads all 280 slots, validates counts, terminators, struct/list agreement and
  levels, derives living and level-100 ownership across party plus PC, and records eggs only as
  opaque eggs.
- The items and Balls pockets are also decoded coherently from counted item/quantity pairs. Pocket
  membership, stack bounds, duplicate identities and terminators are checked before the adapter
  reports capture-ball and team-recovery reserves to the portable pressure projection.
- Transfer fitting now has two mechanically paired candidates. Both use the authenticated Red
  feature mean and scale, the same Crystal rows in the same order, and the same fixed optimizer.
  One begins with Red's learned weights; the conservative scratch comparator begins at zero. Each
  budget resets from its original initialization.
- A canonical path-free catalog binds every slot to its cartridge, source, state, question,
  availability-menu and private-binding digests. Label-free hashing changes candidate order across
  slots, and every partition must place its intended answer in at least eight of nine positions.
- Prediction commitments require complete slot-by-predictor coverage. The frozen Red model and
  three baselines have fixed public identities; after adaptation, all six fitted model hashes must
  match every corresponding sealed prediction row.
- Sealed results form one canonical 27-outcome artifact. The evaluator reconstructs the catalog,
  commitment and outcome digests before scoring and cannot emit an intermediate statistic.

These facts make the code ready for live qualification, not already qualified. The v1.1 entry gate
now passes, but no Crystal context has been opened and no Crystal model prediction exists.

## Pinned cartridge and source boundary

The first live target is Pokémon Crystal international v1.1:

| Identity | Frozen value |
| --- | --- |
| Game ID | `pokemon.mainline:crystal:gbc:international:rev1` |
| Header title | `PM_CRYSTAL` |
| Size | 2,097,152 bytes |
| Revision | 1 |
| SHA-1 | `f2f52230b536214ef7c9924f483392993e226cfb` |
| Source authority | [`pret/pokecrystal`](https://github.com/pret/pokecrystal) at `7a7881d0d62e0ddbd82dcf10e7116807487ac651` |
| Generated-symbol authority | commit `cc6fc04f19c645f5c40f64f8d88b2ab42c7bdde8` |
| Symbol file | `pokecrystal11.sym` |
| Symbol-file SHA-256 | `8a8b7a675bbb0e7b2e18d1604ecae68ac18aa0bd8f879cc58351489352bf8ef3` |

The owner's exact ROM SHA-256 is bound only at runtime from the lawful private copy. Its path and
bytes never enter Git. `scripts/check_crystal_transfer_entry_gate.py` passed this boundary without
booting the game, opening a context, running the teacher, or computing a prediction. A checked-in
fixture independently reproduces all 52 allowlisted WRAM/SRAM addresses from the pinned 1.1 symbol
file rather than assuming that revision memory layouts are identical.

## Live progress dashboard

The **Pokémon Learning Observatory** is the human view of the run. It combines the latest rendered
emulator frame with semantic information that already belongs to the observation/evidence layers:

- current stage, location, action and frame counts, and emulation speed;
- party levels, health and status;
- registered, living and level-100 collection counts plus capture/storage headroom;
- all nine goal pressures, availability, selected goal, confidence and authority mode;
- decision, teacher-query and fallback totals;
- zero-shot, adaptation and sealed-test counters; and
- a short evidence event stream.

It is deliberately not a controller. The server binds only to `127.0.0.1`, serves GET endpoints,
rejects POST/PUT/DELETE, and reports zero controller endpoints in its own status. The emulator frame
observer can request rendered pixels but has no button methods. `scripts/run_crystal_dashboard.py`
provides an authenticated no-input preview; the production qualification and collection runners
will publish their real semantic snapshots through the same in-memory observer.

## The 72-context experiment

Every partition covers all nine goal kinds evenly.

| Partition | Contexts | Per goal kind | Label use |
| --- | ---: | ---: | --- |
| Zero-shot probe | 18 | 2 | Never fitted; Red predicts before the first Crystal label |
| Adaptation | 27 | 3 | Nested fixed prefixes of 9, 18, and 27 examples |
| Sealed test | 27 | 3 | Never fitted; opened once after every candidate prediction is committed |

The adaptation order is three complete nine-kind blocks. Therefore the 9-, 18-, and 27-example
prefixes contain exactly one, two, and three examples of every kind. No budget can accidentally
become “nine easy healing examples.” Every policy context must be unique, partitions may have zero
context overlap, each context needs at least two candidates, each partition needs context-dependent
menu reversals, and candidate answer positions must vary.

The execution order is fixed and represented by executable artifact gates:

1. Freeze the 18 zero-shot questions and commit Red's predictions before any Crystal label.
2. Open that probe once, publish every result, and forbid it from selecting schema, architecture,
   normalizer, optimizer, or budget.
3. Collect the 27 adaptation examples in registry order.
4. Reset and fit Red-initialized and zero-initialized candidates at 9, 18, and 27 examples.
5. Commit every candidate's prediction for every sealed test question before the teacher acts.
6. Execute each predeclared candidate/context identity at most once from authenticated paired
   starting state, verify it independently, and preserve failures and interruptions.
7. Score and publish all candidates without optional stopping.

The fitter rejects an adaptation record unless its decision identity, ordered and order-independent
question digests, availability menu, candidate order, selected answer, environment and independent
episode lineage all match the frozen adaptation catalog. This prevents an unrelated but
superficially balanced dataset from entering the correct optimizer.

If the schema or settings change after the zero-shot probe, this experiment is retired and a new
plan with fresh contexts is required.

## Statistical endpoint

The primary comparison is Red-initialized versus scratch at the smallest nine-example budget on all
27 sealed test contexts. It uses a paired two-sided exact test. The preregistered success boundary
requires at least six discordant wins and zero discordant losses for the Red initialization;
`2 × (1/2)^6 = 0.03125`. Missing predictions count as incorrect. The 18- and 27-example comparisons,
zero-shot baselines, calibration, per-kind accuracy, and paired causal outcomes are mandatory
secondary reports, not alternative endpoints to choose after seeing results.

This design answers the sample-efficiency question with the same decisions on both sides. It avoids
the earlier six-example validation defect, where even a perfect result could not beat chance at
`p < 0.05`.

## What happens now that the matching ROM is supplied

1. **Complete:** bind its SHA-256 privately and verify title, size, SHA-1, and revision before
   emulator start.
2. **Complete:** qualify one whole-state banked
   party, Pokédex, inventory and storage bundle plus stable badge, map and control state. The fixed
   clean-power setup reaches the starting bedroom, proves uninitialized storage fails closed, uses
   the real SAVE menu and compares complete reads across 600 no-input frames. The exact-commit
   46-input / 33,276-frame result is preserved in the
   [path-free qualification receipt](evidence/crystal-banked-observation-qualification-2026-08-14.json).
3. Implement the smallest independently verified bindings needed to create genuine multi-need
   contexts. Begin with goal choice, one battle choice, and one local navigation round trip.
4. Materialize all 72 private captures, then freeze a path-free catalog that satisfies the public
   uniqueness, balance, menu-reversal, and candidate-position gates.
5. Run the zero-shot phase before collecting any adaptation label. Do not begin with a full route.

The first Crystal teacher is therefore a bounded context builder and verifier, not a walkthrough
that hands the model an entire answer key. A full completion teacher becomes useful later as a
curriculum generator for story, breeding, version routing, legendary prerequisites, and living-
Pokédex mechanics.

## Claim boundary

A successful primary endpoint would establish that Red initialization improved Crystal goal-choice
sample efficiency under this fixed benchmark. It would not establish autonomous Crystal
completion, battle or navigation transfer, a complete Crystal Pokédex, or a universal Pokémon
player. Those are later gates. A failed endpoint is equally useful: it identifies whether the
failure came from observation, availability masking, ranking, missing binding, execution,
verification, source identity, or external interruption rather than collapsing everything into
“the AI failed.”
