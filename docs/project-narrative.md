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
| The fresh v4 rehearsal cleared the repaired Route 24 accuracy, poison, Rocket sleep, and Route 6 branches, then lost the S.S. Anne rival with Ivysaur at only 3/57 HP after its sole retained Potion. | Conditional carry-forward was correct, but the minimum end-to-end budget still covered only one recovery; a shifted damage lineage could legally require two. | Cerulean now buys one additional Potion and preserves it through every downstream boundary. S.S. Anne receives a two-Potion minimum and may spend either only at the existing live low-HP gate, strengthening resource planning without scripting a mandatory heal. The failed rehearsal remains private and uncounted. |
| The two-Potion replay defeated the S.S. Anne rival, cleared Surge, and reached Rock Tunnel before rejecting lead status `0x05`. | The field recovery recognized poison and paralysis but omitted Gen I's low-three-bit sleep counter, even though battle recovery already handled the same representation. | Every sleep counter from one through seven now selects the carried Awakening at the stable field boundary and increments the exact resource ledger. Seven regression cases prevent the representation gap from returning; the failed rehearsal remains private and uncounted. |
| The sleep-aware replay reached final Rock Tunnel trainer 4, where DUX reduced Bellsprout to 3/57 HP, was paralyzed, and then fainted during repeated Wrap despite entering at full health. | Type-based role assignment kept returning Grass opponents to DUX even after status made that specialist unsafe; a local matchup preference overrode the broader party-preservation objective. | Both final Grass trainers now enable status protection. A status-triggered escape latches DUX unavailable for that battle, allowing the healthy story lead to finish with its neutral attack instead of switching back into the impaired specialist. This teaches persistent role reassignment under control loss rather than relying on a favorable Wrap duration. |
| The role-pivot replay defeated every Rock Tunnel trainer and healed in Lavender, then failed the chapter ledger with zero Awakenings remaining. | DUX was put to sleep twice. The teacher spent the first Awakening immediately during battle even though healthy Wartortle could safely take over, leaving the second field cure to consume the protected Pokémon Tower reserve. | Status recovery now selects a healthy party pivot before spending a scarce item; Awakening remains the fallback only when no living reserve can take the role. A regression test proves that priority and the exact Lavender reserve contract remains unchanged. |
| The reserve-preserving replay won final Rock Tunnel trainer 5 but rejected the result because DUX's required Peck PP was unchanged. | The type-aware role planner immediately assigned the opening non-Grass opponent to Wartortle, allowing battle completion before the specialist produced its promised executable teaching action. | The final-tunnel planner now latches an observed DUX PP decrement before enabling matchup pivots. It still pivots after the lesson or under an unavoidable status emergency, but it cannot label a physical victory as curriculum evidence when the declared move never occurred. |
| The evidence-gated replay passed all eleven Lavender trainer lessons, seven safe wild escapes, the complete party and healing contract, and every route gate, but arrived with zero Awakenings after two legitimate uses. | The reserve was still sized for a one-use lineage. The exact diagnostic showed ₽1,761 remained after eighteen Super Potions and all other restocks, so the missing contingency was affordable rather than an economy conflict. | The route now carries a three-Awakening total reserve. The contract still permits at most two uses and requires at least one remaining for Pokémon Tower; the additional ₽200 is propagated instead of relaxing the downstream requirement. |
| Combining the second Awakening into the original quantity selector left ₽591 after the Repel charge but failed to expose the four Repels in the bag, stopping at the Mart proof. | Altering a previously qualified multi-item settlement changed the menu/dialogue lineage immediately before another quantity purchase. The total budget was sufficient; transaction sequencing, not money, was the failure. | The Mart keeps the original one-Awakening, Parlyz-Heal, and four-Repel sequence intact, proves the Repels, then buys the additional Awakening as a separate one-item top-up. Each inventory target is independently verified while the same ₽200 budget increase remains exact. |
| The split sequence proved all four Repels, but the final same-Mart Awakening top-up again charged ₽200 without settling the existing stack. | Repeating the same item purchase later in the open shop session remained an unstable menu lineage even after the intervening transactions were individually proven. | The additional copy moves to the earlier Cerulean purchase. Cerulean now carries two Awakenings forward, while Vermilion reuses its already-qualified single-Awakening, two-Parlyz-Heal, four-Repel sequence to reach the unchanged three-item Tunnel reserve. |
| The two-copy Cerulean attempt stopped at the first Mart with the second Awakening absent. | That purchase occurs before the rival, Nugget Bridge, and its ₽5,000 reward, so the route had no honest source for the extra ₽200 yet. | The original pre-rival purchase stays unchanged. After defeating the Nugget Rocket, the normal Center recovery makes a separate one-item Mart visit funded by the earned reward, then replays Route 24. This preserves both the early battle economy and Vermilion's qualified transaction sequence while still carrying three Awakenings into the Tunnel. |
| The funded repeat visit reached checkpoint 45/312, returned to the Cerulean Mart, and failed before selecting Awakening. | Gen I retained the clerk's prior BUY/SELL cursor across visits, while the original helper assumed a fresh BUY selection. The item-list navigator was therefore acting on the wrong menu. | Repeat visits now read and normalize the live clerk cursor to BUY before entering the item list. The failed run remains private and uncounted; the purchase quantity, earned funding, and downstream reserve are unchanged. |
| Cursor normalization alone reproduced the repeat-visit failure; the diagnostic trace remained at menu index zero for all twelve movement attempts and reported a non-shop item register. | The repeat clerk interaction needed one more dialogue acknowledgement before BUY became actionable. Movement was being sent to dialogue, not to either a clerk or inventory cursor. | The repeat-only helper now acknowledges that additional live dialogue frame before navigating the item list. Its bounded trace remains in failure messages so any future menu drift reports the exact observed state. |
| The richer trace reached a two-choice quantity/prompt geometry instead of the seven-item Cerulean inventory. | Nugget Bridge awards a Nugget item, not cash. Treating the ₽5,000 sale value as immediate money sent the unfunded purchase into a rejection prompt and made later input meaningless. | The post-Bridge visit now proves one earned Nugget, sells it for exactly ₽5,000, restores field control, reopens BUY, and purchases one Awakening. Vermilion conditionally skips its old Nugget sale while preserving the identical final purchase-cost ledger. |
| The first sale replay reached the clerk with the Nugget but did not move the cursor to SELL. | The new helper reused the purchase path's interaction action, while every already-qualified Mart sale in the teacher initiates the clerk with the general confirm action before moving the two-choice cursor. | The Cerulean sale now reuses that proven controller sequence exactly; it still verifies SELL, the selected Nugget, the ₽5,000 proceeds, and restored field control independently. |
| Reusing the single-confirm sale action still left Cerulean's cursor at BUY. | This earlier clerk retained one additional greeting acknowledgement before exposing the same two-choice menu used by the later qualified Mart. | The bounded Cerulean branch advances that remaining zero-index dialogue state once, then requires the cursor to move to SELL before any inventory action can occur. |
| The additional acknowledgement also failed, while the private trajectory showed every A, Down, and wait produced an identical state hash. | The repeat Mart's moving NPC blocked both upward route steps. The unchecked direction string then walked left from the doorway to `(0,7)` instead of reaching the clerk stance at `(1,5)`; every apparent menu observation was stale RAM read while facing empty space. | The repeat visit now takes the clear left-first corridor, requires the exact `(1,5)` clerk stance and live field control, and only then runs the already-qualified one-confirm SELL sequence. This coordinate proof removes the false dialogue theory and prevents any future shop action from executing at the wrong tile. |
| The first coordinate-gated detour correctly rejected `(1,7)` instead of emitting shop actions. | The official map data shows the customer blocks the direct `(3,6)` column, while the clerk is served across the counter from `(2,5)`; `(1,5)` is counter collision, not a legal stance. | The repeat route now detours through the unobstructed right column—right, up, up, left, left—and pins `(2,5)` before facing the clerk. The gate and source-derived route replace both unchecked movement and guessed interaction coordinates. |
| The source-derived approach then sold the Nugget and bought the Awakening, but the persistent return gate found the player still inside the Mart. | The same moving customer occupied the old rightward exit lane from `(2,5)`. The unchecked shared return string lost those steps and walked into the west wall. | The repeat visit now exits through the clear lower aisle—down, down, right, door—before rejoining the qualified exterior route to the Center. The sale, purchase, and two-Awakening inventory proofs all passed before this movement-only correction. |
| The corrected Mart route and reserve passed through Bill and checkpoint 55, where Goldeen's Supersonic left Wartortle confused at 5 opposing HP; repeated self-hits reduced 47 HP to zero while the fixed Mega Punch controller kept selecting the same intent. | The mandatory Gym lesson had no recovery policy because the earlier lineage ended before confusion became dangerous. The downstream four-Potion minimum left no unallocated item to survive a shifted status lineage. | The funded top-up now includes one additional Potion. Route 25 hands five to the Gym; the trainer controller retains Mega Punch evidence, spends at most one Potion at a live 30-HP MAIN gate, and normalizes any unused item as legal post-battle recovery. Both branches restore the exact four-Potion Rocket reserve, teaching bounded contingency use without borrowing from later objectives. |
| The bounded Gym controller defeated the trainer and restored full HP, then the route immediately missed the Center. | The new controller already consumed all victory dialogue and proved stable field control before applying its unused Potion. The legacy fixed-battle cleanup confirmations therefore opened an overworld menu, and the following direction string never moved the player. | The obsolete cleanup pulses are removed from this semantic controller path. Its stable-field and exact inventory proof is now the sole handoff to the verified Gym exit route. |
| The corrected v4 replay passed Misty, the Rocket route, the S.S. Anne, and the Diglett setup through checkpoint 91, then spent its remaining six Poké Balls on one full-health level-6 Kakuna. | The reusable area controller allowed one unlucky wild encounter to consume every ball remaining after the earlier Spearow, Diglett, Route 1, and Caterpie captures. A campaign-wide reserve did not imply a safe per-encounter budget. | Wild-source capture now spends at most five balls on one specimen. If that bounded attempt fails, it verifies the exact ball decrement, flees, and lets the semantic source survey seek a fresh encounter without claiming collection progress. The failed artifact remains private and uncounted; the exact source still requires a complete clean-power rehearsal. |
| The bounded-retry replay returned to checkpoint 91 and preserved capture accounting, then exhausted the Forest's 64 survey legs while seeking fresh specimens after failed attempts. | The physical search bound had been calibrated for one encounter per capture target; adding legal encounter retries increased the number of corridor traversals without increasing the separate 1,000-encounter or 20,000-action safety bounds. | The Forest traversal budget is raised to 256 finite legs under those unchanged semantic bounds. This propagates retry capacity through the search layer while retaining a hard terminal limit and exact collection-progress checks. |
| The expanded traversal replay reached the independent 20,000-action ceiling with Caterpie retained but no balls left for the remaining Forest roots. | Per-encounter retry prevented one target from monopolizing the reserve, but full-health throws still consumed the same finite resource across multiple fresh encounters. Search capacity could not repair an inefficient capture action. | The Red adapter now invokes the game-neutral weaken-before-throw policy. It selects a healthy low-level Rattata, Caterpie, or Pidgey with usable Tackle/Gust, switches through verified battle menus, spends exactly one move PP, requires real target damage, and then uses the five-throw encounter budget. A knockout is treated as a fresh-source retry with no false collection progress; zero balls now fail immediately. |
| The first weakening replay reached Route 1 and rejected the new action before opening the party menu. | The semantic area planner can request capture while wild-introduction dialogue is still settling, while the weakening adapter required MAIN at method entry. The existing battle navigator already handles that state transition. | Weakening now first preserves encounter identity and party composition, uses bounded dialogue normalization to reach PARTY-selected MAIN, and only then applies the strict switch-and-damage gate. No menu action runs unless the same species, HP, and party survive normalization. |
| The normalized replay reached stable wild MAIN and then rejected navigation to PARTY. | The shared navigator had previously needed only FIGHT, ITEM, and RUN, so PARTY had no declared transition map. | PARTY now has an explicit bounded path from every main-command position: right from FIGHT, up from RUN, and ITEM first normalizes through FIGHT. The general navigator can therefore support capture-helper switching without raw cursor assumptions. |
| The PARTY-capable replay successfully weakened repeated Metapod and Kakuna targets, reducing 18 HP to 16 with one verified Rattata Tackle, then stalled after a failed Pikachu throw when the 1-HP helper fainted. | Weakening used the correct low-power battler, but left that fragile battler active for the ball sequence; every failed throw grants the wild target another attack. | Wild capture now switches back to the healthy story lead immediately after proving target damage and before opening the bag. The reusable switch helper preserves species and target HP in both directions, while the low-level member supplies only the transferable weakening lesson rather than tanking the capture. |
| The protected-lead replay continued through more Forest captures, then a faster Pikachu knocked out Rattata before Tackle executed: target HP stayed 15 and no PP was spent. | Returning the helper after a successful hit protected the throw sequence, but the adapter still treated every helper faint as an invariant failure rather than a normal forced-switch branch. | Forced-switch recovery now recognizes the live party cursor, selects the healthy lead, and preserves species and target HP. If the move landed first, capture continues; if PP and target HP prove it never executed, the lead performs a bounded flee and the source survey seeks a fresh specimen without claiming progress. |
| The first forced-switch replay detected a cursor immediately after the knockout but never restored MAIN. | Gen I left the just-closed move cursor address populated while the faint dialogue was still active, so address validity alone accepted stale menu state and confirmed too early. | Forced-switch recovery must advance at least one bounded faint-dialogue transition before accepting the live cursor. It then retains the cursor-address, tile, party-range, species, and target-HP checks. |
| Requiring one attempted transition still accepted the same stale cursor because the first confirm left the entire semantic snapshot unchanged. | Elapsed input attempts are not proof of UI progress; the cursor address itself remained the move-menu address. | The adapter records the pre-faint cursor pointer and refuses party selection until the live pointer changes to a different valid cursor tile. This converts the transition gate from timing evidence to observed UI-state evidence. |
| Cursor-transition validation still could not restore MAIN after faster Pikachu knocked out the low-level helper; every bounded input left the semantic snapshot unchanged. | The upstream decision was unsafe: passive Metapod and Kakuna are suitable weakening targets, but Pikachu can outspeed and defeat an early helper before it acts. | The Red adapter classifies Pikachu as a direct-throw target behind the durable lead. Passive Forest roots still exercise verified weaken-then-throw behavior, while the threatening target uses its high catch rate and the same five-throw budget without sacrificing a party member. Forced-switch handling remains fail-closed contingency code rather than the planned path. |
| The surplus-preserving replay cleared the S.S. Anne rival and Surge, then reached Rock Tunnel B1F trainer 5 at checkpoint 109. After DUX became status-locked, Wartortle used resisted BubbleBeam against Bulbasaur, exhausted two recoveries, and fainted with the opponent at 12/55 HP. | The role pivot was correct, but the post-pivot type policy recognized later Bellsprout/Oddish families as Grass matchups while omitting Bulbasaur. Recovery was masking repeated poor move selection. | Bulbasaur is now part of the shared Grass-matchup set, so a replacement story lead ranks neutral Bite after DUX's required participation instead of resisted Water damage. The private rehearsal remains uncounted and the correction improves type-aware transfer rather than increasing a retry cap. |
| The next exact replay proved the Forest retry curriculum and surplus Poké Ball sale through checkpoint 103, then reached Rock Tunnel trainer 5 at checkpoint 109. DUX correctly escaped after paralysis, but the replacement Wartortle was also paralyzed and fainted after lost turns with the opponent at 9 HP. | The status policy could cure sleep on the replacement but treated paralysis only as a post-battle field condition. The already-funded second Parlyz Heal therefore could not protect the live role handoff it was purchased to support. | The in-battle status adapter now recognizes paralysis independently from sleep, consumes at most the surplus Parlyz Heal at a verified main-menu gate, proves the exact cure and item decrement, and preserves one cure for the subsequent tunnel evidence battle. The rehearsal remains private and uncounted. |
| The paralysis-cured replay cleared Rock Tunnel and every subsequent chapter through checkpoint 271, then entered Cinnabar with 15 occupied bag slots instead of the qualified 16–19-slot capacity range. | Selling every early Poké Ball funded Tunnel supplies but removed the harmless unique-item slot that the Mansion route later uses to prove a full-bag delayed TM reward. Adding an unrelated purchase at Cinnabar would create a new economy and inventory branch. | Vermilion now sells the exact early surplus while retaining one Poké Ball. That single capacity token also remains legal Snorlax backup, survives the Great Ball cleanup, and is sold by the existing Indigo normalization. The ₽1,400 proceeds still fund all four Repels on the observed 15-ball remainder. The failed rehearsal remains uncounted. |
| Retaining the capacity token changed the exact downstream timing and reached Rocket Hideout Giovanni at checkpoint 136 before the protected recovery failed through DUX. | The shared recovery primitive defaulted to the historical weak-reserve lesson: after absorbing the item turn, the helper kept attacking until it fainted or hit a long bound. That is inconsistent with the balanced-party curriculum and can also defeat the opponent before restoring the lead. | Giovanni now uses the primitive's preservation mode: a surviving helper absorbs one reply, the Super Potion decrement is proved, and the lead is restored immediately. The policy then requires an attack before considering another recovery and retains the original finite item reserve. The private failure remains uncounted. |
| The preserved-helper replay defeated Giovanni, cleared Pokémon Tower, and reached the Snorlax restock at checkpoint 172 with ₽97 after buying 25 Great Balls and one of two Super Potions. | Retaining the capacity ball cost ₽100, while the prior Lavender top-up had blindly bought one Parlyz Heal even when both fixed-reserve cures survived Rock Tunnel. The route was simultaneously preserving an unused ₽200 item surplus and reporting a later ₽100 cash shortfall. | Lavender now restores a fixed two-Parlyz-Heal reserve: it buys only the exact number consumed in Rock Tunnel and proves the resulting inventory/economy ledger. A no-cure schedule saves ₽200, while a cure schedule replenishes the spent unit. The capacity token and both later Super Potions remain funded. The failed rehearsal remains uncounted. |
| The fixed-reserve replay reached the same restock with ₽297 after buying 25 Great Balls and one Super Potion, still ₽403 short of the second recovery item. | The new capacity token is itself a valid Snorlax throw, but the restock still purchased the older 25-Great-Ball reserve as though no Poké Ball survived. The combined reserve had silently grown from 25 to 26 while cash was scarce. | The static-encounter budget is now 24 Great Balls plus the retained Poké Ball: the same 25 legal throws as the qualified reserve, still seven beyond the historical 18-throw exhaustion. This saves ₽600 and funds both Super Potions without reducing capture depth. The failed rehearsal remains uncounted. |
| The combined-reserve replay funded both recovery items, caught Snorlax in three throws, and reached the Silph rival at checkpoint 243. After the two-item recovery budget was correctly exhausted, Venusaur fainted the lead with 38/120 HP remaining. | Forced-switch handling existed only inside the loop that could still spend a healing item. Once that separate budget ended, the final battle runner reverted to a single-active-member assumption despite several living teammates. | Recovery count and party depth are now independent bounds. The teacher still spends at most two Hyper Potions, but after exhaustion it may select up to the same four living reserves through the verified forced-switch path and rank their legal moves. This teaches party continuity rather than increasing the healing allowance. The failure remains private and uncounted. |
| The repaired v4 dry run then completed 312/312 checkpoints, 36/36 objectives, the Hall of Fame, and the 68/68 schedule audit. Its first one-shot training seed stopped at checkpoint 43 when Wartortle fainted during Route 24 trainer 1. | The bridge curriculum healed before trainers 3 and 2, but assumed the final trainer was safe on whatever HP survived the accuracy/poison battle. The counted offset schedule disproved that assumption. | The failed v4 slot is retained permanently and v4 cannot supply five complete training roots. The teacher now performs a verified, resource-neutral Center recovery before the final bridge trainer, using the same bounded backtrack/return primitive already proven earlier on the bridge. A fresh registry and full dry qualification are required; the counted failure is not rerun. |
| V5 froze disjoint seeds and began its uncounted qualification, where the new timing schedule left the Cerulean rival's Pidgeotto at 6 HP after Wartortle exhausted its protected Potion allowance and fainted at checkpoint 37. | The teacher already carried a living Zubat helper for its accuracy-reset lesson, but the rival controller treated that helper as temporary and had no forced-switch continuation after lead loss. Resource conservation and party continuity were incorrectly coupled. | The rival keeps the exact Potion reserve for Route 24, but a lead KO now invokes one bounded, observed forced switch to the living helper and selects a legal active-battler move from live move/PP evidence. This adds no healing or retry allowance and teaches the same full-party continuity used later at Silph. The uncounted v5 qualification must restart on the republished source. |
| The helper-continuation replay reached the same 6-HP Pidgeotto, selected Zubat, and proved one legal reserve attack, but Zubat also fainted. | The lead had exhausted as many as twelve Potions because each enemy reply could leave it below the recovery threshold and immediately trigger another heal. The controller never required an attack between recoveries, so more party depth could not repair the unchanged battle state. | Cerulean rival recovery now latches one mandatory legal attack after every Potion before another heal can be considered. The fixed reserve, HP gate, exact item accounting, accuracy reset, and helper contingency remain unchanged. This removes an unproductive healing loop rather than raising any resource bound. |
| The progress-latched v5 replay defeated the Cerulean rival, all five Route 24 trainers, Misty, and reached the Rocket thief at checkpoint 62 before Drowzee's Sing recovery stopped with one sleep turn remaining. | The shared runtime gave the entire sleep condition one 48-pulse transition budget even though Gen I represents as many as seven distinct suppressed turns. The live counter had decreased correctly, but earlier dialogue and menu transitions consumed the allowance before the final turn. | The recovery allowance now scales only from the observed three-bit sleep-turn counter. Every pulse remains bounded, every sleeping turn must preserve the complete PP vector, the counter may never increase, and a living battler is still required. A regression covers a long Sing sequence that exceeds the former global allowance while making semantic progress. The qualification remains private and uncounted. |
| The sleep-scaled v5 replay cleared the former failure, Route 6, the S.S. Anne, and the capture/trade setup before exhausting all thirty Poké Balls in the Forest collection lesson after checkpoint 91. | The game-neutral policy requested weakening until an HP threshold, but the Red adapter executed at most one weakening attack and then threw regardless of the updated ratio. A single low-level Tackle often removed only two or three HP; Metapod and Kakuna therefore consumed bounded five-ball attempts while still near full health. | The adapter now replans after every verified damage action. Passive cocoon targets receive a deeper 50% threshold under an eight-attack maximum; Caterpie retains the lighter 85% threshold, and dangerous Pikachu remains a direct-throw target behind the durable lead. Each attack still requires exact PP loss and live target damage, and every encounter and throw remains bounded. The qualification is private and uncounted. |
| The first deep-weakening replay reached the Forest and reduced a passive Kakuna from 22 HP toward its target range, but the one-action verifier eventually reported that the attack did not settle. | After a completed hit, Gen I could expose the previously selected MOVE menu before returning to MAIN. The verifier treated every non-MAIN phase as dialogue and confirmed it, issuing another unintended attack; multiple PP decrements then correctly failed the exact-one-action contract. | A returned MOVE phase now receives CANCEL, while only UNKNOWN dialogue receives bounded confirmation. The outer semantic policy alone may request the next weakening action after observing the new HP ratio. A regression pins the phase-to-action distinction; the failed qualification remains private and uncounted. |
| The cancel-aware replay again reached Kakuna; Tackle spent exactly one PP but missed, leaving the target at 22/22 HP. MAIN returned correctly, yet the verifier waited for damage until its finite settling bound expired. | The one-action contract distinguished a damaging hit from pending dialogue but omitted a completed miss. PP loss plus stable MAIN is terminal evidence that the selected turn executed even when HP is unchanged. | The verifier now classifies that exact boundary as a miss, restores the protected lead, flees, and lets the area policy seek a fresh required encounter. It neither labels damage nor retries invisibly inside the same action. Regression cases distinguish a hit, a miss, and a still-pending MOVE phase. The qualification remains private and uncounted. |
| The miss-aware replay completed the Forest collection, defeated Surge, and reached checkpoint 102 before the Rock Tunnel Mart could not fund four Repels: only five of thirty Poké Balls survived, leaving ₽591 after the protected healing/status purchases. | The supply plan depended on selling a favorable surplus while the capture lesson still direct-threw at Pikachu and stopped most weakening at 65–85% HP. Valid capture variance could therefore consume the money indirectly without violating any per-encounter throw bound. | The adapter now treats Pikachu as a high-risk weaken-and-throw target rather than a direct throw: only helpers above 75% HP may participate, and the verified forced-switch/flee path prevents a failed action from sacrificing the party. Ordinary targets use a 65% threshold and passive Metapod/Kakuna use 30%, while exact PP/damage and eight-attack limits remain. Healing, status, and Repel reserves are not reduced to hide the economy failure. The qualification remains private and uncounted. |
| The high-risk capture replay funded Rock Tunnel, cleared all nine trainers, Rocket Hideout, and Pokémon Tower, then reached the Snorlax restock at checkpoint 172. After buying the 24-Great-Ball reserve, the shop remained on Great Ball and an attempted Super Potion purchase bought a 25th ball; even without that extra purchase, the live budget was ₽779 short of both recoveries. | The route had preserved an unused TM34 Bide solely as a later one-slot Cinnabar capacity token, while requiring capture luck to fund a completion-oriented static-encounter reserve. The purchase adapter also chained two products without re-establishing a product-list boundary. | Lavender now sells the unused TM34 for its exact ₽1,000 proceeds before Snorlax supplies and reopens BUY from a verified field boundary between product stacks. Cinnabar replaces the missing unique slot with one Great Ball, then sells that replacement after Blaine to preserve the delayed TM38 inventory lesson. The money proof accounts for the ₽1,300 buy/sell difference; the 24 Great Balls, retained Poké Ball, and two Super Potions are unchanged. The qualification remains private and uncounted. |
| The Bide-funded replay bought the correct Snorlax reserve, caught Snorlax in five throws, completed Safari, Koga, Erika, and reached Saffron at checkpoint 239 before Silph capacity cleanup rejected the boundary. | Exact follow-up diagnostics proved the bag had only fourteen occupied slots and the Helix Fossil was already absent. Capacity was safe, but the teacher incorrectly required a fixed obsolete-item checklist even when no cleanup was needed. | Capacity cleanup now proves the actual sixteen-slot bound first, performs no PC transaction when the bag is already safe, and otherwise deposits only enough available obsolete route items to reach the bound. The qualification remains private and uncounted. |
| The type-aware replay survived Bulbasaur but reached Rock Tunnel B1F trainer 4 still paralyzed. Wartortle selected BubbleBeam, lost the turn to paralysis, and the final opponent self-destructed; the trainer event was complete but required-move PP remained unchanged. | Winning and teaching evidence diverged. A stochastic self-KO can complete the physical battle before an attempted curriculum action executes, so event-only success is insufficient for an imitation label contract. | The route cures supported status before the self-destructing Hiker sequence and buys a second Parlyz Heal so the later Grass contingency remains protected. This preserves an executable evidence move rather than weakening the PP contract or changing the schedule. |
| The status-cured replay cleared Rock Tunnel, Rocket Hideout, and Pokémon Tower, then exhausted ten Great Balls plus every surviving Poké Ball while attempting the one-time Route 12 Snorlax at checkpoint 174. | The capture budget still treated balls left from unrelated earlier searches as part of a guaranteed-encounter reserve. Completion reliability should not depend on luck already spent on Spearow, Diglett, or Pikachu. | The Lavender restock establishes a 25-throw combined reserve under a thirty-three-throw controller bound and sells the temporary remainder after capture. This is a reusable static-encounter resource rule and directly supports the eventual Pokédex-completion objective. |
| The first thirty-Great-Ball restock attempt stopped safely in Lavender Mart with ₽16,897 available against a ₽19,400 capture-plus-healing bill. | A reliable reserve must also be funded; increasing quantities without propagating the live economy simply moves the failure to the shop. | The funded reserve is twenty-five Great Balls plus both Super Potions for ₽16,400. It exceeds the prior 18-throw exhaustion without selling future-use TMs, reducing recovery, or depending on earlier ball leftovers. |
| The funded replay caught Snorlax in six throws, cleared Koga, and reached the Celadon Gym trainers before a wandering Pokémon Center NPC occupied the first exit tile beyond eight bounded waits. | The controller already released movement between attempts, but its observation window covered only part of this NPC cycle. The route and target tile were valid. | The same game-neutral release, wait, and observe primitive now allows sixteen bounded attempts. It remains fail-closed on map or coordinate drift while covering the longer observed NPC cycle. |
| Replaying with sixteen waits reached the identical Center tile and the NPC remained parked for the entire window. | Waiting directly above this NPC was not a reliable progress action; increasing the same bound again would encode hope rather than a semantic alternative. | The second Center exit now follows the legal left-side corridor around the occupied tile and rejoins the same doorway below it. The route remains observable and collision-checked without depending on NPC timing. |
| The left-side Center detour failed immediately, and an exact right-side replay failed at the same coordinate. | Both apparent side routes were structural walls, while the redundant post-rooftop nurse visit placed the teacher back above the occupied one-tile aisle. No battles or hazards occur between the already-proven heal and the rooftop TM exchange. | The TM exchange now preserves and verifies the healed party, returns only to the Center entrance, and exits directly through the adjacent door. This removes an unnecessary second nurse interaction instead of guessing around an impossible corridor. The exact source must still requalify end to end before collection. |
| The entrance-return replay cleared Erika, assembled the six-member party, and reached Sabrina at checkpoint 261 before rejecting a Hyper Potion recovery even though the diagnostic reread showed the main battle phase. | The bounded loop sampled before each cancel pulse but did not accept a transition caused by its final pulse. The verifier therefore contradicted its own terminal observation. | Battle-item recovery now performs one authoritative post-action observation at the bound and accepts it only when the trainer battle and main-menu semantics are both present. Item decrement remains independently required, so the repair closes an observation-boundary race without weakening consumption evidence. |
| With the observation race repaired, the exact Sabrina schedule consumed all seven Hyper Potions without advancing out of its low-HP loop. | One X Special left Blastoise taking enough damage after each heal to fall immediately below the same recovery threshold. Repeating recovery could not improve the state, even though a second stage of Special defense was already available from the same Celadon shop stack. | The shared purchase now reserves one X Special for the Silph rival and two for Sabrina. Sabrina proves both exactly-once setup consumptions before attacking; the second stage reduces incoming special damage and teaches staged defensive setup instead of adding more healing retries. |
| V3 qualified **312/312 checkpoints**, **36/36 objectives**, Hall of Fame, and **68/68** schedule attestations, but immutable train slot 01 failed at Route 24 trainer 2 with the opponent at 4 HP. | Pidgey lowered Wartortle's accuracy; Nidoran poisoned it; three consecutive Water Gun misses then let poison and enemy attacks reduce the 24-HP lead to zero. The fixed controller had no live recovery gate inside this unscheduled bridge battle. | The v3 result remains permanently failed and v3 is retired. V4 promotes the exposed v3 seed to its uncounted rehearsal, preregisters twelve fresh counted seeds, heals at the Center immediately before the accuracy battle, and may spend one already-budgeted Potion at a live low-HP MAIN boundary. If that Potion is spent, a post-bridge Center visit replaces the old field heal; otherwise the old field Potion remains. Both branches prove the same four-Potion handoff before the Nugget Rocket. |
| The first uncounted v4 rehearsal survived the exposed accuracy/poison sequence but exhausted the local bridge completion loop after using its Potion. | The item helper correctly returned to a stable trainer MAIN menu with the cursor still on ITEM. The bridge loop inherited the older fixed controller's assumption that the cursor always remained on FIGHT, so repeated confirmations reopened ITEM instead of selecting the next move. | Stable MAIN states now re-enter the semantic move selector, which normalizes any main-command cursor to FIGHT, selects Water Gun, and proves its PP decrement before continuing. Unknown dialogue states remain bounded confirmations. The failed rehearsal consumed no slot and the exact v4 source must requalify. |
| The next v4 rehearsal passed both repaired bridge trainers, then fainted while walking back to the Center. | The in-battle Potion preserved the planned four-Potion handoff, but Wartortle left trainer 1 poisoned. Field poison applied during the long recovery walk before the nurse could be reached. | The existing semantic field-Antidote routine is now map-parameterized and runs at the stable Route 24 boundary before any movement. It consumes one of the two already-budgeted Antidotes only when live status proves poison, leaving the downstream Potion economy unchanged and the second Antidote available for Route 25. |
| The poison-safe v4 replay cleared both Routes 24 and 25, Misty, and reached the Rocket thief before Drowzee's sleep exhausted the bounded recovery loop at checkpoint 62. | The generic runtime correctly observed a decreasing sleep counter, but assumed every suppressed sleeping turn remained in dialogue. Gen I returned to MAIN between turns; confirming from MAIN entered FIGHT rather than attempting the selected move, so the final sleep turn never advanced. | Sleep recovery now semantically normalizes MAIN to FIGHT and MOVE to the latched legal slot before each suppressed turn, while UNKNOWN remains a dialogue confirmation. Complete PP-vector checks still prove that sleep recovery neither substitutes nor spends a move. A regression simulation returns through ITEM-selected MAIN states and verifies wake-up plus the eventual legal attack. |
| The two-stage setup defeated Sabrina and advanced to the Mansion training block at checkpoint 275, where a wild opponent Disabled the last preferred move with PP. | The short lead-training policy ranked PP but did not remove a live disabled slot, even though the longer balanced-team policy already treated Disable as a temporary capability loss. | Lead training now ranks battle-active PP and excludes a slot only while its Disable counter is live. If no legal preferred attack remains, it records a bounded flee and resumes the field-level heal/seek policy instead of issuing an illegal action. |
| The v5 replay passed the repaired Silph boundary and reached 1,250 equal-level Mansion wins, but the five non-workhorses were still levels 45–46 while the escort had reached 79. | The five-level-spread gate optimized visual symmetry rather than the future collection objective. Four non-workhorses were already final species; Diglett alone still needed its level-26 evolution, so thousands of party-wide fights repeated grinding instead of targeting the missing evolution behavior. | The replay was stopped safely and remained uncounted. The main teacher trains Blastoise to 75, uses the developed-team planner to identify the precise nonfinal slot, trains only Diglett until Dugtrio is observed, and then requires the exact healthy final-form roster. Recruitment, evolution, restoration, switching, and workhorse readiness remain reusable semantics; the older equal-level policy remains available for explicit experiments. |
| V5 qualified the new level-75-workhorse/final-form curriculum, but its first immutable training root fainted at the S.S. Anne rival with Ivysaur still alive. | Pidgeotto lowered accuracy twice, the first three opponents consumed both retained Potions, and the lower-accuracy Mega Punch lesson prolonged Ivysaur while Leech Seed restored it. The route had already earned TM11 but delayed teaching BubbleBeam until after Surge. | V5 is preserved and retired. V6 teaches BubbleBeam before boarding at no economic cost, ranks it against Pidgeotto and Raticate, uses Bite against Kadabra and Ivysaur, and promotes the exposed failed seed to the uncounted qualification schedule. Its twelve counted seeds are fresh and disjoint. |
| The first v6 rehearsal reached the Vermilion dock after learning BubbleBeam but the checkpoint reported an unknown phase. | The inherited chapter-completion invariant treated possession of consumable TM11 as permanent evidence. Correctly teaching the move removed the item and therefore hid otherwise-valid dock evidence. | The invariant now accepts either TM11 in the bag or BubbleBeam in the observed lead moveset. This is an evidence-model repair, not a route retry or relaxed gameplay gate; the complete rehearsal restarts uncounted. |
| The next v6 rehearsal cleared S.S. Anne but stopped while weakening a level-4 passive Forest cocoon at 7/18 HP. | Harden reduced the helper's Tackle to one damage. The reusable planner still requested weakening to 30% HP, but the adapter imposed a fixed eight-hit ceiling unrelated to the observed remaining HP. | The adapter computes a finite per-encounter budget from current HP, maximum HP, and the policy threshold under a conservative one-damage assumption, capped at 32. Normal targets retain the eight-hit floor; passive cocoons receive only the additional verified attacks needed before throwing. |
| The adaptive replay captured the passive cocoon, then a level-5 Pikachu immediately knocked out the level-3 Pidgey helper on switch-in. | The adapter classified Pikachu as high risk but still allowed a fragile helper switch at 80% HP. The opponent's type and damage ceiling made that ratio inadequate before the helper could act. | Pikachu is a direct-throw target behind the durable workhorse, with the existing five-ball encounter limit. Fragile helpers remain available for ordinary targets; dangerous encounters avoid an unnecessary sacrificial switch. |
| The next v6 rehearsal passed Forest, Rock Tunnel, Silph, and Sabrina, then rejected a valid nineteen-slot Cinnabar bag containing two Antidotes. | The capacity policy correctly knew that the obsolete cure slot should be removed, but its sale primitive assumed the stack quantity was exactly one and its money proof encoded only zero-or-one sale proceeds. | The Cinnabar cleanup sells the exact observed one- or two-Antidote stack through a verified quantity selector and includes the precise proceeds in its ledger. It still frees exactly one slot and preserves every Mansion item/capacity gate. |
| The capacity-safe replay completed the developed-team curriculum and reached Lance, where an unconditional Aerodactyl pivot fainted a level-25 teammate. | The pivot was inherited from the old single-carry route. The healthy level-79 Blastoise already had type-advantaged Surf and Ice Beam, so sacrificing a deliberately lower-level final-form teammate added risk without creating a needed recovery turn. | Lance keeps the workhorse active against Aerodactyl and uses the existing type-aware move ranking. Helper switches remain available only when a real HP/status recovery boundary requires one, aligning League play with the zero-faint developed-team objective. |
| The Lance-safe replay reached the Champion's last level-65 Alakazam with a level-80 Blastoise, completed one recovery, then rejected a later valid healing action. | Alakazam's Recover animation and enemy reply outlasted the healing helper's twenty-four-frame settle window; the teacher timed out even though the workhorse and item reserve were sufficient. | Healing uses the shared bounded battle-item settle allowance and cancellation-only text advancement, while still proving return to trainer MAIN and an exact one-item decrement. The uncounted replay receives no extra item, retry, level, or battle attempt. |
| The long-settle replay used that valid recovery, then switched its 180/262-HP Blastoise to a level-30 teammate after recovery items ran out; the teammate fainted while Alakazam healed from 176/189 to full. | The exhausted-reserve pivot was inherited from the obsolete single-carry route. It did not purchase a healing action, erased offensive progress, and violated the developed-team objective by treating a final-form member as disposable. | Champion play keeps the healthy workhorse active after recovery is exhausted. Helper pivots remain bounded to verified recovery turns, so party switching must create a concrete strategic capability rather than merely absorb a knockout. |
| Keeping the workhorse active reduced the final Alakazam to 4/189 HP, but Blastoise then fainted while three developed teammates remained alive. | The Champion adapter still treated an active-battler KO as a terminal single-carry failure; it could not express the ordinary team skill of choosing a healthy reserve and finishing the battle. | The teacher performs an observed, bounded forced switch to the healthiest living teammate and selects that reserve's first legal live-PP move, respecting Disable. A five-switch ceiling preserves a finite team-battle contract without extra healing, resets, or attempts. |
| The forced-switch replay sent in Snorlax and reduced Alakazam from 4/189 HP to zero, but rejected the post-KO transition. | Champion receipts still read Blastoise's party-slot-zero HP and PP after a reserve became active, so a won battle looked like a fainted-lead runtime failure. | Post-switch decisions and receipts use active-battler HP, status, moves, and PP. A verified final KO receives a bounded victory-text transition, after which the unchanged Champion-event plus Hall-of-Fame terminal contract must still pass. |
| The active-battler replay correctly recorded Snorlax at 140 HP using Headbutt and Alakazam at zero, yet still emitted the runtime error. | The first exception sample preceded the stable KO state, while the authoritative diagnostic reread already held enemy HP zero; the handler checked only the transient sample. | The strict final-KO handler also runs on the authoritative reread before error emission. It still requires the trainer battle, exact zero enemy HP, and a living teammate, then resumes the unchanged Hall-of-Fame proof. |
| The authoritative-reread replay still rejected the KO, and its final snapshot showed `scripted_or_blocked` with no active battle while the enemy-zero bytes remained present. | By the stable reread, the game had already crossed from trainer battle into post-battle dialogue; requiring battle state two was one observation too early, just as requiring it to be zero on the first sample was too late. | The handler accepts both legal sides of the exact KO transition: active trainer battle plus zero HP receives bounded settling, while post-battle dialogue plus zero HP returns to the existing Hall-of-Fame dialogue controller. Every other state fails closed. |
| The next replay passed 312/312 checkpoints and entered the Hall of Fame, but the offline harness reported an incomplete planned schedule despite recording all 68 offset-application events. | The reserve-battler final KO exited outside the adaptive runtime. Gameplay proved the exit, but the manual path did not close the schedule controller's still-active Champion intent. | The proven external Champion exit now invokes the same lifecycle hook used by other bounded team continuations, closing both schedule and recorder state. No attestation is synthesized; the next exact-source replay must still apply and finish all 68 scheduled battles. |
| V6 then qualified **312/312 checkpoints**, **36/36 objectives**, Hall of Fame, and **68/68** scheduled battles, but immutable train slot 01 stopped after the mandatory Cerulean Gym trainer with Wartortle at full 61/61 HP and five Potions. | The teacher had no recovery need, yet its post-battle contract demanded normalization to exactly four Potions and attempted to use an item the game correctly rejects at full HP. A safety allowance had again been confused with a mandatory action. | V6 remains permanently failed and retired. V7 uses the exposed seed only for its uncounted rehearsal and preserves unused Potions across every early handoff. Its twelve counted seeds are fresh and disjoint. |
| The first v7 rehearsal cleared the repaired Gym, Rocket, and Route 6 contracts, then Wartortle fainted against the S.S. Anne rival's Ivysaur with 25/57 HP remaining. | Pidgeotto lowered accuracy, the rival healed Raticate, and Leech Seed plus repeated misses exhausted three retained Potions. The route was still budgeting near the historical minimum rather than funding realistic early variance. | The failed rehearsal is uncounted and all official slots remain unopened. The Nugget-funded Cerulean top-up buys two additional Potions in the same inventory stack and carries a bounded four-to-seven reserve through the early chapters. This strengthens reusable resource planning without adding retries or weakening battle evidence. |
| The first expanded-reserve replay reached checkpoint 55 and legitimately attempted a post-Gym heal, then rejected the item transition. | The purchase and live decision were correct, but the field helper still asserted the retired exact-four destination instead of the new starting reserve minus one. | The damaged branch now proves exactly one Potion decrement and the full-health branch proves zero; both have direct regression tests. The replay was uncounted and no collection slot opened. |
| The next v7 replay defeated the S.S. Anne rival and reached the Viridian Forest collection lesson after checkpoint 91, where a weakening helper fainted and the forced replacement never settled. | The party menu accepted an early confirmation without changing the battler. The recovery loop did not recognize that the forced-party cursor had reappeared, so it alternated generic dialogue inputs instead of explicitly choosing the healthy lead again. | While the battler remains fainted, the controller now recognizes the live party cursor, reselects slot zero, and requires unchanged target identity/HP plus a stable wild-battle MAIN menu. A simulation covers the premature-confirmation lineage; the failed rehearsal remains uncounted. |
| The forced-switch repair advanced v7 through Forest, Silph, and Sabrina to checkpoint 271, where Cinnabar rejected a twenty-slot effective plan. | The live bag had nineteen slots with Bide already sold. The planner added its Great Ball replacement before accounting for the already-planned Antidote sale, briefly modeling twenty effective slots even though the cleanup would leave nineteen physical slots. | The capacity model now accepts the twenty-effective-slot branch, sells the obsolete Antidote first, and then buys the replacement token. A true twenty-slot input can sell an obsolete Potion stack with exact proceeds. The failed rehearsals remain uncounted. |
| The corrected ordering reached Pokémon Mansion at checkpoint 273, collected TM14, and then could not add the Secret Key because the bag had reached twenty occupied slots. | Selling the Antidote before buying the replacement left nineteen physical slots after the one-use Repel disappeared. The plan had reserved only one pickup slot even though the qualified route collects two unique Mansion items. | A nineteen-slot input with Bide absent also sells its obsolete Potion stack before purchasing the disclosed Great Ball replacement. The route enters the Mansion with eighteen occupied slots after Repel use, reserves exactly two pickup slots, and still reaches the intended full-bag delayed-TM38 lesson. The uncounted failure consumed no campaign slot. |
| V7 then qualified **312/312 checkpoints**, **36/36 objectives**, Hall of Fame, and **68/68** scheduled battles, but its first immutable training root stopped at checkpoint 55 after Wartortle hurt itself in confusion. | The turn legally returned to the main battle menu with Wartortle's HP reduced from 61 to 47, Goldeen still at 27 HP, and Mega Punch PP unchanged. The selector treated every no-PP turn as an unregistered confirmation even when combat-state evidence proved the turn had resolved. | V7 remains permanently failed and retired. V8 uses the exposed seed only for its uncounted rehearsal. The confusion-capable Gym controller accepts a no-PP turn only when the main menu returns and combatant HP changed, then explicitly chooses the move again; stale input with no state change still fails closed. Fresh counted seeds remain disjoint. |
| The first v8 rehearsal passed the exact confusion branch and Misty, then Cerulean's moving walker blocked the robbed-house route at checkpoint 59. | The same coordinate already had a bounded yield maneuver on a later northbound replay, but the initial southbound traversal still used generic movement retries that could not create room for the NPC to move. | Both crossings now share the finite step-aside, wait, return, and retry maneuver. It proves the exact corridor throughout and rejects map changes, battles, or failure to clear; the rehearsal remains uncounted. |
| The walker-safe v8 replay reached the S.S. Anne rival at checkpoint 79, spent six Potions, and still fainted against Ivysaur at 15/57 HP. | A 20-HP Potion created little or no net recovery once Ivysaur's attack and Leech Seed resolved, so adding more copies of the same weak item would prolong the losing cycle rather than solve it. | Vermilion preparation buys three 50-HP Super Potions with an exact ₽2,100 ledger and prioritizes them at a bounded low-HP MAIN boundary before ordinary Potions. The high-value reserve is consumed during the rival battle, preserving downstream inventory shape; the failed rehearsal remains uncounted. |
| The first funded-reserve rehearsal stopped at checkpoint 75 before reaching the Vermilion Mart. | The new route concatenated an interior Center exit and the exterior walk without allowing the map transition to settle, so subsequent directions were applied from the wrong coordinate. | Center exit and Mart approach are separately observed segments with the established bounded transition wait between them. No item was purchased and the rehearsal remains uncounted. |
| The transition-safe replay bought and consumed all three Super Potions but still fainted against Ivysaur at 16/57 HP after repeated accuracy-reduced misses. | Stronger healing extended the same underpowered battle instead of improving damage, accuracy recovery, or workhorse development. The route was still postponing all deliberate experience management until Cinnabar. | A game-neutral training policy now stages the workhorse in Diglett's Cave before boarding: fight bounded wild encounters with ranked Water moves, stop at level 30, return through the exact Route 11 gate, and heal before the rival. The receipt proves level, wins, steps, healing, and zero faints; level 75 remains the later workhorse target. The failed rehearsal remains uncounted. |
| The pre-ship training rehearsals successively exposed an early warp input, the stable `(37, 31)` arrival/return-warp boundary, and then 2,000 bounded attempts against the blocked north neighbor of `(37, 30)`. | The cave entrance has three distinct semantics: `(4, 4)` is transitional, `(37, 31)` is safe only on arrival and becomes the return warp after leaving it, and the safe `(37, 30)` anchor cannot move north. | Training waits for two input-ready observations, steps once to `(37, 30)`, probes only non-warp neighbors until the coordinate really changes, and remembers the inverse direction for a one-tile bounce and exit return. All rehearsals remain uncounted. |
| The adaptive lane reached level 26 through repeated safe `(36, 30)`/`(37, 30)` encounters, then lost its return direction when a battle began before the attempted step changed the coordinate. | In Generation I an encounter can take control on the movement input while the reported overworld coordinate remains unchanged. Coordinate delta alone therefore cannot distinguish a blocked step from a successful encounter request. | A live battle now counts as successful encounter seeking even without a coordinate delta. If the trainer was away from its anchor, its previously proven inverse direction survives the battle; if it was already at the anchor, no return direction is needed. The rehearsal remains uncounted. |
| The first clean replay with the level-60 workhorse target cleared the revised S.S. Anne route and Pokémon Tower, then reached the Snorlax restock with four carried Super Potions but only enough cash for the 24-Great-Ball reserve. | The restock treated two recovery items as a mandatory purchase rather than a minimum inventory floor, ignoring a stronger valid carryover from the early training route. | The Mart plan now buys only the shortfall below two Super Potions and proves the exact dynamic ledger. The 24-Great-Ball reserve and Snorlax recovery bound are unchanged; the replay remains uncounted. |
| The shortfall-aware replay caught Snorlax and reached Saffron, then repeatedly failed to enter Celadon's department store while fetching X Specials. | The source-defined right entrance at `(10, 13)` did not accept the northward step on this live lineage even after field authority was proved; retrying the same doorway added no new evidence. | Both Silph-era visits now use the source-defined left entrance at `(8, 13)` and a collision-derived path from its `(2, 7)` interior warp to the second-floor stairs. Every step remains state-observed and bounded. The replay remains uncounted. |
| The alternate-door replay completed Silph, assembled and healed all six members, defeated Sabrina, and reached Cinnabar at checkpoint 271 with a level-48 lead. | The Cinnabar receipt required the historical exact level 47 even though it also proved that Route 16/21 preserved the complete stat vector. Earlier deliberate training legitimately advanced the same starter lineage by one level. | The chapter now requires a level floor of 47 and exact before/after level and stat preservation, retaining the route-safety evidence without binding it to one experience total. The replay remains uncounted. |
| The level-floor replay tested the reduced workhorse target end to end. | Level 75 was a conservative carryover, while earlier evidence already showed a smaller party could enter the Hall of Fame at level 61. | The six-member teacher passed **312/312 checkpoints**, **36/36 objectives**, defeated the Champion, and entered the Hall of Fame in **87,020 actions**. Blastoise trained from level 48 to 60 through 177 Mansion wins, 2,826 steps, seven healing trips, and zero faints; 24 additional targeted battles evolved Diglett without grinding the four already-final teammates. It reached Indigo at level 63 and the Hall-of-Fame census at level 67. This clean-power diagnostic qualifies the strategy change; the exact source still needs the uncounted 68/68 scheduled rehearsal before collection opens. |
| The first source-frozen level-60 v8 schedule rehearsal reached checkpoint 75, then deadlocked on the harbor approach at `(21, 27)`. | Vermilion's horizontal sailor had reached the end of his patrol immediately left of the player. Repeating left and waiting kept the two characters facing each other, so the NPC had no legal tile through which to clear. | The route recognizes only that exact map, coordinate, direction, and chapter. It steps north off the patrol row, waits with a finite bound until the return tile opens, restores `(21, 27)`, and retries left to `(20, 27)`. Any different position, map, battle, or failed restoration is rejected. The artifact remains private and uncounted; all twelve v8 slots remain pristine. |
| The sailor-safe rehearsal reached checkpoint 86, found twelve legal level-17 Spearow, and knocked out every one while trying to weaken it. | Water Gun had been qualified when the starter was level 24. The new staged-development curriculum arrives at level 30–31, where every available damaging move is lethal to full-health Spearow; retaining the old move rule converted development into a capture failure. | The teacher now recognizes the proven level-30 floor and uses a maximum of five full-health throws on the same legal target. Every failed throw must consume exactly one Ball, preserve a living level-17 Spearow and workhorse, and return to the battle main menu; success proves the exact total decrement and party addition. This teaches the portable rule “do not weaken when no nonlethal attack exists” and removes twelve unnecessary knockouts. The rehearsal remains uncounted. |
| The direct-capture replay caught Spearow on its fourth Ball, completed Surge, and reached the Rock Tunnel supply purchase at checkpoint 102 with ₽259 less than the fixed four-Repel budget. | The Mart plan advertised a five-throw capture allowance but still financed itself by reselling the Ball remainder from an exact one-throw outcome. Three additional legal throws reduced proceeds by ₽300, exposing a hidden economy dependency. | Supply planning computes the shortfall after observed Nugget and Ball sales, then sells only the exact number of obsolete 20-HP Potions needed to fund the fixed Super Potion, status-item, and Repel contract. The sale is capped by live inventory and proves both quantity and money deltas. This carries variable capture cost into downstream planning instead of weakening either bound; the rehearsal remains uncounted. |
| The funded replay passed checkpoint 194 after winning HM03, and Surf replaced Water Gun correctly, but the teaching helper still rejected the result. | Its gate required Bite and BubbleBeam to have maximum PP after teaching. The observed route legitimately entered with both at 16 PP, and Gen I preserved those unrelated slots while setting Surf to 15; PP restoration happens only at the later Center visit. | HM teaching now records pre-lesson PP, proves slots one through three are unchanged at the immediate teaching boundary, proves slot four becomes Surf with 15 PP, and separately proves the later nurse restores the full `(25, 30, 20, 15)` vector. The failed artifact was semantically successful gameplay but remains uncounted because its evidence contract rejected it. |
| The observed-PP replay passed Surf teaching at checkpoint 195 and left the Safari Zone, but its final chapter report still saw `(16, 30, 16, 15)` PP. | The Fuchsia nurse loop stopped on already-full HP and zero status, one confirmation after opening dialogue. It never required the nurse interaction to complete, so the checkpoint label claimed healing without proving PP restoration. | The nurse boundary now remains in its bounded dialogue loop until HP, status, and the full post-Surf PP vector are all restored. This makes the later report's maximum-PP requirement an executed recovery fact rather than an assumption. The rehearsal remains uncounted. |
| The fully restored replay passed every earlier repair, assembled the six-member party, completed level-60 training, defeated the first three Elite Four members, and reached Lance at checkpoint 308 before a recovery pivot stalled. | Two earlier weak helpers fainted and returned correctly from party slots 1 and 2. The third was slot 4; the shared forced-switch helper still treated cursor values above 2 as invalid, an inherited three-member assumption that left it confirming faint text without selecting Blastoise. | Forced-switch readiness now accepts any cursor smaller than the observed live party size, while still requiring the real party-menu cursor tile. A regression proves slot 4 is valid for six members and invalid for three. This removes a roster-size artifact without adding recovery items, retries, or battle attempts; the rehearsal remains uncounted. |
| The six-slot replay completed the third forced switch and defeated Lance, then post-battle recovery rejected three fainted helpers against a two-Revive reserve. | Once Surf was the only usable attack, the full-health safety threshold requested recovery after each Aerodactyl exchange. The first two helper sacrifices matched the declared revival budget; the third spent a teammate even though Blastoise still had 165/205 HP and could safely use the same healing item directly. | Lance recovery now caps helper pivots at the fixed two-Revive contract. Any later recovery heals the active workhorse directly, preserving the third helper for the Champion. A regression binds the cap, and no extra item, retry, or level is added. The rehearsal remains uncounted. |
| The first conservative-HP recovery returned safely through the cave and Route 11, then collided with the Vermilion Mart at `(26, 15)`. | The old terminal-only return had assumed a four-tile southbound shortcut that had never been exercised because every prior rehearsal stopped inside the cave. | Recovery reverses the qualified Mart-to-Route-11 path to the observed `(23, 14)` exterior and then reuses the qualified Mart-to-Center path. The same source route is used for bounded healing trips and the final restored boundary. |
| The recovered route completed level-30 development and boarded the S.S. Anne, then the rival checkpoint saw `unknown` one observation after battle state became active. | The battle-state byte can precede the full semantic identity fields at this timing boundary. Treating the first nonzero battle byte as a complete rival snapshot was premature. | Rival entry waits without selecting an action until the opponent, trainer, and ship-script identity contract is simultaneously true, then hands the verified boundary to the battle policy and schedule instrumentation. |
| Waiting exposed a fully correct RIVAL2 opponent, trainer class, trainer number, map, coordinate, and ship script, but the engaged-trainer scratch class remained `0x15` from Route 6. | The new wild-training block demonstrated that these auxiliary bytes persist across unrelated battles; the old gate mistook stale implementation state for authoritative rival identity, and its set byte matched only by coincidence. | The rival contract retains the live opponent/class/number and ship-local script evidence but excludes both stale engaged-trainer scratch bytes. Regression tests still reject the wrong opponent, trainer class, or trainer number. |
| The level-30 workhorse defeated the S.S. Anne rival without needing all three Super Potions, then the old post-battle contract rejected the unused reserve. | Exact exhaustion had been introduced to preserve one weaker route's downstream inventory shape. Once staged development solved the battle strategically, spending useful items without need became anti-curriculum behavior. | Rival recovery now proves an exact zero-to-three adaptive decrement and preserves unused Super Potions. Later chapters must consume, retain, or sell that legal surplus according to their own observed resource needs rather than requiring waste here. |
| Preserving the unused reserve reached checkpoint 84, where Surge preparation tried to buy “Super Potion number one” despite already holding three. | The Mart script encoded an action count instead of the resource objective: fund at least one bounded Gym recovery. | Surge preparation observes the carryover, buys only a zero-to-one shortfall, and proves the later exact target minus its optional single recovery. The route no longer wastes money or rejects useful legal inventory. |
| The revised Surge ledger cleared checkpoint 97, then Lavender rejected the remaining three Super Potions; accepting them and targeting eleven left the pre-trainer Mart ₽809 short of four Repels. | Rock Tunnel preparation added ten items to the observed quantity instead of funding a fixed capacity, while the old economy assumed the earlier S.S. Anne reserve had been wasted. | Lavender accepts zero-to-three carryover, buys only the shortfall to a fixed ten-item high-value reserve, and sells one obsolete 20-HP Potion for ₽150 when stronger carryover is available. This retains the historical ten-item capacity, funds all four Repels, and preserves the existing four-item post-tunnel reserve. |
| The funded route cleared Rock Tunnel, the Hideout, and Tower through checkpoint 151, where the level-30 workhorse had already evolved naturally into Blastoise and an exact Wartortle tuple guard rejected it. | Tower's Rare Candy lesson encoded the historical level-35 arrival rather than the semantic goal of obtaining and preserving the final starter evolution. Earlier deliberate development moved the same legal evolution sooner. | Tower accepts Wartortle or Blastoise at entry, initializes its movement guard from the observed lineage state, and records an already-final `(Blastoise, Blastoise)` evolution receipt without spending candy. DUX, Diglett, order, moves, living HP, and the final roster remain protected. |
| The Disable-safe replay trained all six members to at least level 75, earned all eight badges, and crossed Victory Road before the League shop lacked ₽611 for its two-Revive reserve at checkpoint 296. | The expanded capture and Sabrina reliability budgets were not propagated through the final economy. Two obsolete Antidotes remained, while the shop still bought a third Full Heal despite six Full Restores providing the same status-clearing fallback. | Indigo cleanup now sells every remaining narrow status cure and buys two Full Heals plus the unchanged six Full Restores, eleven Hyper Potions, two Revives, and battle-setup reserves. This funds the exact helper-revival plan without reducing the full-team training target or static-capture reserve. |
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

