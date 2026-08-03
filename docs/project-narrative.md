# Project Narrative: From a Completed Run to a Transferable Pokémon Agent

> **Living engineering record — updated August 1, 2026.** This document separates verified
> historical results from work on the current robustness branch. It will be updated at each
> collection, training, evaluation, and transfer gate.

## Executive summary

This project asks a harder question than “can software finish Pokémon Red?”:

> Can a system turn one verified solution into reusable game-playing knowledge, remain reliable
> when timing and encounters change, and reduce the amount of teaching required for the next
> Pokémon game?

The project began with a completion-first deterministic teacher. That teacher reached the Hall of
Fame from clean power-on in three uninterrupted runs, each proving 299/299 semantic checkpoints and
36/36 objectives. It established that the route, controller, state adapter, and completion referee
could solve the full game without save-state restoration or human input.

The revised robustness lineage has now independently repeated that result from clean power-on. Its
first qualifying rehearsal reached the same 299/299 checkpoints and 36/36 objectives in 5,163,657
frames and 43,005 controller actions. The different totals reflect the intentionally changed route,
resource plan, recoveries, and battle decisions described below; they do not replace or rewrite the
historical receipt.

That result is the foundation, not the final claim. A deterministic route can still contain hidden
assumptions about random encounters, damage rolls, move-learning prompts, menu state, or collision
tiles. The current phase deliberately changes early decisions and reruns the game from clean power
to expose those assumptions. Each failure is converted into a semantic observation, bounded
recovery rule, transferable feature, or stronger evaluation gate before model training begins.

The intended result is a learned/hybrid agent that understands objectives and bounded skills rather
than memorizing a four-million-frame button sequence.

The long-term target is broader still: a general Pokémon agent that can satisfy a published 100%
completion contract for each supported title. For Red, the stretch contract means registering
every species legitimately obtainable in the cartridge, completing every available evolution,
and training the maximal coexisting living collection to level 100. Impossible solo-ROM requirements such as external
trades and version exclusives remain visible exceptions. This completionist run is a source of
capture, storage, evolution, resource, and grinding demonstrations; it does not replace capped and
randomized evaluations of actual battle competence.

The north star now has four explicit rungs: finish the story, master the transferable skills,
satisfy the title-specific 100% contract, and finally retain every obtainable species at level
100. “Every Pokémon game” is treated as a sequence of supported adapters and measured transfer
experiments—not as a claim that one Red route automatically solves later mechanics, or that expired
events and unavailable network services can be wished away.

### The collection denominator is now explicit

“Catch them all” is ambiguous on one unmodified Red save: version exclusives, trade evolutions,
mutually exclusive starters, fossils, Fighting Dojo gifts, Eevee branches, and event-only Mew
cannot all coexist without external transfer or save branching. The implementation now partitions
all 151 species into **124 obtainable registrations** and **27 named exclusions** for the
qualified Squirtle/Helix/Hitmonlee/Jolteon lineage. Evolving the unique Squirtle, Eevee, and Helix
Fossil specimens consumes Squirtle, Wartortle, Eevee, and Omanyte, so the largest legitimate
simultaneous living collection in that lineage is **120 species**. That makes both denominators
reviewable instead of quietly moving them after a run.

It also distinguishes three facts that are often conflated: a species was registered in the
Pokédex; a specimen is still retained across the party and PC; and that retained specimen has
reached level 100. The emulator adapter can read the owned/seen flags and strictly cross-check the
party plus all twelve boxes. Red keeps the active box in Work RAM and the other boxes across two
checksummed save-RAM banks; the adapter mirrors that design through a narrow read-only port and
never exposes bank numbers or addresses to the planner. A bounded storage specialist can now open
Bill's PC, deposit or withdraw an exact species slot, and prove the resulting party/box transition;
the live route's Zubat deposit uses that specialist. It can now also traverse the multi-page save
warning, initialize storage, switch among all twelve boxes, and prove that the complete collection
was preserved. The 124 registration routes and 120-species retention/training curriculum remain
open. Consequently, living-collection and level-100
qualification remain explicitly unverified. This is infrastructure for the stretch goal, not a
claim that the stretch goal has been completed.

The first uninterrupted clean-power census then completed the same 312-checkpoint Hall-of-Fame
route and measured the gap directly: **12 of 124** targets had historical owned flags, **85** had
been seen, **7 of 120** living targets remained, and **0 of 120** were level 100. Box 1 held the deposited level-7 Zubat;
the other six living specimens formed the final party. All twelve boxes were accounted for, and
the adapter correctly recognized that the save had never performed its first box change. See the
[sanitized collection-census receipt](evidence/qualified-play-collection-census-2026-08-01.json).

The corrected foundation was then replayed from clean power with executable box switching enabled.
It initialized all twelve boxes, deposited Zubat, switched Box 1→2→1 through the game's multi-page
save warning, and proved that no specimen disappeared. Long-form training exposed and repaired
three seed-sensitive assumptions: terminal Selfdestruct during an escort switch, insufficient
headroom in the battle budget, and a wild opponent ending battle while sleep recovery was active.
The final uninterrupted run passed **312/312 checkpoints** and **36/36 objectives**, trained for
**6,493 zero-faint wins**, passed the team gate at levels **88–93**, defeated the Champion, and
entered the Hall of Fame. Its terminal census was **12/124 registered, 7/120 living, and 0/120 at
level 100**, with storage initialized and all boxes verified. The
[sanitized perfect-save foundation receipt](evidence/qualified-play-perfect-save-foundation-2026-08-01.json)
records that result without ROM bytes, save data, or private paths.

The next layer replaces the vague phrase “add 124 routes” with a complete dependency graph. At the
pinned pret/pokered revision, each target now has one canonical ordinary-wild, Safari, fishing,
gift, static, prize, fossil, in-game-trade, or evolution method. The graph contains **102 direct
methods and 22 transformations**. Propagating the 120 living targets backward through consumed
precursors proves that the save needs 120 root specimens from 98 source species—not merely one
capture per Pokédex number—and that those paths register all 124 targets along the way. The same
calculation exposes scarce resources before execution: 3 Moon Stones, 2 Leaf Stones, 3 Water
Stones, 1 Fire Stone, and 1 Thunder Stone.

The first reusable source-survey executor began with a ROM-free Route 1 simulation, then crossed
its first live qualification boundary. From the ordinary story route, the teacher reversibly
crossed Diglett's Cave and Route 2, traversed Route 1 until it caught Pidgey and then Rattata,
verified both Pokédex ownership flags, returned to Vermilion, deposited the exact two party slots,
verified the PC box tail, and resumed Lt. Surge without changing the three-member story roster.
The same uninterrupted clean-power run then passed **312/312 checkpoints**, **36/36 objectives**,
the zero-faint six-member gate at levels **77–82**, and the Hall of Fame in **758,430 actions**.
Its terminal collection was **14/124 registered, 9/120 living, and 0/120 at level 100**. This
qualifies one ordinary-wild source end to end; it does not qualify the remaining source methods or
the complete collection. See the
[sanitized Route 1 acquisition receipt](evidence/qualified-play-route1-acquisition-2026-08-02.json).

That first live slice initially duplicated its capture-selection loop inside the Surge chapter.
It proved the route, but it did not yet prove that the game-neutral source-survey controller could
drive a real cartridge. The chapter now supplies a narrow live adapter instead: global collection
observations come from the Pokédex, the active party, and a checksum-verified census of all twelve
boxes; live enemy identity is translated into the shared species ontology; and the reusable loop
chooses seek, capture, flee, box handling, or stop. A declared requirement order preserves the
qualified Pidgey-then-Rattata lineage without hiding the actual encounter identity. The adapter
also bounds encounter count and route legs and normalizes an early successful stop back to the
Viridian endpoint.

The acquisition graph now emits a route-agnostic priority list that counts missing root specimens,
not just distinct species. That distinction makes Viridian Forest worth six retained specimens:
Caterpie, two Metapod, two Kakuna, and Pikachu. Seafoam Islands 1F also has six globally, but the
chapter planner may combine the neutral ranking with current reachability and resource cost; the
Forest is therefore the next early-game live slice. The refactor reproduced the existing terminal
exactly—**312/312 checkpoints**, **36/36 objectives**, **83,835,201 frames**, and **758,430
actions**—and passed the full private integration test without changing adjacent save artifacts.
See the
[sanitized reusable-source receipt](evidence/qualified-play-reusable-wild-source-2026-08-02.json).

The next live slice reused that same controller in Viridian Forest rather than adding another
chapter-local capture loop. The adapter legally financed a larger early Ball reserve, dismissed
irrelevant encounters, retained Caterpie, two Metapod, two Kakuna, and Pikachu in the dependency
order required by later evolutions, normalized the asymmetric Forest and Viridian return warps,
and deposited the three party-visible collection specimens without losing the duplicates sent
directly to Box 1. Two independent clean-power runs then reproduced **312/312 checkpoints**,
**36/36 objectives**, **83,619,428 frames**, and **765,088 actions** through the Hall of Fame.
The terminal save contains 15 specimens across party and storage, representing **13 distinct
living target species**, with **18/124 registrations** and **0/120 level-100 targets**. This is a
qualified second ordinary-wild source, not the full acquisition curriculum.

Qualification also exposed a different kind of missing bridge: the existing learning command was
intentionally diagnostic-only and rejected preregistered episodes. The formal lane now requires
the exact campaign and rehearsal identities, complete one-shot outcomes for all five train and two
validation roots, and an untouched five-root test partition. It trains only on the train roots,
selects against validation, reports free-choice and forced-choice behavior separately, discloses
visible-state overlap and novel-visible performance, chooses a validation-only confidence
threshold, and writes a canonical private candidate artifact. A weak candidate remains recorded
but cannot be frozen. No such candidate exists yet because the collection campaign has not opened.

The current phase makes one further correction. The qualified route completed the game by
overleveling a single Pokémon, which is a legitimate way to finish Red but a poor thing to imitate:
it hides the battle decisions the agent is supposed to learn, concentrates all risk in one party
member, and does not transfer to another title. The project is therefore moving to a balanced
six-member team with complementary roles and a bounded level spread. The single-carry route is
preserved unchanged as teacher and route evidence.

## The problem

Pokémon Red is a useful long-horizon benchmark because success requires several kinds of reasoning
to work together:

- story and prerequisite planning across eight badges;
- navigation across connected maps;
- dialogue, inventory, party, PC, and shop menus;
- battle decisions under HP, PP, status, accuracy, and opponent variation;
- captures, trades, HMs, field moves, and puzzles;
- resource planning over many hours of gameplay; and
- an independent definition of completion.

A system can appear busy without becoming competent. The predecessor project generated 8.24
million actions and discovered seven milestones, but its frozen evaluation retained no durable
skills. The successor therefore made reliable completion and evidence quality the first
requirements, then placed learning behind explicit reliability gates.

## Phase 1: establish a trustworthy reference solution

The first deliverable was a deterministic teacher that could complete the game legally and prove
what it had accomplished.

The teacher:

- starts from clean emulator power-on;
- uses a privately supplied, fingerprinted ROM;
- sends every input through one frame-safe executor;
- reads validated semantic state rather than changing game memory;
- never restores a save state during a qualifying run;
- verifies objectives as persistent game facts rather than inferred screen text; and
- requires the Champion-defeated event and Hall-of-Fame location concurrently.

Three independent teacher runs reached the same terminal with:

- **299/299 semantic checkpoints**;
- **36/36 completion objectives**;
- **4,796,436 emulated frames**; and
- **41,316 controller actions**.

The public evidence receipt is
[qualified-play-hall-of-fame-2026-07-29.json](evidence/qualified-play-hall-of-fame-2026-07-29.json).
The first private trajectory was separately integrity-audited and summarized in
[private-trajectory-foundation-2026-07-30.json](evidence/private-trajectory-foundation-2026-07-30.json).

### What the completed run gave us

The completed run provided much more than proof that the game was beatable:

- a complete objective graph and legal route;
- 299 useful supervision boundaries;
- action-aligned demonstrations;
- battle, navigation, menu, puzzle, and recovery examples;
- exact resource and party invariants between chapters;
- an independent referee for future learner evaluation; and
- a baseline against which every changed lineage can be compared.

### What it did not prove

The completed run did **not** prove that a learned model could finish the game, that the teacher was
robust to unseen timing, or that knowledge would transfer to another Pokémon title. One successful
lineage can hide brittle assumptions. Those claims require separate training and held-out
evaluation.

## Phase 2: turn brittle assumptions into reusable capabilities

The robustness phase restarts from clean power after every source change and stops at the first
failure. Diagnostic snapshots may be used to qualify a local fix, but a diagnostic restore never
counts as a clean run. The complete source must subsequently replay from power-on without restoring
that state.

Several failures have already produced general improvements:

| Observation from a changed run | Hidden assumption | Resulting improvement |
| --- | --- | --- |
| The Cerulean rival could exhaust the original healing reserve. | One successful battle seed was treated as sufficient. | The legal reserve was raised to 14 Potions and tested across all 256 timing offsets, producing 256/256 wins. |
| Adding the legal Zubat/TM01 route changed later battle timing. | Downstream actions implicitly depended on the original RNG lineage. | Chapter boundaries now verify party, move, item, and control facts after the new legal route. |
| Wartortle learned Bite at level 24. | Generic dialogue handling declined a strategically required move-learning prompt. | The Rocket battle now accepts Bite at its exact level-up boundary and verifies the persistent move set. |
| Correctly learning Bite changed the Rocket and S.S. Anne matchups. | Move choices were tied to old slot contents instead of live species and move evidence. | Policies now use species-specific, PP-checked choices, including a one-use Bite latch against Drowzee and Bite against Kadabra. |
| Changed battle cadence produced wild encounters in several Route 6 segments. | A few traversal segments treated any wild encounter as fatal. | Every Route 6 grass segment now shares a bounded flee routine that proves unchanged PP, party, status, trainer events, and restored control. |
| The old Tackle capture line no longer existed after learning Bite. | Spearow capture was coupled to a historical move set. | Water Gun was live-qualified against a level-15 Spearow: 41 to 2 HP, exactly one PP spent, no damage to Wartortle, and capture with one Ball. |
| The new capture cadence changed Diglett Cave encounters. | One cave-entry delay was assumed to remain stable. | All 256 waits were scanned on the exact new lineage; 153 succeeded. Wait 199 was selected from the widest contiguous passing window, 195–203. |
| A Vermilion Gym can route encountered an unmodeled collision. | The pure shortest path assumed a complete collision map. | Can navigation now discovers blocked tiles, replans from observed coordinates, and derives the final facing direction semantically. |
| Rock Tunnel selected a move whose PP never decreased. | A disabled move still appeared usable to the policy. | The pinned `wPlayerDisabledMove` state is now decoded into disabled slot and remaining turns, recorded in trajectories, represented in the game-neutral battle feature schema, and removed from the model’s legal action mask. |
| Switching to Diglett solved a difficult Rock Tunnel battle but Blastoise later reached Erika one level short of learning Skull Bash. | A locally successful substitution was assumed to preserve the long-horizon experience budget. | The teacher now keeps the required experience on Wartortle/Blastoise, uses bounded field recovery, and verifies that the required level-up move is actually installed rather than merely accepting a dialogue sequence. |
| Adding a Parlyz Heal changed Route 9 timing enough for DUX to faint. | A legal inventory change was assumed not to affect downstream battle RNG. | The purchase is followed by an explicitly qualified timing boundary, while the item itself is a conditional reserve audited as purchased, used, and remaining. The route no longer forces a cure when live status evidence says none is needed. |
| The safer Rock Tunnel lineage retained one additional Super Potion, but Giovanni then defeated a merely healthy—not fully healed—lead. | A fixed HP threshold discarded useful surplus and was too weak for a changed damage lineage. | The additional legal reserve is carried forward and used to restore the lead fully before Giovanni; the complete inventory and economy lineage is verified at every later chapter boundary. |
| The eastbound Route 8 sequence hit newly observed collision coordinates. | A button string encoded one historical path instead of the map's traversability constraints. | The sequence was replaced by a source-derived 60×18 collision model and a semantic planner that excludes undefeated trainers and their sightlines. The new route passed clean-power validation and entered Pokémon Tower. |
| Pokémon Tower consumed more healing than the original lineage. | Later chapters inherited an exact Super Potion count from one run. | Recovery now uses the legal supply adaptively at three verified boundaries, records the reserve transition `(3, 2, 1, 0)`, and checks the resulting economy rather than assuming the old damage rolls. |
| Battles reached Fuchsia and Koga with different legal PP totals, including a disabled Surf that spent no PP. | Exact PP receipts treated one move sequence as the only valid victory. | Chapter contracts now use battle-specific PP bounds while still requiring victory, legal moves, expected story events, party integrity, and bounded resource use. |
| The Safari Zone produced two encounters instead of the historical six. | Encounter count was mistaken for an objective. | The contract now accepts a bounded number of successfully fled encounters and verifies the actual goals: HM03, the Gold Teeth, unchanged party resources, and restored overworld control. |
| The revised experience lineage reached Erika at level 41 without Skull Bash and lost with the boss nearly defeated. | A required move was expected to appear naturally at an old level-up boundary. | The retained Pokémon Tower Rare Candy is now used immediately before Erika, the move-deletion prompt is detected explicitly, Bite is replaced with Skull Bash, and the item, level, and persistent move set are all verified. |
| A moving Saffron NPC swallowed part of a fixed street route, and an attempted detour entered an unintended house. | “Walkable” city tiles were treated as interchangeable even when some are door warps. | Saffron travel now observes every step, replans around live collisions, permanently excludes all unintended door coordinates, and enters the Center or Gym only from a verified outside stance. |
| The Celadon rooftop girl repeatedly moved between approach, facing, and interaction. | A long post-step wait was harmless for static objects but allowed a walking NPC to escape. | Rooftop pursuit now uses short observed steps, rereads the NPC’s live coordinates, faces and interacts immediately, and proves that dialogue opened before handing control to the reward routine. |
| Sabrina used Disable after Strength had already been selected, then Venomoth inflicted a supported status. | PP loss was treated as the only valid selected-turn outcome, and every intermediate turn was expected to be status-free. | The shared runtime now recognizes opponent-first Disable through unchanged PP plus the live disabled slot, replans to a legal move, and permits only explicitly handled sleep/paralysis states while still requiring a fully healed terminal. |
| Sabrina was defeated and awarded the Marsh Badge, but could not transfer TM46. | Winning the battle was treated as sufficient even though the 20-slot bag was full. | The teacher now stores the spent S.S. Ticket and Lift Key in RED's PC before the Gym, proving an 18-slot boundary that reserves space for both TM46 and the following HM02 reward. |
| Route 16 produced a wild encounter on the way to the Fly house. | Only the later Route 21 water route was expected to encounter wild Pokémon. | The Fly-house route now uses the same bounded flee evidence as other stochastic traversal: no trainer battle, unchanged party/PP/inventory, safe HP, and restored field control. |
| The Secret Key interaction began while a late Mansion field message was still settling. | Reaching the correct coordinate was treated as proof that the item prompt was immediately ready. | Item collection now first proves restored field input, establishes the source-pinned approach, and uses a bounded semantic wait for the key to enter the bag. |
| The single Mansion Repel expired before the Secret Key and a wild encounter occurred. | Zero encounters was treated as part of the objective even though the route and inventory remained valid. | The Mansion contract now permits at most two verified wild flees while still requiring every optional trainer untouched, the exact switch trace, preserved party/PP/inventory, and safe HP. |
| The revised experience lineage needed six legal Surf decisions against Giovanni instead of the historical five and finished one level higher. | An exact action count and terminal level were used as proxies for battle correctness. | Giovanni now requires the exact party transition, legal Surf-only decisions, all required trainer receipts, Earth Badge/TM27 mirrors, and a fully healed level-50 terminal without assuming one damage sequence. |
| Lance consumed both helper Pokémon, and field use of Revive stalled in the item submenu. | Selecting an item was treated as equivalent to selecting “USE” and reaching the party menu. | Field recovery now proves each menu transition, revives the selected party member, and verifies both item decrement and living-party evidence before continuing. |
| The revised Elite Four lineage exhausted healing supplies immediately before the Champion. | Winning each battle was optimized locally, without reserving the final recovery needed by the next objective. | Indigo purchasing, battle recovery, helper pivots, and the Lance terminal now form one resource contract; the last Full Restore is reserved in battle and spent only to establish the Champion input boundary. |
| Lorelei could knock out the lead from above the old 80-HP threshold after a legal shop change altered timing. | A historical damage threshold was treated as a general safety guarantee. | Lorelei now uses a higher observed safety margin and earlier bounded recovery, while preserving both helpers for the later fights where sacrifice pivots are budgeted. |
| The original Champion strategy spent six turns raising Special after Surf and Ice Beam had already run out of PP. | A generally useful setup action was selected without checking whether any remaining attack could benefit from it. | The original setup was removed. Later controlled tests separated offense from defense: the current policy uses four X Specials to reduce incoming special damage without paying for all six setup turns, while a separate physical move reserve, full helpers, and healing contract protect and exploit the setup. |
| Take Down supplied late-game PP but recoil converted every successful hit into additional healing demand. | Move power and PP were optimized independently of the shared Elite Four healing budget. | The legal TM plan now reloads Mega Punch and Mega Kick between fights, using replaceable move slots while respecting that Surf and Strength are permanent HMs. |
| Selling one obsolete item at a time was insufficient to finance the final reserve. | The economy helper handled item identity but not legal stack quantities. | Indigo preparation can now sell bounded stacks of obsolete Poké Balls and Max Repels, verifies each quantity transition, and converts unused exploration supplies into healing and move capacity. |
| Agatha can switch between two members of the same species. | Species and level alone were assumed to identify which opposing party member was active. | The observer now records the opponent's party position, allowing switch sequences and repeated species to be reconstructed without relying on presentation order. |
| The newest clean lineage reached Agatha but stalled during a recovery transition at the original one-frame offset. | A locally valid recovery policy still encountered a bad battle/menu timing lineage. | The exact chapter input was scanned across all 255 nonzero byte offsets: 191 completed, and offset 85 was selected from the widest passing window, 80–91. This remains a diagnostic qualification until clean-power replay proves it end to end. |
| Qualifying earlier Elite Four battles repeatedly changed Lance's exact input lineage. | A locally qualified Lance offset was treated as reusable after upstream timing and inventory changed. | Lance is rescanned only from the exact current input through battle, recovery, helper revival, and TM installation. On the newest six-boost lineage, 105 of 255 offsets passed the full-helper terminal. Offset 40 used one Full Restore and the five available Hyper Potions, leaving ten Full Restores, full helpers, and 39 attacks for the Champion. |
| All 255 Champion offsets appeared to exhaust recovery even though a Full Restore remained. | The status branch selected a Full Heal without checking whether one was still in the bag. | Champion recovery now checks live availability and legally falls back to a Full Restore; the apparent economy failure was separated from the underlying inventory-selection bug. |
| Nine Full Restores still could not compensate for only 25 fresh Champion attacks. | Healing reserve was optimized without proving that the final move set had enough accurate PP to defeat six opponents. | The revised purchase plan skips Mega Kick, buys a second Submission TM, and preserves the 16-PP Mega Punch left by the selected Lance lineage. Installing Submission over the exhausted Ice Beam creates 41 Champion attacks, with Submission prioritized against Rhydon. |
| The first clean replay with the revised TM purchases reached Lorelei but exhausted her recovery reserve. | A strategically equivalent shop change was assumed not to alter the first Elite Four battle's RNG lineage. | The run remains a failed rehearsal. From its exact clean-power input, 201 of 255 offsets completed Lorelei. Offset 45 was selected near the center of a passing window and tied for the lowest total recovery use: three Hyper Potions and one Full Restore. |
| Champion recovery pivots entered at half health and could faint before healing the lead. | “Alive” was treated as sufficient evidence that a helper could perform its planned role. | The Lance terminal now requires both revived helpers at full HP. The remaining Hyper Potion and one Full Restore are spent in the field, where healing is safe, so each helper can establish an actual in-battle recovery window. |
| The legal X Special purchase selected the right item and quantity but could not add it to the bag. | Money and item quantity were checked, but the 20-slot unique-item limit was not included in the purchase precondition. | The spent Silph Scope is now archived through RED's PC during the existing Saffron Center stop, creating a verified free slot before late TM and battle-item shopping. |
| The first clean run with the archived Scope and two X Specials passed Lorelei but lost at Bruno's old timing. | The additional legal menu sequence shifted the second Elite Four battle even though its direct inputs remained valid. | From the exact new Bruno input, 201 of 255 offsets passed. Offset 75 was chosen inside a ten-offset passing window and completed without spending any recovery item. |
| The new Lorelei lineage passed but spent nine healing items, leaving too little reserve for the Champion. | A passing chapter was selected before optimizing its effect on the full Elite Four resource horizon. | The exact two–X Special input was rescanned: 198 offsets passed, and offset 218 used only three Hyper Potions and one Full Restore. This saves five healing items relative to the prior passing offset. |
| The resource-efficient Lorelei choice shifted Bruno again. | The previous Bruno qualification belonged to the higher-spend Lorelei lineage. | On the exact new input, 200 of 255 Bruno offsets passed. Offset 185 was the only passing result that consumed no healing item, preserving all twelve Full Restores and eight Hyper Potions for the final three Elite Four battles. |
| Increasing the Champion defense reserve from two to six X Specials shifted Lorelei yet again. | Resource conclusions from the two-item purchase timing were incorrectly assumed to survive the six-item timing. | On the exact six-boost input, 196 of 255 Lorelei offsets passed. Offset 119 used four Hyper Potions and no Full Restores, preserving all 13 Full Restores for the rest of the Elite Four. |
| Ten Full Restores still produced no Champion pass, and several attempts exhausted the bag without advancing. | Damage taken during a healing turn could leave the lead below the threshold, causing another immediate heal and a recovery loop. | Champion recovery now uses the Lance-proven progress latch: after any recovery, the policy must take one legal attack before it may heal again. |
| Champion inputs retained four Strength PP but spent less-accurate Mega Punch first. | Move priority considered remaining PP but not accuracy when two attacks had the same base power. | The final policy now spends 100%-accurate Strength before 85%-accurate Mega Punch, while retaining Submission priority against Rhydon. |
| Delaying X Special setup until Alakazam was tactically appealing but produced widespread item-menu failures during the opponent transition. | A strategy-level timing change crossed an unreliable presentation boundary. | The delayed setup was rejected after 91 of 255 offsets failed in the X Special transition alone. Setup returns to the stable battle-opening boundary while the improved move allocation is retained. |
| The clean run reached species `0x9A`, which was mislabeled as Arcanine in the working narrative. | A local internal species ID was interpreted from memory instead of the pinned species table. | The record now correctly identifies the final Pokémon as Venusaur. Submission is used against Rhydon and Arcanine so limited recoil-free Strength and Mega Punch PP remain available for the flying, Psychic, and final Grass/Poison matchups. |
| Full-health helper pivots were consumed by the first two low-HP events, leaving none for Arcanine or Venusaur. | Recovery treated every battle phase as equally dangerous instead of budgeting scarce safe turns across the opponent party. | Direct Full Restores handle the first four opponents; the two helper sacrifice pivots are now reserved for opponent party positions four and five, where a protected recovery turn has the greatest terminal value. |
| The late-pivot Champion policy was evaluated across all 255 byte-sized start offsets. | The previous policy changes were locally plausible but had no verified Hall-of-Fame terminal. | Offset 150 produced the first passing revised-lineage terminal: four X Specials and three Full Restores used, the lead at 113 HP, one helper at full HP, 16 Submission PP remaining, the Champion event set, and the Hall of Fame entered. It remains diagnostic until clean-power replay confirms all 299 checkpoints. |
| The locally qualified Champion policy was replayed from clean power rather than from its diagnostic boundary. | A passing late-game snapshot could not establish that the complete revised route was reproducible. | The uninterrupted replay passed all 299 checkpoints and 36 objectives, entered the Hall of Fame in 5,163,657 frames and 43,005 actions, and reproduced the same totals on a second clean rehearsal. This closes the revised teacher-completion gate; it does not close the learned-agent or held-out-generalization gates. |
| The first registry-bound, uncounted 63-battle schedule rehearsal changed the Route 25 trainer-5 timing and the lead fainted at checkpoint 49/299. | Reproducibility on the default timing lineage did not imply robustness to the preregistered offset schedule. | The failure was retained as held-out diagnostic evidence. The campaign remains unopened, all twelve declared slots remain pending, and no dry-run qualification exists. Route 25 recovery must be hardened before the schedule rehearsal is attempted again under a newly published source identity. |
| The first uncounted 68-battle rehearsal on the Forest-qualified lineage stopped immediately after the scheduled Cerulean rival at checkpoint 38/312. | A moving Cerulean NPC blocked five westward inputs. The fixed direction string consumed those inputs, turned north from x=13 instead of x=8, and entered a house rather than the Route 24 corridor. | The failed partial remains private diagnostic evidence and consumed no campaign slot. Route 24 entry now observes each coordinate change, retries only unchanged westward steps within a fixed bound, and fails closed on any off-corridor transition. The registry is regenerated and the new exact source must pass clean-power qualification before the rehearsal is retried. |
| The qualified Route 24 repair cleared the former failure under the same 68-battle rehearsal, but the run stopped at checkpoint 109/312 in Rock Tunnel 1F trainer 4. | The lead used resisted BubbleBeam against Bellsprout, then entered a multi-turn Wrap sequence above the ordinary 40-HP in-battle recovery gate; the menu did not return before it fainted with the opponent at 3 HP. | The failed partial remains private diagnostic evidence and consumed no campaign slot. A first 60-HP recovery experiment was rejected when the default lineage spent all nine Super Potions and ended the battle at 13/79 HP. Type-aware Bite removed the resisted Wrap exposure, then revealed Oddish could still put the lead to sleep in trainer 5. The first live DUX pivot won that battle but violated the reserve-survival contract because DUX entered poisoned. Preparing DUX to full health and curing its status passed the complete tunnel, then exposed that the additional recovery left Pokémon Tower one potion short. Instrumentation proved seven Tower potions were spent at real low-HP gates while one was wasted topping 74/89 HP to full after the rival; the current contract raises the post-Lavender reserve from 10 to 11 and replaces that full top-off with a 55-HP safe floor. The exact new source must again pass clean-power qualification before rehearsal. |
| The repaired tunnel and Tower lineage reached Sabrina but spent every remaining Hyper Potion without attacking Alakazam. | The Alakazam-specific 110-HP recovery threshold was above the roughly 60-HP damage taken during the healing turn, so each heal returned the lead to the same below-threshold state and triggered another heal. | Instrumentation identified the repeated 84–101/145 HP states. Sabrina now uses the ordinary 70-HP safe floor for Alakazam and caps recovery by the live reserve as well as the chapter maximum. The next clean replay cleared Sabrina without entering the loop. |
| The Sabrina-hardened replay reached the long six-member Mansion curriculum but rejected a slot-four PP change after one attack was already proven. | The first Fly hypothesis was rejected when excluding DUX's two-turn move reproduced the same failure. The actual missing semantic was a level-up move replacement: the move identity and its PP changed after the attack, which was neither a second attack nor an unexplained PP mutation. | The runtime now recognizes an observed move-identity replacement before applying the unchanged-move PP invariant; an unexplained second PP spend still fails closed. DUX still reserves Fly for field travel and grinds with one-turn Peck and Cut. The combined source completed a clean-power **312/312-checkpoint** Hall-of-Fame replay in **84,632,189 frames**. |
| The newly published source cleared the former Route 24 and Route 25 schedule failures but stopped again at Rock Tunnel 1F trainer 4. | Type-aware Bite removed resisted BubbleBeam, but the scheduled Bellsprout still began Wrap at 20/57 HP and trapped Wartortle until it fainted. Waiting for sleep before pivoting left trapping as an independent loss of control. | The uncounted rehearsal consumed no slot. The revised route prepares DUX before both final Grass-heavy trainers, leads with one-turn super-effective Peck, restores its health/status between them, and returns Wartortle to the lead before the exit. The same lineage collects Safari Zone TM40 for a bounded Skull Bash lesson and prevents duplicate battle-item confirmation. The exact combined source passed **312/312 checkpoints**, **36/36 objectives**, and the Hall of Fame in **762,318 actions**; the Mansion curriculum won **4,236 battles** with a level-77 floor and five-level spread. |
| The next uncounted rehearsal cleared the prior tunnel assignment but fainted DUX while trying to finish a nearly defeated Slowpoke. Subsequent clean-power diagnostics also exposed natural evolution, a moving Celadon NPC, a transformed Ditto, and the Silph rival's Gyarados as hidden assumptions. | A low-HP finisher optimized one battle instead of protecting a reusable party role; several later contracts encoded one historical experience or timing lineage rather than the semantic objective. | The teacher removes the DUX finisher, enforces tunnel potion floors, changes to unresisted Bite after required Slowpoke evidence, and escapes a status-locked DUX to the healthy lead. Natural evolution is accepted, a surplus Rare Candy establishes level 41 without unsafe grinding, movement retries release the controls for NPC traffic, transformed Ditto receives type-aware Strength, and the Silph rival uses Ice Beam plus two bounded whole-battle recoveries. The exact combined source passed **312/312 checkpoints**, **36/36 objectives**, and the Hall of Fame in **762,804 actions** with the six-member curriculum still recording **4,236 battles**, a level-77 floor, and a five-level spread. All failed rehearsals remained uncounted. |
| The following uncounted rehearsal reached Rock Tunnel trainer 5 and correctly escaped a sleeping DUX, but Oddish also slept replacement Blastoise and fainted it. A clean-power diagnostic with an added Awakening then reached the same battle but left Blastoise at party index one, outside the original healing target. | Status recovery, party switching, and HP recovery each worked locally, but the item executors still assumed the active battler was always the first party slot. Buying the contingency too early also changed Route 24 RNG, while buying two in Vermilion exceeded the route budget. | The accepted route buys exactly one extra $200 Awakening in Vermilion, keeps at least one for Tower, targets Awakening and Super Potion at the observed active party index, and caps trainer-5 HP recovery at two uses. Early Cerulean timing remains unchanged and the exact Mart ledger is proven. The source passed **312/312 checkpoints**, **36/36 objectives**, and the Hall of Fame in **771,022 actions**; its six-member curriculum exceeded **4,000 battles**, retained the level-77 floor, and passed the bounded spread contract. The failed rehearsal consumed no slot. |
| The strengthened teacher then cleared all nine Rock Tunnel trainers under the uncounted offset schedule but reached the Lavender restock with only $5,601: enough for eight required Super Potions or the required Parlyz Heal, but $200 short of both. | The extra active-party recovery was behaviorally correct, but its $200 Awakening purchase had not been propagated through the worst-case schedule-specific item economy. | The route now liquidates the unused TM28 for its source-verified $1,000 sale value after Dig capability has already been proven, then restores the full twelve-Super-Potion and one-Parlyz-Heal downstream reserve. TM28 may already be absent when a lower-level Diglett consumed it; that lineage remains explicitly supported. The failed rehearsal consumed no counted slot. |
| The corrected recovery economy carried the uncounted rehearsal through checkpoint 202/312, where Koga Gym Juggler 4 fainted the lead against a still-healthy final opponent. | The battle policy allowed Disable-aware move fallback but still assumed the story lead should absorb every attack; full-party composition was not yet used as a tactical safety resource. | At the observed 50-HP floor, Juggler 4 now pivots to the healthiest living reserve and ranks moves from that active Pokémon's own live move/PP state. The post-battle Center route restores the complete party, so the handoff consumes no scarce item and teaches a transferable party-role concept. The failed rehearsal consumed no counted slot. |
| The reserve handoff advanced the uncounted rehearsal to Sabrina at checkpoint 261/312, where a Hyper Potion action failed its post-item MAIN-menu proof. | The shared battle-item routine allowed only 24 single-frame confirmations for the item text and opponent reply. Under the scheduled timing, MAIN did not reappear inside that window; using CONFIRM also risked re-entering ITEM on the first unobserved MAIN frame. | The primitive now samples for up to 720 single frames using CANCEL, which advances Gen I battle text but is inert on MAIN. It reports the terminal battle state, phase, active HP, and item quantity if the bounded proof still fails. The failed rehearsal consumed no counted slot. |
| The menu-settling repair passed Sabrina and carried the uncounted rehearsal beyond 1,250 balanced-team battles before a Mansion fighter exposed no usable preferred move. | The pre-encounter planner had observed a safe PP reserve, but a long live battle can consume that reserve or Disable its final legal training attack before the next field decision. The move selector could report only failure, not the higher-level need to disengage. | Exhaustion and Disable now raise a semantic training-recovery signal. The Red adapter switches to its safe Blastoise escort when necessary, flees with a zero-faint proof, and returns control to the game-neutral team planner so it can rotate or schedule a Center trip. This preserves one-turn species-specific attack curricula instead of silently substituting field Fly or a status move. The failed rehearsal consumed no counted slot. |
| The PP-hardened rehearsal completed all **312/312 checkpoints**, defeated the Champion, and entered the Hall of Fame, but the private episode was not promoted after 8,943 instrumentation rejections. | The game controller was complete; the data contract was not. Wild training entered the shared battle runtime without a portable `BattleIntent`, so 4,646 move labels and 4,282 lifecycle callbacks were rejected. Fifteen repeated training-progress reports also reused one event ID. | The retained failed artifact proves the writer persisted about **848,000 records / 506 MB** and that storage loss was not the cause. Every production wild battle now carries an explicit training objective and bounded-recovery policy, externally fled encounters close their physical battle identity, and progress identities include the execution step. The private episode limit now covers the declared 7,000-battle envelope. No collection slot was consumed; exact-source rehearsal remains the promotion gate. |
| The first lossless-label repair again completed **312/312 checkpoints** and Hall of Fame, accepted 4,789 move decisions plus every lifecycle and progress event, but rejected 209 early switch-training labels. | During safe participation training, the field lead was a weak trainee while Blastoise was the active battler. The teacher selected a valid Blastoise move, but the portable snapshot still exposed the field lead's species, HP, status, moves, and PP, so label validation correctly rejected the mismatch. | In battle, the semantic `party.lead` view now means the currently controlled battler; outside battle it remains the field lead. A regression test proves a switched active battler's selected move, species, level, HP, status, and PP are recorded together. The retained 512.6 MB failed artifact consumed no slot, and all later direct-training decisions in that run had already recorded successfully. |
| The next source-bound rehearsal cleared every repaired schedule branch, balanced all six members, defeated both final Gym Leaders, and crossed Victory Road before stopping at checkpoint 296/312 with zero Poké Balls. | Indigo cleanup encoded the older route's assumption that at least one of at most eight balls would remain. The completionist capture reserve is now thirty, and the bounded live curriculum legally consumed the entire stack; calling a positive-quantity sale helper was an implementation detail, not a gameplay requirement. | The terminal contract now accepts every bounded remainder from zero through thirty, skips the sale only when the stack is empty, and still proves the exact Full Restore, Full Heal, Revive, Hyper Potion, and X Special reserves afterward. The private failed artifact remains uncounted, and the corrected exact source must requalify before collection begins. |
| The zero-remainder replay passed the corrected range gate but the first Indigo purchase selected item `0x2e` instead of Full Restore. | The old path always sold at least one Poké Ball. Finishing that sale left the controller inside SELL, where CANCEL returned to BUY/SELL; skipping the sale left the controller on the field, so the same CANCEL opened an unrelated menu and made the following cursor selection meaningless. | Indigo now chooses its entry action from the proven branch state: INTERACT opens the clerk from field control when zero balls remain, while CANCEL exits a completed positive sale. Both paths then normalize the clerk cursor to BUY and retain exact item and quantity verification. The failed replay consumed no slot. |
| After the corrected source qualified **312/312**, **36/36**, Hall of Fame, and **68/68** schedule offsets, v2 train slot 01 reached the Rocket thief and Drowzee fainted Wartortle at 0/66 HP while retaining 24/50 HP. | The policy treated the early item economy as three isolated minimum reserves and used weak Water Gun after exactly one Bite. It stored a seventeenth-Potion supply down to four even though an unseen damage lineage needed one recovery before Route 6. | The immutable v2 failure remains in its denominator and v2 is retired. The next teacher retains five Potions for Route 24, four for Route 25, conditionally spends one from three at the Rocket's live low-HP MAIN gate, and preserves the original two for Route 6 and one for the S.S. Anne. After proving one fresh Bite, it ranks live legal Mega Punch, Bite, and Water Gun rather than forcing weak cleanup. Fresh v3 seeds and a new dry rehearsal prevent rerunning the exposed outcome. |
| The first uncounted v3 rehearsal reached the Nugget Rocket at checkpoint 44 with Wartortle at 2/56 HP; Ekans trapped and fainted it before the post-battle recovery could run. | The route had enough Potions and an immediate Center visit after victory, but scheduled the field Potion on the unreachable side of the battle. Inventory planning was correct while action ordering was not. | The same exact Route 24 Potion is now spent before triggering the Rocket, leaving the unchanged four-Potion handoff for Route 25. The failed rehearsal remains uncounted, all twelve v3 slots remain untouched, and the exact repaired source must repeat the complete qualification. |
| The next v3 rehearsal cleared the Nugget Rocket and survived the original checkpoint-62 Rocket-thief fight without spending its emergency Potion, then failed the teacher's exact-one-use assertion. | Recovery had been improved from absent to available, but its verification confused a maximum safety allowance with a mandatory action. Forcing a heal in every lineage would teach wasteful item use. | Rocket recovery is now conditional on the live low-HP gate. Unused Potions carry forward as a bounded surplus instead of being spent to recreate one historical inventory count. The rehearsal remains uncounted and v3 remains unopened. |
| The following replay proved both Rocket repairs through checkpoint 69, then won the first Route 6 trainer without needing its reserved Potion and hit an identical mandatory-use assertion. | The same historical-lineage assumption had been duplicated at the next recovery boundary. A safe victory was again being rejected because an allowance was modeled as an obligation. | Route 6 now uses the same conditional-recovery abstraction and preserves every unused allowance for later objectives while protecting a one-Potion minimum. The failed rehearsal remains uncounted. |
| That repair cleared Route 6 and reached the S.S. Anne rival at checkpoint 79, where one Potion was insufficient and Ivysaur fainted the lead with 38/57 HP remaining. | Normalizing every boundary down to its historical minimum discarded a legal surplus that the harder schedule needed later. The teacher was still optimizing each chapter locally instead of carrying resources across objectives. | Surplus Potions now flow from Rocket to Route 6 to S.S. Anne. The rival can spend multiple Potions only when the live low-HP gate recurs, and every recovery resumes the same battle intent. This is reusable resource conservation rather than another mandatory-use script. |
| The surplus-preserving replay cleared the S.S. Anne rival and Surge, then reached Rock Tunnel B1F trainer 5 at checkpoint 109. After DUX became status-locked, Wartortle used resisted BubbleBeam against Bulbasaur, exhausted two recoveries, and fainted with the opponent at 12/55 HP. | The role pivot was correct, but the post-pivot type policy recognized later Bellsprout/Oddish families as Grass matchups while omitting Bulbasaur. Recovery was masking repeated poor move selection. | Bulbasaur is now part of the shared Grass-matchup set, so a replacement story lead ranks neutral Bite after DUX's required participation instead of resisted Water damage. The private rehearsal remains uncounted and the correction improves type-aware transfer rather than increasing a retry cap. |
| The type-aware replay survived Bulbasaur but reached Rock Tunnel B1F trainer 4 still paralyzed. Wartortle selected BubbleBeam, lost the turn to paralysis, and the final opponent self-destructed; the trainer event was complete but required-move PP remained unchanged. | Winning and teaching evidence diverged. A stochastic self-KO can complete the physical battle before an attempted curriculum action executes, so event-only success is insufficient for an imitation label contract. | The route cures supported status before the self-destructing Hiker sequence and buys a second Parlyz Heal so the later Grass contingency remains protected. This preserves an executable evidence move rather than weakening the PP contract or changing the schedule. |
| The status-cured replay cleared Rock Tunnel, Rocket Hideout, and Pokémon Tower, then exhausted ten Great Balls plus every surviving Poké Ball while attempting the one-time Route 12 Snorlax at checkpoint 174. | The capture budget still treated balls left from unrelated earlier searches as part of a guaranteed-encounter reserve. Completion reliability should not depend on luck already spent on Spearow, Diglett, or Pikachu. | The Lavender restock now buys twenty-five Great Balls under a thirty-three-throw total bound and sells the remainder after capture. This is a reusable static-encounter resource rule and directly supports the eventual Pokédex-completion objective. |
| The first thirty-Great-Ball restock attempt stopped safely in Lavender Mart with ₽16,897 available against a ₽19,400 capture-plus-healing bill. | A reliable reserve must also be funded; increasing quantities without propagating the live economy simply moves the failure to the shop. | The funded reserve is twenty-five Great Balls plus both Super Potions for ₽16,400. It exceeds the prior 18-throw exhaustion without selling future-use TMs, reducing recovery, or depending on earlier ball leftovers. |
| The newest PP-hardened lineage defeated Agatha and Lance, then reached the Champion at checkpoint 299/300 but fell to the level-65 Venusaur after exhausting Blizzard. | Late-game tactics were compensating for a strategic level deficit. Experience had been treated as a side effect of the route rather than a planned, reusable resource. | A game-neutral training policy now chooses when to seek an encounter, fight, flee, return to heal, and stop. Its first Red adapter uses the Pokémon Mansion's level 28–39 encounters, Cinnabar healing, and Dig-based recovery to train the lead to level 55 before the final gyms. The adapter is bounded by battle, step, healing-trip, HP, status, PP, and enemy-level rules and emits a training receipt. |
| A required attack was disabled during a held-out trainer battle even though other legal attacks remained. | The teacher confused “preferred” with “required on every turn.” | Battle policies now rank legal fallback moves from live PP and Disable state, while the post-battle contract separately proves that the strategically required move was used at least once. |
| A legally captured level-15 Spearow survived the capture contract but produced an underpowered DUX after the in-game trade. | Capture success alone did not prove fitness for a Pokémon's later assigned role. | The capture planner now accepts the level-17 encounter needed by the downstream battle plan, turning party acquisition into a long-horizon capability contract. |
| A level-up prompt in the Rocket Hideout threatened to replace Bite with Withdraw. | Generic prompt handling could silently destroy a later required capability. | Move-learning decisions now preserve the declared move set and verify it after the battle instead of assuming every level-up prompt should be accepted or declined identically. |
| The Tower rival needed different attacks against Pidgeotto, Growlithe, and the rest of the party, plus bounded recovery on the changed damage lineage. | One preferred move and one historical healing point were insufficient for a multi-opponent battle. | The rival policy now chooses from live opponent identity, legal move state, HP, and inventory, and can spend a tightly bounded recovery reserve before proving its terminal contract. |
| Pokémon Tower 6F put the lead to sleep and attacked through seven sleeping turns. | HP-only recovery could not solve loss of control caused by status. | A legal Awakening is now purchased as a conditional contingency and the battle runtime can distinguish status recovery from healing. This fix is still undergoing clean-power validation. |