The agent should acquire and retain a full six-member party with complementary roles, evolve every
member to its declared final form available in the title and save lineage, and train one designated
completion workhorse to level 60. That target is deliberately empirical: an earlier three-member
teacher entered Indigo at level 58 and the Hall of Fame at level 61, while the current six-member
teacher has better reserve coverage. Already-final non-workhorses do not need thousands of redundant
battles merely to match the carry's level. The portable equal-level policy remains available for
explicit balancing experiments; the main route instead uses the same final-form semantics needed
by the future Pokédex curriculum. Temporary deviations are permitted when progression genuinely
requires them, but each one must be recorded with its reason rather than silently weakening the
rule.

### Reusable concepts, not Red coordinates

The new layer is deliberately split so the policy can outlive Pokémon Red:

- `party.py` is the **game-neutral observation contract**. It describes party membership, species,
  active-party position, level, health, status condition, moves and remaining power points, and
  experience, plus the derived team metrics a planner actually reasons over: minimum and maximum
  level, level spread, average level, fainted count, incomplete-party state, and the weakest
  *trainable* member. It contains no addresses, coordinates, or revision-specific identifiers.
- `team_training.py` contains the **reusable team-development policies**. It decides whether to
  recruit, evolve, restore, switch, train, or stop; selects safe grinding areas; and emits portable
  equal-level and developed-team receipts. The developed-team contract verifies the final-form
  roster and a configurable workhorse target without requiring every specimen to share one level.
  Its rules are expressed in species, levels, roles, and health—never in map tiles.
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