### Current schedule-hardening work

The working branch has since replayed the same declared dry-run offsets in an in-memory diagnostic
that does not consume an official collection slot. That work is intentionally not presented as a
new qualification: the source is still changing, the registry still identifies the last published
commit, and the official failed rehearsal remains the public result until a clean, committed
replacement passes.

The diagnostic has nevertheless advanced from Route 25 through Koga, the Safari Zone, Strength,
and the Saffron shopping boundary. Its current frontier is the Celadon rooftop reward interaction
that supplies Ice Beam before Silph Co. This work has exposed several useful
causal links:

- Route 25 now chooses attacks from the opposing trainer's party rather than using one historical
  slot everywhere. A single legally purchased Antidote provides conditional field recovery when
  the held-out lineage produces poison; if no poison is present, the item is not consumed.
- The S.S. Anne rival policy now ranks legal fallback attacks when Disable removes its preferred
  move, using the observed disabled slot rather than failing on an otherwise winnable state.
- Capture planning now accounts for downstream responsibilities. The Spearow chosen for the DUX
  trade must be strong enough for its later required battles, and the Diglett acceptance window is
  being evaluated against its actual Surge role rather than one historical encounter level.
- DUX's Route 9 demonstration now uses bounded in-battle recovery under live HP evidence. The next
  Route 9 battle selects BubbleBeam because the held-out opponent disabled Bite.