The formal learner requires complete one-shot outcomes for all five train and two validation roots
under one exact campaign identity. It fits only training, selects on validation, leaves all five
test roots unopened, and publishes a private canonical candidate with legality, baseline,
cross-entropy, free/forced-choice, visible-overlap, novel-visible, and confidence evidence. V3
passed its complete **312/312**, **36/36**, **68/68** Hall-of-Fame rehearsal, then its first
immutable training root failed honestly at Route 24 trainer 2 after accuracy loss, poison, and
repeated misses. Later v4 and v5 campaigns also qualified before their first immutable roots
failed. V6 qualified **312/312**, **36/36**, and **68/68**, but its first training root exposed the
unnecessary exact-four-Potion handoff at Cerulean. V6 is preserved and retired. V7 now binds the
four-to-seven Potion corridor, uses exposed seed `16001` only for its uncounted rehearsal, and has
twelve fresh counted slots. V7 remains unopened pending that complete replay. No learned model has
completed the game.

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

The first exact replay of the revised capture curriculum passed the former Viridian Forest
bottleneck and reached checkpoint 102/312. It then exposed a separate resource-coupling defect:
successful early captures left 15 Poké Balls but only ₽291, while the deterministic Rock Tunnel
supply contract still required four Repels. The teacher now liquidates 14 unused early Poké Balls
for ₽100 each, retains one as a legal capture/capacity token, and verifies both the inventory delta
and the complete Mart cash ledger. This does not weaken the later Snorlax capture contract, which
purchases an independent Great Ball reserve. The replay remains an uncounted qualification rehearsal.