- Rock Tunnel and the Rocket Hideout now pass the diagnostic schedule with adaptive legal moves,
  retained resource evidence, and protection against an unwanted level-up move replacement.
- The Rock Tunnel lineage can consume a different number of healing items without invalidating the
  rest of the route. Lavender now performs a legal adaptive refill to a declared reserve, and later
  chapters prove item conservation and minimum supply rather than inheriting one exact historical
  count.
- Pokémon Tower's rival and Channeler battles now pass with opponent-aware attacks, bounded
  recovery, and status-aware item use. The trace also corrected a Generation I decoding error:
  status bit `0x40` means paralysis, while sleep is encoded by the low three bits. The runtime now
  chooses Parlyz Heal or Awakening from the actual status and proves a one-item decrement.
- Koga can disable Surf before it is used. The policy now ranks legal moves from live PP and Disable
  state instead of repeatedly selecting the preferred slot, while the chapter contract separately
  proves victory, badge progress, and a fully healed party.
- Several exact companion-HP tuples were artifacts of one damage lineage. Koga and Strength now use
  semantic terminal gates—all required party members present, alive, status-free, and fully healed—
  so harmless battle variation no longer masquerades as failure.
- Saffron's moving pedestrians can invalidate a fixed walk string. The Mart approach now observes
  the player's coordinates and replans around live collisions before proving the intended door
  entry.
- The 20-slot bag made an individually legal purchase sequence globally impossible. Silph
  preparation now acquires, exchanges, and teaches the temporary Fresh Water/TM13 items before
  purchasing the Hyper Potion stack; an unnecessary Max Repel was also removed. This turns bag
  capacity and subgoal ordering into explicit planning constraints.
- The current failure is not a battle or route failure but interception of a randomly walking
  rooftop NPC. The ongoing fix uses observed player/NPC coordinates and bounded pursuit rather than
  assuming the NPC remains on the tile where she was first seen. It will not be called stable until
  the complete held-out lineage passes from power-on.

These changes remain **diagnostic work in progress**. They will be simplified, covered by the full
ROM-free suite, replayed on the default lineage, committed and pushed, bound into a regenerated
registry, and then subjected to the official uncounted schedule rehearsal. Only that final
rehearsal can reopen the collection gate.

This process is intentionally slower than patching a single run with a save-state restore. It
produces a better teacher, more useful correction data, and a stronger model interface.

## Phase 3: from a single carry to a balanced team

### Why the completed route is the wrong thing to imitate

The qualified route finishes the game, twice, across 301 checkpoints. It does so by training one
Pokémon far beyond everything it meets: the lead entered the Mansion block at level 46, left at 55,
reached Indigo at 58, and entered the Hall of Fame at 61 while the rest of the party stayed small
enough to be irrelevant. Every recorded battle decision was therefore made from a position where
almost any legal move wins.

That is excellent *route* evidence and it remains in the repository unchanged. It is poor
*teaching* evidence, for three reasons:

1. **It hides the decision the agent needs to learn.** When one member outclasses the field,
   matchup selection, switching, and type reasoning stop mattering. A behavior-cloning dataset
   collected from that route mostly teaches "attack with the strongest move," because that label
   was almost always correct.
2. **It makes progress depend on a single point of failure.** The first held-out rehearsal stopped
   at Route 25 checkpoint 49/299 precisely because changed battle timing let the lead faint. A
   route with one carry has no depth to absorb that variance; a balanced party does.