The final source-frozen v8 rehearsal then qualified end to end: **312/312 checkpoints**, **36/36
objectives**, **68/68 scheduled battles**, Champion, and Hall of Fame. Its first immutable training
root reached checkpoint 90 before the Dig lesson rejected TM28 despite the item being present.
Variable Spearow capture spending had shifted the bag, and the old absolute-item helper could move
its cursor only downward. The run is retained as an honest failed data point; v8 is retired with
eleven unopened slots. The replacement v9 curriculum makes bag navigation bidirectional, rehearses
only on exposed seed `18001`, and preregisters twelve fresh counted roots. This is the intended
research loop: preserve a failure, generalize the teacher skill, and prevent the observed root from
leaking into the model-fitting set.

V9's first uncounted rehearsal proved the bidirectional TM28 selection through checkpoint 91, then
Rock Tunnel produced a third legal paralysis event. The two carried cures had already been consumed,
so the teacher rejected DUX's remaining paralysis instead of inventing an item or ignoring its own
status contract. Tunnel preparation now carries and Lavender restores a third, explicitly funded
contingency cure. It increases the existing item-stack quantity without consuming another bag slot.
No counted v9 slot opened during this diagnosis.

Buying the third cure required one additional 120-frame Mart quantity input. The following v9
rehearsal retained the old post-Mart wait, shifted the Tunnel RNG lineage by that exact amount, and
fainted at trainer 5. The alignment wait is reduced from 191 to 71 frames so the quantity-selection
inputs plus explicit alignment remain the previously qualified 311 frames. This preserves the
tested battle lineage without adding a retry, recovery, or level; the rehearsal remained uncounted.

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