3. **It does not transfer.** "Overlevel the starter" is a Red-specific exploit of a specific level
   curve. "Keep six complementary members within a few levels of each other" is a strategy a
   player would carry into any mainline title, which is exactly the kind of knowledge
   [Milestone 6](roadmap.md) needs.

The single-carry route was never a stated design goal. It was the cheapest way to satisfy a
completion contract that only measured *whether* the game ended, and it is being replaced now
because the project has moved from proving completion to producing transferable training data.

### The target policy

The agent should acquire and retain a full six-member party with complementary roles, train every
final member past the level-50 floor before the Elite Four (the current Mansion specialist targets
level 55), prefer training whoever is furthest behind, and hold the party within a five-level
spread at major training boundaries. Temporary
deviations are permitted when progression genuinely requires them, but each one must be recorded
with its reason rather than silently weakening the rule.

### Reusable concepts, not Red coordinates

The new layer is deliberately split so the policy can outlive Pokémon Red:

- `party.py` is the **game-neutral observation contract**. It describes party membership, species,
  active-party position, level, health, status condition, moves and remaining power points, and
  experience, plus the derived team metrics a planner actually reasons over: minimum and maximum
  level, level spread, average level, fainted count, incomplete-party state, and the weakest
  *trainable* member. It contains no addresses, coordinates, or revision-specific identifiers.
- `team_training.py` is the **reusable balanced-training policy**. It decides whether to recruit,
  restore, switch, train, or stop; selects a safe grinding area from encounter level bands; accepts
  or rejects a matchup; and emits a portable readiness receipt. Its rules are expressed in levels,
  roles, and health—never in map tiles.
- `red_party.py` is the **only Red-specific piece**. It projects the game's 44-byte party structure
  into the neutral contract and binds each role to a species.

The declared roster binds six species to six species-neutral roles:

| Role | Species | Status in the current route |
| --- | --- | --- |
| Lead attacker | Blastoise | Already the starter lineage |
| Speed control | Dugtrio | Evolves from the Diglett the Vermilion chapter already captures |
| Field utility | DUX (Farfetch'd) | Already obtained by the Vermilion trade |
| Special sweeper | Jolteon | **Acquired and evolved** through the Celadon gift/stone route |
| Bulky absorber | Snorlax | **Caught and retained** through the Hall of Fame |
| Physical sweeper | Hitmonlee | **Acquired** after defeating all five Fighting Dojo trainers |

No slot is a substitution, so no slot carries a substitution reason. The roster type rejects any
future substitution that does not record why it was made, so a roster change cannot enter the
repository unexplained.

### Empirical confirmation from the first clean-power run on this branch

Running the qualified route from clean power-on against the supported ROM produced two findings
that were not visible from the code alone.

**Route 21 was tied to one encounter sequence.** The crossing failed at step 26 of 91 with
"Route 21 blocked". The corridor was not obstructed. A surfing encounter can consume a movement
step without advancing the player, and the traversal treated any non-advancing step as a blocked
tile, so it only succeeded when the encounters fell exactly where the original recording saw them.
The chapter's other mover already retried each step up to eight times; Route 21 did not. Giving it
the same bounded retry makes the traversal depend on the corridor rather than on the encounters,
and the run then proceeds. This is a small fix, but it is the exact failure shape the project
exists to remove: a fixed sequence standing in for a decision.

**The single carry then lost the Champion.** With Route 21 crossed, the same run reached the final
battle and lost it. The receipt is unambiguous: the lead fought every one of the Champion's six
Pokémon (`party_position` 0 through 5), exhausted its third move to zero PP, and fainted to the
last one at `hp=0/197` while the rest of the party sat at 26 and 18 HP. Two members were never
viable contributors; they were carried.

That is the single-carry design failing on its own terms, in the place it was always going to
fail. It also explains why this route can pass on one RNG trajectory and lose on another: a lead
that must win six consecutive fights on a finite PP budget has no margin, so a different damage
roll changes the outcome. A balanced six-member party is not a stylistic preference here—it is the
mechanism that turns a marginal, RNG-sensitive win into a repeatable one, which is precisely what
held-out evaluation across unseen timing schedules will require.

### What this phase does *not* yet claim

This increment adds observation, metrics, policy, and adapter with unit coverage. It does not add
the acquisition chapters the roster implies, it has not run under the emulator, and it has not
produced any trajectory. The three unacquired members and the Route 12 catch-instead-of-defeat
change are route work that must follow, and the current 301-checkpoint route remains the qualified
teacher until a balanced-team route independently replaces it.

## What is being built

The repository contains three related products, with deliberately different evidence standards:

1. **A completion referee and semantic game interface.** These turn emulator state into durable
   facts such as badges, inventory, party condition, opponent state, map position, and objective
   completion.
2. **A robust deterministic teacher.** This supplies legal demonstrations, correction examples,
   chapter contracts, and a known-good recovery path. It is training infrastructure, not the
   learned-agent claim.
3. **A learned/hybrid agent.** This will select objectives and bounded skills from semantic state,
   first in Red and then behind a small adapter in a second Pokémon game.

This distinction matters: improving the teacher increases the quality and diversity of the
dataset, but only a frozen model completing held-out runs will count as learned-agent completion.

## Learning architecture

The system separates long-horizon planning from bounded execution:

1. A semantic state adapter translates revision-specific RAM into validated facts.
2. An objective graph tracks story prerequisites and durable progress.
3. A router selects a bounded navigation, interaction, battle, inventory, puzzle, or recovery
   skill.
4. A frame-safe executor owns controller input.
5. A recorder stores semantic observations, decisions, outcomes, and teacher corrections.
6. An independent referee determines whether completion actually occurred.

The model is not asked to rediscover controller timing from raw frames. It chooses meaningful
macro-actions under explicit constraints, while deterministic infrastructure handles exact input
delivery and verifies effects.

### Current learned component

The first slot-equivariant battle ranker reached 72.5% teacher-choice agreement against a 50.5%
fold-local majority baseline across 422 recorded decisions. Its legality and PP mask prevents
invalid outputs by construction. This is a diagnostic from one teacher lineage, not a full learned
gameplay rollout. See
[private-battle-imitation-diagnostic-2026-07-30.json](evidence/private-battle-imitation-diagnostic-2026-07-30.json).

The battle feature schema is deliberately game-neutral. Candidate moves are represented by
mechanics such as power, accuracy, category, type, STAB, effectiveness, PP, status effects, stage
interactions, and whether the move is currently disabled. Route names, local move IDs, and fixed
slot positions are excluded from the transferable vector.

## Evaluation discipline

The project keeps several claims separate:

- **Teacher completion:** deterministic expert reaches the Hall of Fame.
- **Hybrid completion:** one or more learned specialists operate inside teacher scaffolding.
- **Learned-module evaluation:** a frozen specialist passes its own held-out suite.
- **Learned-stack completion:** frozen learned specialists compose across the full game.
- **Transfer evaluation:** a model trained on Red improves learning efficiency on another game.

Official evaluation uses frozen source, configuration, partitions, and model weights. Training,
validation, test, and dry-run schedules are declared before collection. Failed attempts remain in
the denominator; diagnostic snapshot probes do not silently become clean-run evidence.

The next collection gate is:

1. one uninterrupted rehearsal of the finalized teacher;
2. regeneration and verification of the source-bound collection registry;
3. five clean training trajectories;
4. two held-out validation trajectories;
5. frozen model training; and
6. held-out full-game evaluation.

## Transfer to other Pokémon games

The goal is not to author another complete route for every title.

Knowledge expected to transfer includes:

- battle mechanics and legal-action masking;
- type, status, PP, healing, and party-resource reasoning;
- menu and dialogue skills;
- exploration and collision-aware navigation;
- objective prerequisites and persistent-event verification; and
- recovery from unexpected encounters, damage, status, and displaced positions.

Another game still needs a small adapter that maps its local memory and mechanics into the shared
ontology. A game such as Pokémon Silver also introduces new maps, objectives, Pokémon, and
mechanics, so reliable zero-shot completion from Red alone is not assumed.

The planned transfer experiment is:

1. run the frozen Red-trained specialists on the target game without target-game training;
2. measure which skills transfer and where they abstain or fail;
3. provide targeted demonstrations and teacher corrections only for missing knowledge;
4. fine-tune under a frozen target-game validation split; and
5. compare the amount of target-game data and intervention with the original Red effort.

Success means each new game requires less hand-authored scaffolding—not that one Red trajectory
magically contains Silver’s story.

## What worked

- Completion-first design created a reliable source of demonstrations and corrections.
- Semantic checkpoints made long failures local and diagnosable.
- Clean-power replay exposed assumptions that snapshot-only testing would miss.
- Source-pinned RAM observations turned vague screen behavior into testable facts.
- Hard legality masks prevented the learned battle ranker from emitting impossible actions.
- A private/public evidence split preserved reproducibility without redistributing copyrighted
  game data.
- Failure-first iteration produced reusable recovery behavior rather than a growing list of timing
  hacks.
- Treating the Elite Four as one continuous resource-planning problem exposed solutions that
  per-battle optimization missed.
- Exact diagnostic snapshots made it practical to test bounded timing variation locally, while
  clean-power replay remained the only accepted end-to-end proof.

## What did not work

- Millions of unguided actions did not create cumulative competence in the predecessor.
- One deterministic lineage did not establish robustness.
- Fixed move slots broke when a legal level-up changed Wartortle’s move set.
- Exact encounter counts broke when earlier battles consumed RNG differently.
- Assuming a complete collision map broke on a legitimate Gym path.
- Treating PP as the only move-legality signal failed when Disable left PP intact.
- Treating a battle substitution as resource-neutral failed because experience is a long-horizon
  resource just like HP, PP, money, and inventory.
- Treating successful menu actions as timing-neutral failed because their frames can change every
  downstream damage, status, and encounter outcome.
- Continuing to press confirmation after an unexpected TM result could consume another item; TM
  teaching now fails closed as soon as the intended item disappears.
- Spending setup turns without checking the remaining attacking PP failed at the Champion.
- Using recoil moves to solve a PP shortage merely moved the shortage into the healing budget.

## Current status and honest limitations

The active lineage now combines the complete story route, a six-member balanced curriculum,
checksum-verified storage, the Red-only perfect-save contract, and two live ordinary-wild
collection sources. It begins from clean power, restores no save state, keeps all six story
members alive, verifies all **312 semantic checkpoints** and **36 objectives**, defeats the
Champion, and enters the Hall of Fame.

The newest route catches Pidgey and Rattata on Route 1, then retains Caterpie, two Metapod, two
Kakuna, and Pikachu in Viridian Forest. Two independent runs reproduced **83,619,428 frames** and
**765,088 actions** exactly. The terminal contract reads **18/124 registered**, **13/120 distinct
living**, and **0/120 level 100**, with nine specimens in Box 1 and the six-member story party
intact. The duplicate Metapod and Kakuna roots are physically retained without inflating the
distinct-species count.

The formal learner now requires complete one-shot outcomes for all five train and two validation
roots under the exact campaign identity. It fits only training, selects on validation, leaves all
five test roots unopened, and publishes a private canonical candidate with legality, baseline,
cross-entropy, free/forced-choice, visible-overlap, novel-visible, and confidence evidence. It has
not executed because the 68/68 rehearsal is still pending. Rehearsal failures at Route 24 and Rock
Tunnel remained uncounted and exposed moving-NPC, trapping, healing-budget, type-matchup, and
reserve-survival assumptions. The current combined repair passed a clean-power **312/312**,
**36/36** Hall-of-Fame qualification in **771,022 actions** with the six-member level-77 curriculum
intact. The campaign remains unopened and all twelve collection slots remain unconsumed. No
learned model has completed the game.

### Historical qualification snapshots

The paragraphs below preserve the order in which earlier lineages were qualified. Statements such
as “current branch” describe their milestone at that time; the synopsis above is authoritative.

The historical deterministic teacher completion remains verified. The current robustness branch
has also completed an uninterrupted clean-power replay with **299/299 checkpoints**, **36/36
objectives**, **5,163,657 frames**, and **43,005 controller actions**. A second clean rehearsal
reproduced those exact totals. Both runs used the complete revised route: archived obsolete
inventory, rebalanced Elite Four purchases, live opponent-party identity, resource-aware
recoveries, full-health helper pivots, four X Specials, and a physically usable Champion move
reserve. Diagnostic states were used while developing and qualifying local fixes, but neither
qualifying completion restored one.

The revised teacher has passed broad source validation, and its source-bound collection registry
was committed and pushed as source commit `58c3dbd`. The first uncounted schedule rehearsal stopped
at Route 25 trainer 5 (checkpoint 49/299) after the changed battle timing caused the lead to faint.
The private status audit confirms `campaign_started=false`, no dry-run qualification, and all
twelve declared slots still pending. Uncommitted diagnostic work has since advanced the same
schedule to Pokémon Tower, but that progress is not counted as a qualifying run. The next task is
to finish hardening the full held-out schedule, pass both default and declared clean-power
rehearsals, republish a source-bound registry, and only then open collection.

No learned model has yet completed the game. Collection, frozen training, held-out Red evaluation,
and the first cross-game transfer experiment remain subsequent gates.

The current working branch adds one semantic checkpoint for the bounded Mansion training block.
Two uninterrupted clean-power replays reproduced **301/301 checkpoints**, **36/36 objectives**,
**6,581,531 frames**, and **54,261 actions**. In both runs the lead trained from level 46 to 55
through 115 wild wins, 1,862 encounter steps, five healing trips, and zero faints; it reached
Indigo at level 58 and entered the Hall of Fame at level 61. The final terminal retained all three
party members alive. This proves the new deterministic-teacher lineage and the reusable training
adapter; it does not prove that a learned policy can choose the target, area, or recovery cycle.

The balanced-team layer described in Phase 3 is now implemented as an observation contract, derived
team metrics, a reusable training policy, a bounded capture policy, and a Red party adapter, all
covered by ROM-free unit tests. None of that layer has been called from the route yet, and no
balanced-team route exists.

The protected-party guard no longer blocks one: it was exact tuple equality, which forbade the
party ever growing. That was an artifact of the single-carry route rather than a safety property,
and it now matches on the leading members instead, so a lost, reordered, or substituted core still
fails while the open slots become recruitable.

The first clean-power balanced-team lineage reached the Hall of Fame with three members. The next
qualified lineage adds a semantic Route 12 capture planner, catches Snorlax in five throws, and
then completes all **301/301 checkpoints** and **36/36 completion objectives** with four members.
Before Blaine, the teacher trains the whole active party until every member is at least level 50,
the largest level gap is no more than five, nobody is fainted, and every battle, step, and healing
trip remains bounded. A lean six-Full-Restore League reserve was sufficient through the Champion
and left 3,814 money. This qualifies the deterministic teacher and reusable training/capture
mechanisms; it is not yet the target six-member curriculum or a learned-policy completion claim.

The next qualified lineage added Eevee through Celadon Mansion's rear entrance, purchased and
consumed a Thunder Stone, and retained Jolteon as the fifth member. It established the first
five-member balanced result and exposed the remaining roster gap.

The current lineage closes that gap with a source-pinned Fighting Dojo chapter. It defeats each
Blackbelt and the Karate Master, records their exact identities and parties, chooses Hitmonlee,
heals all six members, and proves physical field control before continuing. Its uninterrupted
clean-power run passes **312/312 checkpoints** and **36/36 objectives**. The zero-faint Mansion
block uses semantic matchup, HP, damaging-PP, recovery, move-learning, and party-order gates; it
qualifies after **5,445 wild wins** and **529 healing trips**, with all six members between levels
82 and 87. The complete teacher run executes **516,338 actions** before entering the Hall of Fame.
This qualifies the six-member deterministic curriculum, not a learned-policy rollout.

The full learned-system and transfer claims remain pending. In particular:

- the current battle ranker has not completed the game;
- the required five training and two validation trajectories have not yet been collected on the
  finalized source;
- held-out full-game completion has not yet been demonstrated;
- cross-game transfer has not yet been measured;
- no learned policy has yet reproduced the teacher's full-game completion or demonstrated transfer
  to another Pokémon title.

These limitations are part of the public project record rather than hidden behind the completed
teacher result.

## Engineering and portfolio takeaways

This project demonstrates:

- long-horizon system decomposition;
- emulator integration and deterministic control;
- semantic state modeling from a pinned external codebase;
- graph-based planning and collision-aware navigation;
- closed-loop verification and fail-closed safety;
- dataset contracts, integrity manifests, and leakage-resistant partitions;
- behavioral cloning, legality-constrained ranking, and correction-driven training;
- reproducible evaluation design; and
- honest separation of baseline, hybrid, learned, and transfer claims.

A concise interview description is:

> I built a completion-first Pokémon Red system that reaches the Hall of Fame through 312 verified
> semantic checkpoints with a balanced six-member party, then turned replay failures into reusable
> navigation, capture, storage, recovery, and experience-training skills. It now measures a
> 124-registration/120-living completion contract, records integrity-checked private
> demonstrations, and keeps train, validation, and test roots sealed before fitting
> legality-constrained specialists. The next experiment measures whether those game-neutral skills
> reduce how much teaching a second Pokémon title needs.

## Related documentation

- [Architecture](architecture.md)
- [Roadmap](roadmap.md)
- [Teaching and Data Plan](teaching-plan.md)
- [Battle Learning](battle-learning.md)
- [Transfer Learning](transfer-learning.md)
- [Collection Protocol](collection-protocol.md)
- [Completion Contract](completion-contract.md)
- [Assistance Policy](assistance-policy.md)
