# Preregistered battle collection protocol

## Scope and current status

The public
[`red-battle-collection-v70.json`](../configs/red-battle-collection-v70.json)
registry freezes one prospective Pokémon Red teacher-collection campaign:

- 71 stable public battle-plan identities in exact qualified-route order;
- five `train`, two `validation`, and five `test` root-lineage slots;
- partition-local ordinals `1/5` through `5/5`, `1/2` through `2/2`, and `1/5`
  through `5/5`, in addition to global collection ordinals `1/12` through `12/12`; and
- one unique 71-offset timing schedule and one attempt for each slot.

The v1 campaign's uncounted rehearsal completed all 312 checkpoints, all 36 objectives, and Hall
of Fame with 68/68 schedule attestations. Its first one-shot training root then failed at Route 24:
a poisoned Wartortle entered trainer 3 at 17/54 HP and Ekans trapped it with Wrap. That failure is
preserved in the private immutable ledger; v1 is not eligible for model fitting because its five
training roots can no longer all complete. The teacher now visits the already-planned Center before
that trainer, and an uncounted replay of the exact exposed schedule reached the following trainer.

The v2 campaign later qualified its complete dry rehearsal, but its first immutable training root
failed at the Rocket thief as documented below. V2 is therefore retired and remains preserved as
historical evidence. The v3 campaign also qualified a complete 312/312, 36/36, 68/68 Hall-of-Fame
rehearsal. Its first immutable training root reached Route 24 trainer 2 at checkpoint 42 before
three consecutive accuracy-reduced Water Gun misses let poison and enemy attacks faint Wartortle
with the opponent at 4 HP. The one-shot v3 failure remains in its private ledger, so v3 is retired
and cannot be used for fitting.

V5 passed its complete uncounted 312-checkpoint, 36-objective, 68-battle Hall-of-Fame
qualification, including the targeted Diglett-to-Dugtrio lesson. Its first immutable training root
then failed at the S.S. Anne rival after accuracy loss and the earlier opponents consumed both
retained Potions. V5 is therefore retired with that failure preserved. V6 subsequently passed its
complete **312/312 checkpoint**, **36/36 objective**, **68/68 battle**, Hall-of-Fame qualification.
Its first immutable training root then reached the mandatory Cerulean Gym trainer with Wartortle
at full **61/61 HP** and all five Potions intact. The historical exact-four handoff tried to consume
an unnecessary field Potion, which the game correctly disallowed at full health. That one-shot v6
failure remains preserved, and v6 is retired rather than changed or rerun.

The retired v7 registry promoted exposed v6 seed `16001` to its uncounted dry rehearsal and assigned
twelve fresh, disjoint counted seeds. Its first rehearsal proved the original preservation repair
through Cerulean, Rocket, and Route 6, then accuracy loss, the rival's own Potion, and Leech Seed
exhausted three retained Potions at the S.S. Anne rival. The failure is private and uncounted; all
twelve official slots remain pending. The funded Cerulean top-up now buys two additional Potions
and carries a bounded four-to-seven reserve through the Rocket thief, Route 6, and S.S. Anne rival.
This converts
an accidental exact-count requirement into the intended resource lesson: recovery is permitted
when live damage requires it, never mandatory merely to reproduce one historical inventory. V7
must pass its complete qualification before any counted slot opens.

The first expanded-reserve replay reached the same mandatory Gym trainer and legitimately needed
one post-battle heal, but its item helper still asserted the retired four-Potion destination rather
than the new starting quantity minus one. That uncounted bookkeeping failure stopped at checkpoint
55. The helper now proves exactly one decrement on the damaged branch and zero decrements on the
full-health branch; both have direct regression coverage before the next complete rehearsal.

The corrected reserve replay defeated the S.S. Anne rival and advanced through checkpoint 91,
where the shifted encounter schedule fainted a weakening helper in Viridian Forest. The forced
party menu accepted an early confirmation without switching, and the old settle loop then alternated
generic inputs until its bound expired. The uncounted artifact remains preserved. While the active
battler is still fainted, the recovery now recognizes a live forced-party cursor, explicitly
reselects the protected lead, and only succeeds after proving the same wild target HP and a stable
battle MAIN menu.

That correction carried the rehearsal through S.S. Anne, Forest, Silph, and Sabrina to checkpoint
271. The capacity plan reported twenty effective slots: the live bag held nineteen with Bide
already sold, and the planner added its Great Ball replacement before accounting for the planned
Antidote sale. The corrected ordering supports that twenty-effective-slot branch by selling the
obsolete Antidote first and then buying the replacement token, leaving nineteen physical slots.
A true twenty-slot input may instead sell an obsolete Potion stack with exact proceeds. The failed
rehearsals were uncounted and the full exact-source qualification remains mandatory.

The next rehearsal replayed that branch through checkpoint 273 and proved that nineteen physical
slots before entering the Mansion were still one too many: TM14 filled the twentieth slot, so the
Secret Key could not enter the bag. When the live input has nineteen slots and Bide is absent, the
cleanup now also sells the obsolete Potion stack before buying the disclosed Great Ball
replacement. The Mansion therefore begins with eighteen occupied slots after using its Repel,
leaving exactly two slots for TM14 and the Secret Key while preserving the later full-bag TM38
lesson. Potion quantity and proceeds remain exact evidence. This failure was uncounted; no official
v7 slot had opened at that point.

The corrected v7 source then passed the complete **312/312 checkpoint**, **36/36 objective**,
**68/68 battle**, Hall-of-Fame qualification. Its first immutable counted training root exposed a
different legal battle branch at checkpoint 55: Wartortle hurt itself in confusion, so its HP fell
while Goldeen's HP and Mega Punch PP correctly remained unchanged. The move selector required a PP
decrement from every selected turn and rejected that completed confusion turn. The failed v7 root
is preserved in its immutable ledger, so v7 is retired and its eleven pending slots will not run.

The retired v8 registry used that exposed v7 seed `17001` only for its uncounted dry rehearsal. It
assigns fresh counted seeds `18001`–`18005`, `28001`–`28002`, and `38001`–`38005`. The Cerulean Gym
controller may now recognize one narrowly evidenced no-PP turn only after the battle returns to its
main menu and either combatant's HP changed; it then deliberately selects the required move again.
Unchanged stale input still fails the original persistent PP gate. V8 must pass its full exact-source
qualification before any counted slot opens.

The first v8 rehearsal crossed the repaired confusion turn and defeated Misty, then the altered
timing placed Cerulean's north/south walker in the robbed-house corridor at checkpoint 59. The
route already had a bounded yield-and-retry maneuver for the identical corridor on a later replay;
that maneuver now applies on the initial crossing as well. It may step aside, wait with a finite
attempt count, restore the exact approach coordinate, and retry left, while any off-corridor or
battle state still fails closed. This rehearsal was uncounted and v8 remains unopened.

The obstruction-safe rehearsal then reached the S.S. Anne rival at checkpoint 79. Six ordinary
Potions could not escape Ivysaur's damage cycle: a low-HP Potion restored 20 HP, but the following
attack plus Leech Seed removed nearly the same amount while healing the opponent. Wartortle
eventually fainted with Ivysaur at 15/57 HP. The teacher now buys three Super Potions in Vermilion
before boarding, proves their exact ₽2,100 ledger, and prioritizes their 50-HP recovery at a bounded
low-HP battle menu before falling back to the retained Potion stack. The reserve is deliberately
consumed in the rival battle so the downstream capture and inventory contracts remain unchanged.
This failure was also uncounted; another complete qualification is required.

The first funded-reserve rehearsal reached Vermilion preparation at checkpoint 75, then missed the
Mart because the new path concatenated the Center exit and overworld walk without the qualified map
transition wait. The route now keeps those as two separately observed movement segments with the
same bounded transition settle used elsewhere. No purchase or counted attempt occurred.

After that movement repair, the reserve was purchased and consumed as planned, but the exposed
schedule still produced enough accuracy-reduced misses for Wartortle to faint against Ivysaur at
16/57 HP. Healing improved endurance without correcting the strategic level and damage deficit.
Pre-ship preparation now includes a portable training-policy lesson in Diglett's Cave: seek wild
encounters, prefer super-effective Water moves, stop at level 30, and fail closed on HP, status, PP,
battle, step, or enemy-level bounds. It trains only on a two-tile corridor beside the Route 11
entrance, returns through the exact gate, heals in Vermilion, and emits a training receipt before
boarding. This keeps the long-term level-75 workhorse target while teaching staged development
where it first creates reliable value. The rehearsal remains uncounted.

The first staged-development rehearsal reached the cave gate at checkpoint 75, but began holding a
movement direction while the linked Route 11 warp was still relocating the player from `(4, 4)`
to the stable `(37, 31)` arrival tile. That input crossed straight back out, and the excluded-warp
guard stopped the run. Training now requires two consecutive input-ready reads on a stable cave
coordinate before its first encounter-seeking step. The next uncounted rehearsal proved that
`(37, 31)` itself is stable rather than transitional, so only the observed `(4, 4)` handoff is
excluded from that readiness gate. It also proved that stepping back onto `(37, 31)` after leaving
it activates the return warp. A third rehearsal proved the assumed northbound neighbor of
`(37, 30)` is blocked. The trainer now makes one verified step to that safe anchor, probes only
non-warp neighbors until one actually changes the observed coordinate, and remembers the inverse
step so every encounter excursion remains one tile from the anchor. A fourth rehearsal showed
that a wild battle can begin before the coordinate changes; that battle now counts as a successful
search action and preserves any already-known return direction across the battle.

The first bounded-recovery rehearsal correctly retreated before another faint and returned through
the Route 11 gate, but an unexercised shortcut then tried to walk south through the Vermilion Mart
at `(26, 15)`. The return now reverses the already-qualified eastbound Mart-to-Route-11 path to the
observed `(23, 14)` Mart exterior, then reuses the qualified Mart-to-Center path.

That route completed the staged development and reached the ship's second-floor rival corridor.
The first battle-state byte appeared one observation before the full RIVAL2 identity fields, so an
immediate checkpoint classified the boundary as unknown. Rival entry now waits without issuing a
battle choice until the complete opponent, trainer, and ship-script identity contract is
simultaneously true.

The resulting diagnostic proved the live opponent (`RIVAL2`), trainer class, trainer number, map,
coordinate, and ship script were all correct. Only the auxiliary engaged-trainer scratch fields
still held the preceding Route 6 trainer identity after the new wild-training block; one value
matched the old rival gate only by coincidence. Those stale fields are no longer treated as rival
identity. The live battle fields and ship-local script remain mandatory and are independently
regression-tested against the wrong opponent, class, and trainer number.

At level 30 the workhorse then defeated the rival without consuming the three-Super-Potion
reserve. The previous contract rejected that stronger outcome because it required all three items
to be deliberately wasted solely to recreate an older inventory shape. Recovery now proves the
exact adaptive decrement from zero through three uses and preserves every unneeded item for later
chapters.

Surge preparation now treats that legal carryover as funded capacity: it buys one Super Potion
only when the observed reserve is zero, otherwise preserves the existing one-to-three copies. The
Gym receipt checks the exact starting target minus the optional single live recovery instead of
assuming the route began with zero and must end with zero or one.

Lavender preparation likewise accepts the resulting zero-to-three carryover and buys only the
shortfall to its fixed ten-Super-Potion Rock Tunnel capacity. When two or more stronger items carry
in, it liquidates one obsolete 20-HP Potion for ₽150 to close the pre-trainer Repel budget without
weakening the high-value reserve. Its purchase receipt records the actual quantity and cost; the
later four-item reserve remains unchanged.

The stronger workhorse naturally reaches Blastoise before the historical Tower Rare Candy gate.
Tower now accepts either Wartortle or an already-evolved Blastoise at entry, initializes its party
guard from that observed legal lineage state, and records `(Blastoise, Blastoise)` as the evolution
receipt when no further transformation or candy use is needed. DUX, Diglett, party order, moves,
living HP, and the final Blastoise roster remain mandatory.

The retired v4 registry began with twelve fresh counted seeds. Its uncounted dry
seed `13001` deliberately replays that exact exposed v3 schedule. The teacher now heals at the
Center immediately before the accuracy-lowering trainer, may spend one of the already-budgeted
Route 24 Potions at a live low-HP MAIN boundary, and returns to the Center after the bridge when
that recovery was needed. Either branch proves the same four-Potion handoff before the Nugget
Rocket. The first v4 rehearsal survived the exposed damage sequence but revealed that the local
bridge loop left the main-command cursor on ITEM after recovery and repeatedly reopened the bag.
Stable MAIN states now pass back through the semantic move selector, which normalizes FIGHT and
proves the chosen move's PP decrement. The next replay passed both repaired trainers, then field
poison fainted Wartortle during the return walk to the Center. Route 24 now invokes the existing
exact Antidote cure at the stable post-bridge boundary before any movement, preserving all four
Potions and one Antidote for downstream routes. That replay then reached the Rocket thief, where
Drowzee sleep returned to MAIN between suppressed turns and exposed a dialogue-only recovery
assumption. The shared battle runtime now normalizes MAIN to FIGHT and MOVE to the latched legal
slot on every sleeping turn while preserving the exact unchanged-PP proof. The complete v4
rehearsal then cleared Rocket, both Route 6 trainers, and every earlier repair before the S.S.
Anne rival fainted Wartortle with Ivysaur at only 3/57 HP. The route now buys and carries one
additional Potion through every bounded handoff, giving that adaptive rival controller two
recoveries without making either use mandatory. The complete v4 rehearsal is still required
before any v4 counted slot can begin. That repair cleared S.S. Anne and Surge, then exposed a
five-turn sleep value (`0x05`) at the Rock Tunnel field-recovery boundary. Gen I stores remaining
sleep turns in the low three status bits, so the field recovery now treats every value from one
through seven as sleep, consumes the already-budgeted Awakening, and accounts for it exactly.
The following replay crossed that field gate, but DUX was paralyzed after reducing the final
trainer's Bellsprout to 3/57 HP and then fainted inside repeated Wrap. The two final Grass
trainers now enable the existing status-protection role pivot: once status makes DUX unavailable,
the healthy story lead owns the matchup for the rest of that battle instead of immediately
switching back into the impaired specialist.
That replay cleared all nine Tunnel trainers and reached Lavender, but the resource contract
correctly rejected zero remaining Awakenings: DUX had been awakened immediately during an earlier
battle despite a healthy reserve, then needed the second item at a later field boundary. Status
recovery now prioritizes the healthy party pivot and spends an Awakening only when no safe reserve
exists, preserving the declared Pokémon Tower contingency.
The next replay preserved that item but won final Tunnel trainer 5 after pivoting before DUX had
executed its declared Peck lesson. The physical victory was rejected rather than mislabeled.
Final-tunnel role reassignment is now gated on an observed PP decrement from the required DUX
move; once that evidence exists, the adaptive type/status pivots resume normally.
If the aggregate Lavender contract still fails after its individual gates, the retained private
diagnostic now reports the complete public-safe trainer, inventory, party, and route ledger rather
than a generic rejection, allowing the next repair to target the exact invariant.
That ledger proved all eleven trainer lessons, seven wild escapes, party state, healing, Repels,
and route gates passed; only the Tower reserve failed after two legitimate Awakening uses, with
`$1,761` still available after every other restock. The route therefore carries a three-item
total reserve and preserves one after the observed two-use lineage.
The first three-reserve attempt paid for four Repels but failed their inventory settlement after
changing the original Awakening quantity selector. Splitting the added copy into a final same-Mart
top-up proved the Repels but reproduced the unsettled Awakening stack. Buying two at the original
Cerulean stop then proved the early route did not yet have the extra ₽200. The extra copy is now a
separate Cerulean purchase after the Nugget Rocket reward: the earned Nugget is sold for its exact
₽5,000 value, the funded top-up carries two forward, and Vermilion performs its already-qualified
single-Awakening, two-Parlyz-Heal, four-Repel sequence to reach the same three-item reserve.
The same funded Cerulean top-up now adds one Potion for the mandatory Gym trainer. Route 25
consumes its planned recovery from six to five; the Gym controller may spend the fifth item only
at a live low-HP MAIN boundary under confusion, or use it as post-battle field recovery when the
lineage wins without crossing that threshold. Either path restores the exact four-Potion Rocket
handoff instead of weakening the downstream reserve.

Historically, the v3 registry had twelve fresh counted seeds. Its
uncounted dry seed `12001` deliberately replays the exact schedule that exposed the v2 failure;
none of its counted train, validation, or test seeds reuse a v1 or v2 assignment.
The first v3 rehearsal reached checkpoint 44 with Wartortle at 2/56 HP before the Nugget Rocket's
Ekans trapped and fainted it. The failed rehearsal remains private and uncounted. The already
budgeted Route 24 Potion is now consumed before that battle instead of after victory, preserving
the same four-Potion downstream handoff. The corrected source must repeat all 312 checkpoints and
attest all 68 battle offsets before any counted v3 slot can begin.
The next replay cleared both Rocket fights but reached the same exact-one-use assertion after the
first required Route 6 trainer. Route 6 recovery is now conditional under the identical live HP
gate, and unused Potions remain available to later objectives instead of being spent to normalize
an historical inventory count. The S.S. Anne rival may spend that bounded surplus repeatedly when
its live low-HP gate recurs, reusing one battle intent across recovery.
That correction carried the rehearsal through Surge and checkpoint 109 before Rock Tunnel B1F
trainer 5 status-locked DUX. The healthy Wartortle pivot then treated Bulbasaur as a generic
matchup and spent resisted BubbleBeam plus its two-heal allowance before fainting. Bulbasaur now
belongs to the reusable Grass-matchup set, so a replacement story lead ranks neutral Bite instead.
The failed rehearsal remains private and uncounted.
The next replay survived that matchup, then a still-paralyzed Wartortle lost its selected
BubbleBeam turn against B1F trainer 4 before the opponent self-destructed. Victory set the trainer
event without spending the required evidence PP. The route now cures supported status before the
self-destructing Hiker sequence and carries a second Parlyz Heal for the later Grass contingency,
preserving both executable teaching evidence and status robustness.
That replay then cleared Rock Tunnel, Rocket Hideout, and Pokémon Tower before consuming the
ten-Great-Ball reserve plus all surviving Poké Balls at the one-time Route 12 Snorlax. The teacher
now establishes a completion-oriented 25-throw combined reserve with a thirty-three-throw total
controller bound and sells the temporary remainder after capture. The static encounter no longer
depends on unbounded leftovers from earlier species searches.
An attempted thirty-ball reserve failed closed at the Mart because its ₽19,400 combined capture
and healing cost exceeded the live ₽16,897 balance. Twenty-five balls plus both Super Potions cost
₽16,400, retain the recovery contract, and require neither selling future-use TMs nor relying on
earlier Poké Ball leftovers.
The funded replay caught Snorlax in six throws and continued through Koga and the Celadon Gym
trainers before a wandering Center NPC occupied the first exit tile beyond the original eight
bounded waits. Movement now retains the same release-and-observe semantics with sixteen bounded
waits, covering a complete longer NPC cycle without teleporting or changing the route.
The exact replay showed the NPC can remain parked while the player waits directly above it even
through that longer window. The second Center exit now uses the legal open side corridor around
the occupied tile and rejoins the same doorway below it; no collision retry or NPC timing is
required for that handoff.
The first side-detour rehearsal reached checkpoint 223 but could not move left; the exact right-side
replay failed at the same coordinate, proving those apparent alternatives were structural walls.
Because the party is healed immediately before the hazard-free rooftop TM exchange, the exchange
now verifies that state and returns only to the Center entrance instead of performing a redundant
second nurse visit. The doorway is then one step away. This remains an uncounted source repair and
requires a new exact dry qualification.
That entrance-return lineage cleared Erika and formed the complete six-member party, then reached
Sabrina at checkpoint 261. A Hyper Potion wait exhausted its pre-action samples even though the
diagnostic reread already showed the main battle phase. The bounded recovery now accepts a main
menu reached by the final cancel pulse, while the independent exactly-once item-decrement contract
is unchanged. This late failure was also uncounted and requires another exact dry qualification.
The post-observation replay then showed the underlying Sabrina strategy could consume all seven
Hyper Potions while falling below the same threshold after every enemy reply. The Celadon purchase
now reserves three X Specials: one for the Silph rival and two independently verified setup uses
for Sabrina. This staged Special-defense lesson changes the battle state instead of extending an
unproductive healing loop, and the exact source again requires full dry qualification.
The staged replay defeated Sabrina and reached checkpoint 275 before a Mansion encounter Disabled
the lead's last preferred move with PP. Lead training now uses battle-active PP, excludes only a
currently disabled slot, and performs a bounded flee when no legal preferred attack remains. This
aligns the lead block with the existing balanced-team recovery semantics and requires another
uncounted exact-source qualification.
That replay completed the level-75 six-member curriculum and reached checkpoint 296 before the
Indigo shop lacked ₽611 for two Revives. The final economy now sells leftover Antidotes and buys
two Full Heals instead of three while preserving six Full Restores, eleven Hyper Potions, both
Revives, and every League setup item. This uncounted repair keeps the capture and balanced-team
contracts intact and again requires complete exact-source qualification.

The now-retired v2 registry began as a prospective campaign with fresh counted seeds.
Its first uncounted dry run reached checkpoint 70 before a walking Cerulean NPC blocked the Route 6
healing-replay corridor. The failed private artifact is retained. A bounded yield-and-retry repair
then carried that exact rehearsal schedule through the next checkpoint. The registry below binds
the repaired source; it still requires a new complete dry run, and all twelve counted slots remain
unexecuted. The next replay cleared that collision, reached checkpoint 91, and then exhausted the
25-ball Forest capture reserve while attempting Pikachu. The repaired source raises that legal
reserve to 30 and expands the later bounded cleanup gate accordingly; its downstream economy is
part of the next required full rehearsal. The longer purchase cadence also shifted Route 11 and
reached the old 72-encounter Spearow cap; the repaired source gives that search a dedicated
96-encounter bound while retaining the exact species and level requirement. This remains a plan, not a held-out-result claim, and
contains no trajectory, ROM, snapshot, private path, or completion evidence.
That replay then cleared both capture curricula and reached the live Lt. Surge battle. Diglett
defeated the first opponent with 10/30 HP remaining, but the next opponent moved before its third
Dig and knocked it out. The teacher now performs one bounded Super Potion recovery only from a
proven low-HP MAIN battle gate, verifies both the HP increase and inventory decrement, and resumes
the Dig-only plan. The complete v2 rehearsal remains the next qualification gate.
The exact replay proved that recovery and the Dig-only victory through checkpoint 97. The
following Lavender entrance then rejected the correctly depleted potion slot because its legacy
handoff allowed only one remaining Super Potion. That boundary now accepts either zero or one and
still restores the observed quantity to the same fixed twelve-potion downstream reserve with an
exact money-and-inventory proof.
That replay reached checkpoint 102 and proved the handoff, then showed that blindly replacing the
consumed potion would exceed the exact early-game budget by ₽409. The intermediate repair retained
the planned tunnel allocation regardless of whether Surge consumed the carried reserve, recorded
the observed zero-or-one starting quantity explicitly, and proved the conservation equation
`starting + purchased - used = remaining`. Lavender still tops the result back to twelve after
selling TM28, so the downstream reserve is unchanged.
The next replay proved that the 30-ball capture curriculum also displaced ₽1,400 needed for four
Rock Tunnel Repels. Historical qualified recovery evidence used five Super Potions across this
chapter, and the live contract already requires at least five at Route 9. The purchase therefore
allocates ten Super Potions plus the observed starting remainder, preserving a two-times safety
margin and all four Repels; the later exact top-up still restores twelve.
That replay validated the complete economy repair through Rock Tunnel and continued to checkpoint
220. Koga's terminal mutual-KO recovery had completed the physical battle outside the adaptive
turn loop, but had not closed the collection schedule lifecycle; the next Erika battle therefore
failed closed as an apparent intent change. The externally settled trainer exit now closes the
matching already-applied schedule entry exactly once, alongside the existing observer lifecycle.
The following exact replay proved that repair, defeated Erika, and reached checkpoint 230 before a
moving fourth-floor department-store customer occupied the evolution-stone clerk route. A bounded
eastward yield maneuver now preserves and restores the exact approach coordinate until the customer
vacates the single blocked tile.
That replay proved the yield, entered Silph Co., and reached checkpoint 243 before the rival
knocked out Blastoise with 17 enemy HP remaining. The bounded rival controller now treats the live
active battler—not only the field lead—as its recovery subject, selects the healthiest living
reserve from the forced-switch menu, and resumes with that reserve's actual PP. This is a reusable
full-party lesson rather than another lead-only retry.
The first replay of that lesson proved the knockout branch but showed that Gen I presents bounded
faint dialogue before the forced party cursor accepts movement. The selector now interleaves a
periodic confirmation with cursor normalization, matching the already-qualified Koga mutual-KO
pattern while still proving the chosen living reserve and restored MAIN state.
The next replay reached the same turn with both Blastoise and the rival's final Pokémon at zero HP.
That terminal mutual-KO is now distinct from a mid-battle KO: the teacher selects a living reserve,
accepts the proven battle exit instead of requiring another MAIN menu, and closes the matching
Silph schedule and observer lifecycle exactly once.
That repair proved the rival victory at checkpoint 244, but post-battle text still owned input when
the elevator route began. Terminal recovery now clears bounded dialogue and requires two consecutive
field-readiness observations before any navigation, matching the normal adaptive runtime contract.
The next exact rehearsal proved that repair, completed the six-member balancing block with every
trainee in the upper seventies, defeated Blaine and Giovanni, crossed Victory Road, and reached
checkpoint 296/312. The expanded bounded capture curriculum legally consumed all thirty Poké
Balls, but Indigo cleanup still required at least one leftover before opening its sale path. The
cleanup contract now accepts the complete zero-through-thirty remainder range, skips the sale when
the stack is empty, and retains the exact downstream supply checks. The failed rehearsal remains
private and uncounted; this corrected exact source must repeat the full dry run before slot `01`.
That replay again reached checkpoint 296 and accepted the empty stack, then exposed that the old
positive-sale branch had also supplied an implicit menu transition: cancelling after a completed
sale returns to BUY/SELL, while skipping the sale leaves field control at the clerk. The zero path
now interacts with the clerk explicitly before selecting BUY; the positive path retains its
cancel-to-menu transition. The second failed rehearsal also remains private and uncounted.
The corrected v2 source then completed **312/312 checkpoints**, **36/36 objectives**, Hall of Fame,
and a **68/68** offline schedule audit, publishing the required dry-run qualification. Its first
immutable training slot reached checkpoint 62 before Drowzee defeated a 0/66-HP Wartortle with
24/50 HP remaining. That failed outcome is retained in the private v2 ledger and makes v2
ineligible for the required five complete training roots. The teacher now carries one additional
already-owned Potion out of the Cerulean reserve, spends it at the Rocket thief's live low-HP MAIN
gate only when needed, and ranks the stronger Mega Punch after the required one-use Bite lesson.
A v3 campaign with fresh counted seeds must qualify this repair; the v2 slot is never rerun.

The latest v4 clean-power rehearsal passed the repaired Cerulean economy, Misty, the Rocket route,
the S.S. Anne, and the Diglett curriculum through checkpoint 91 before one level-6 Kakuna consumed
the six Poké Balls left by earlier captures. The generic source adapter had allowed a single
full-health encounter to spend the complete campaign remainder. It now caps one encounter at five
throws, verifies the exact decrement, and returns a failed bounded attempt to the area survey as a
fresh-encounter retry rather than false capture progress. This applies to every live wild-source
survey; the private failed artifact remains uncounted and the modified source must requalify the
complete 312-checkpoint/68-battle rehearsal.
That retry-capable replay returned to checkpoint 91 and then reached the Forest's older 64-leg
physical traversal bound. Because failed capture attempts now legally seek a fresh specimen, the
Forest permits 256 finite corridor legs while retaining its independent 1,000-encounter and
20,000-action ceilings. Collection changes remain accepted only after exactly one new retained
specimen appears.
The expanded traversal then reached the independent 20,000-action ceiling after the finite reserve
had already been consumed across several full-health encounters. The source adapter now applies
the portable capture policy instead of extending search again: it chooses a healthy low-level
Rattata, Caterpie, or Pidgey, performs one verified Tackle or Gust weakening action, proves the PP
decrement and target damage, and only then enters the five-throw budget. A knockout returns as a
fresh-source retry without collection progress, and an empty reserve fails immediately.
The first live weakening attempt arrived during wild-introduction dialogue rather than MAIN. The
adapter now preserves the encounter identity and party, invokes the existing bounded battle-menu
normalizer, and applies its strict helper-switch gate only after PARTY-selected MAIN is observed.
That normalized replay exposed that the shared navigator had no PARTY destination because earlier
callers used only FIGHT, ITEM, and RUN. PARTY now has an explicit bounded transition from each
main-command position before the adapter opens the helper list.
That route then proved repeated one-PP weakening hits before a failed Pikachu throw let the 1-HP
Rattata helper faint. After target damage is proven, the adapter now uses the same verified party
transition to restore the healthy story lead before any ball is thrown. The helper teaches the
weakening action but does not absorb the complete retry sequence.
A later faster Pikachu knocked out Rattata before Tackle executed. Forced-switch recovery now
selects the protected lead through a verified live party cursor. Target damage plus PP decrement
decide whether capture may continue; otherwise the restored lead flees and the survey retries a
fresh specimen without crediting a capture.
The first forced-switch attempt saw the stale move-menu cursor address immediately after fainting.
It now advances at least one bounded faint-dialogue transition before a live party cursor can be
accepted, while retaining the cursor-tile, party-range, species, and target-HP gates.
Because the first confirm left the full snapshot and cursor pointer unchanged, elapsed attempts are
no longer accepted as progress. The pre-faint cursor address is retained and party selection is
permitted only after a different valid live cursor address appears.
The exact branch remained unable to restore MAIN because Pikachu could outspeed and knock out the
low-level helper before it acted. Pikachu is now a Red-adapter direct-throw target behind the
durable lead. Passive Metapod and Kakuna still exercise weaken-then-throw; the threatening target
uses its high catch rate and the same five-throw limit without deliberately sacrificing a helper.

One invocation against the superseded registry
`24520b0f5cfb027cf1339261a179650cda6e7792058af148af8722333bfdf72b` stopped before
the episode header or emulator startup because the path-free serializer rejected a canonical
relative PyBoy inventory name. Its failed private artifact is retained, but it contains no
gameplay, schedule application, campaign seal, or declared-slot outcome. This revision permits
only validated location-free distribution inventory names at the exact structural runtime field;
absolute paths, traversal, spoofed keys, and every other path-bearing field remain invalid. The
registry below supersedes that preflight-only identity.

The exact source and configuration commit must be committed and pushed to GitHub before the
schedule dry run or any declared attempt begins. The command verifies that the clean local commit
is reachable from a remote-tracking branch. The registry loader resolves that commit once, reads
the registry and executable source from that exact object ID, and carries the same object ID
through metadata construction; a concurrent commit or checkout change fails before execution.
That pushed Git commit—not the co-committed digest
sidecar by itself—is the public preregistration anchor. Every dry-run header records the commit,
registry digest, and teacher-execution digest. Before slot `01`, the private campaign seal fixes
that exact source commit and registry digest for all twelve outcomes. If executable source,
behavior, objective graph, roster, assignment, or schedule changes before collection, regenerate
and publish the registry and sidecar first. Once a counted slot has started, such a change requires
a new registry version rather than replacement of the observed result.

## Canonical byte convention

Every content-addressed JSON document below uses the same canonical newline encoding. For a JSON
value `x`, define:

```text
C(x) = json.dumps(
    x,
    allow_nan=False,
    ensure_ascii=True,
    separators=(",", ":"),
    sort_keys=True,
).encode("ascii") + b"\n"

D(x) = lowercase_hex(SHA256(C(x)))
```

`C(x)` therefore has sorted object keys, compact separators, ASCII escaping, no non-finite
numbers, and exactly one trailing line feed. Array order remains significant. The registry itself
must equal `C(registry_object)` byte for byte. Generated values remain in the canonical registry
and sidecar; `scripts/regenerate_collection_registry.py --check` independently rebuilds the
prospective bytes and fails when they are stale.

## Frozen public identity

The prospective campaign published by this version has these independent golden values:

| Field | Frozen value |
| --- | --- |
| Registry bytes | `6659` |
| Registry SHA-256 | `9d35da5744953dc172da54731d6a44cab88bcc24b5ac315e6cb9ba6751cffe98` |
| Source bundle SHA-256 | `87fd4e04b21ea639a8798f1c58923aaab2877daca239dae05bf52bf15a7bd886` |
| Behavior configuration SHA-256 | `6b1ead4078541ca953ed432e90c175710d4c4f7a2b096f14ed9ed5cb6c71b39d` |
| Objective graph SHA-256 | `453ba1dcecbb33df9e10a911ac93090ff9a5080b07e02a5594e34a015e5bd3b6` |
| Teacher execution SHA-256 | `406e2bed217f20e17d330d93ba0a9d7c4dc444bf62357dd2cf27127c8680cf51` |
| Dry-run schedule SHA-256 | `7fdf8905f235b1e25e1f58595a986b7d16a2da91dbaa741d587870a304ed47d4` |
| Slot `01` assignment ID | `fb33b30d44ca47f0e078d1d99afd92675b9847dbdd26789e7e3c64ca7a60fc99` |

The tests independently pin these values so an accidental registry, source, behavior, objective,
or assignment change fails before collection.

## Exact content-addressed identities

### Battle roster and schedules

The roster digest is:

```text
D({
  "battle_plan_ids": [the exact 71 IDs in qualified route order],
  "schema": "pokemon-red-battle-plan-roster-v1"
})
```

The array must equal the 71-entry `RED_BATTLE_PLAN_IDS` tuple exactly. A missing, duplicated,
substituted, or reordered ID is invalid even if the array length remains 71.

For each roster ID, `sha256-mod-v1` derives a frame offset from 0 through 255. The SHA-256 input is
the following exact byte concatenation:

```text
ASCII("pokemon-red-battle-start-offset-v1")
+ NUL
+ harness_seed as exactly 8 unsigned big-endian bytes
+ NUL
+ ASCII(battle_plan_id)
```

Interpret the first eight digest bytes as an unsigned big-endian integer and reduce modulo 256.
The expanded schedule digest is:

```text
D({
  "offsets": [
    {"battle_plan_id": ID_01, "frames": OFFSET_01},
    ...,
    {"battle_plan_id": ID_68, "frames": OFFSET_68}
  ],
  "schema": "pokemon-red-battle-start-offset-v1"
})
```

The registry commits the complete expanded-schedule digest, not merely its seed. Seeds and
schedule digests are unique across all twelve counted slots. The fixed dry-run seed and schedule
digest are also disjoint from all twelve.

### Executable source bundle

The source bundle is computed from one resolved Git commit. Its inventory contains
`pyproject.toml` and every regular committed blob below `src/pokemon_red_completion/`. Collection
configuration is deliberately outside this bundle to avoid self-reference. For each blob:

```text
{"bytes": exact_blob_length, "mode": "100644" | "100755",
 "path": ASCII_git_relative_path,
 "sha256": lowercase_hex(SHA256(exact_blob_bytes))}
```

Sort entries lexicographically by `path`, then compute:

```text
D({
  "files": [sorted file entries],
  "schema": "pokemon-red-executable-source-bundle-v2"
})
```

The registry loader resolves one `HEAD` commit and recomputes this digest from that commit's Git
blobs. Immediately before a scheduled run, the command also hashes the live working files,
including untracked source, rejects ignored executable content, and requires exact equality with
the committed bundle. Uncommitted or ignored working-tree content cannot satisfy the frozen
execution identity.

### Teacher behavior configuration

The behavior digest is:

```text
D(the exact "behavior_configuration" object)
```

That object uses schema `pokemon-red-teacher-behavior-v1` and fixes the emulator name and version,
disabled human input, disabled save-on-exit, the new-game/opening/play timing maps, the pinned
pret/pokered commit, and the battle-schedule application schema. Window visibility and playback
speed are presentation metadata, not part of the behavior digest; changing them does not change
the teacher policy.

The objective-graph digest uses the same encoding and an explicit domain schema:

```text
D({
  "objectives": [the exact topologically ordered public objective payloads],
  "schema": "pokemon-red-objective-graph-v1"
})
```

Each objective payload includes its identity, title, specialist, sorted prerequisites, and sorted
completion facts.

The teacher execution digest is:

```text
D({
  "actor": ACTOR,
  "adapter_id": ADAPTER_ID,
  "behavior_configuration_sha256": BEHAVIOR_DIGEST,
  "collection_id": COLLECTION_ID,
  "game_id": GAME_ID,
  "objective_graph_sha256": OBJECTIVE_GRAPH_DIGEST,
  "ontology_id": ONTOLOGY_ID,
  "policy_id": POLICY_ID,
  "schema": "pokemon-red-teacher-execution-v1",
  "source_bundle_sha256": SOURCE_BUNDLE_DIGEST
})
```

Every counted assignment binds this single execution identity.

### Registry sidecar

The registry digest is SHA-256 over the exact canonical registry bytes. The sidecar must itself
equal:

```text
C({
  "bytes": exact_registry_byte_length,
  "schema": "pokemon-red-collection-registry-digest-v1",
  "sha256": lowercase_hex(SHA256(exact_registry_bytes))
})
```

The loader resolves one commit, reads and validates the canonical sidecar first, reads the
registry from the same commit, authenticates its exact byte length and SHA-256 before parsing it,
then checks that the execution contract names the source bundle recomputed from that commit.
Because registry and sidecar are committed together, this is an authentication and corruption
check rather than an independent timestamp. The pushed commit is the public anchor, and the
write-once private campaign seal prevents a different registry or source commit from replacing it
after collection begins.

### Assignment, lineage, and episode identity

For a declared run, the assignment digest is:

```text
D({
  "collection_id": COLLECTION_ID,
  "harness_seed": UINT64_SEED,
  "partition": "train" | "validation" | "test",
  "registry_sha256": REGISTRY_DIGEST,
  "run_id": RUN_ID,
  "schedule_sha256": EXPANDED_SCHEDULE_DIGEST,
  "schema": "pokemon-red-collection-assignment-v1",
  "teacher_execution_sha256": TEACHER_EXECUTION_DIGEST
})
```

The private root-lineage ID is `red-root-<assignment digest>` and the private episode ID is
`red-teacher-<assignment digest>`. Metadata also records `attempt.counted=true`,
`attempt.attempts_per_slot=1`, the global slot ordinal and total, and the partition-local ordinal
and total. These fields are derived from the authenticated registry rather than accepted as
mutable command-line labels.

## Mandatory schedule dry run

Before global slot `01`, run the registry-declared schedule integration dry run:

```bash
pokemon-red-completion record \
  --private-root /absolute/private/trajectory-directory \
  --schedule-dry-run
```

It is a clean-power-on, full-route rehearsal using the same frozen execution contract and the same
71-ID instrumentation path, but the fixed seed `62001` and its distinct schedule. Its metadata is
`partition=unassigned` and `attempt.counted=false`, and explicitly binds the registry, source
commit, source bundle, behavior, objective graph, and teacher-execution digests. It must not enter
train, validation, or test data, and it must not enter any performance denominator. A normal
unplanned recording is not a substitute.

The dry run must finish successfully and attest all 71 offsets before slot `01` starts. A failed
dry run does not consume a declared slot, but collection must pause until the defect is corrected.
Any correction to a frozen input must be committed, pushed, and reflected in a regenerated
registry and sidecar before repeating the dry run.

After the complete episode and all 71 attestations pass their offline audit, the recorder publishes
a separate immutable dry-run qualification in private storage. It binds the registry, exact source
commit and execution digests, CPython/PyBoy runtime, ROM hashes, dry seed and schedule, episode ID,
manifest digest, and 71/71 audit receipt. Before any counted slot can create the campaign seal or
episode namespace, the command reopens that referenced episode and reruns the audit under the same
exclusive collection session. Absence, identity drift, replacement, or malformed evidence fails
closed. This qualification is not a campaign outcome and never enters an evaluation denominator.

## Runtime schedule attestations

At the first stable main battle menu, before the policy's first choice, the runtime claims the
next roster offset. A positive offset is executed as a normal `WAIT` through the frame-safe
executor; a zero-frame offset creates no fake execution. In both cases the semantic state is read
again before policy inference. Re-entry into the same physical battle never reapplies the offset.

Each application produces exactly one private `battle_start_offset_applied` event containing:

- `battle_ordinal`, `battle_plan_id`, `frames`, and `schedule_sha256`;
- `before_snapshot_sha256` and `after_snapshot_sha256`; and
- `execution_step_index`, which is `null` for zero frames and otherwise identifies the preceding
  `WAIT` execution.

The terminal event must contain a `battle_start_schedule` attestation with `complete=true`,
`expected_battles=71`, `finished_battles=71`, and the same schedule digest. Duplicate or unknown
IDs, intent changes, schedule mismatch, reordering, substitution, partial application, an extra
battle, or an unfinished schedule fails the attempt.

After the episode is atomically published, an offline audit rereads the durable artifact. It
requires the real trajectory header/event/execution schemas and content-addressed snapshot records;
synthetic rows that the production sink could not emit are invalid. For
every positive offset it requires the linked execution to be a successful, decision-free
`WAIT(repeat=frames)` with exactly the declared frame count and matching before/after snapshot
hashes. A zero offset must have no execution link. Because the runtime rejects policy-visible
drift during an offset, every attestation must have identical before/after policy snapshots. The
same audit authenticates the header's complete offset array and the sole terminal event. A
metadata-only claim therefore cannot pass.

## One-shot accounting and power-loss recovery

Before the first counted attempt, a private immutable campaign seal binds the collection,
registry, exact pushed source commit, source bundle, behavior, objective graph, teacher execution,
runtime, ROM, and complete twelve-slot roster identities. Runtime identity includes the CPython
implementation/version, exact interpreter-binary digest, PyBoy version, and a canonical digest
inventory of installed PyBoy files. Each assignment is then a single-attempt namespace. The outcome ledger
classifies every consumed slot as `complete`, `failed`, `interrupted`, or `invalid`, retains an
explicit reason code, and exposes a path-free receipt with all twelve slots and all pending and
terminal counts.

A process interruption or power loss does not create permission to rerun the same seed. On the
next reconciliation, a valid completed manifest left in a partial directory can be recovered as
complete; a finalized failure remains failed; and an unsealed orphan partial is classified
`interrupted` with the corresponding ledger rationale. Failures, invalid artifacts, and
interruptions consume their slot. Replacing any such outcome would permit outcome-dependent
cherry-picking, so a protocol restart requires a new registry version.

The deterministic partial episode directory is the start claim. Its directory metadata and the
private-root directory entry are synchronously persisted before emulator execution can begin. A
power loss therefore cannot turn an already-started counted attempt back into an absent slot.
Completion validation also recomputes the recorded runtime-document digest and requires the
top-level source, objective, behavior, assignment, and schedule identities instead of trusting
detached digest copies.

The public receipt's `ledger_sha256` is `D(core_receipt)`, where `core_receipt` is the complete
path-free ledger object before its `ledger_sha256` field is added.

The current state can be reconciled without starting a slot:

```bash
pokemon-red-completion collection status \
  --private-root /absolute/private/trajectory-directory
```

The ROM may be supplied with `--rom` or `POKEMON_RED_ROM`. Before a campaign exists, this command
reports twelve pending slots without creating a seal. Afterward it verifies the frozen campaign
identity and safely classifies any power-loss partial before returning the path-free ledger.

## Analysis and claim boundary

The current feature schema is `pokemon.core.battle.move-ranker.v2`. It retains goal and move-policy
context and adds the candidate-relative feature `constraint.matches_required_move`.
`exact_required` decisions are forced choices; `any_usable` decisions are free choices. Collection
and model receipts report the counts and accuracies separately, including unobserved-context
counts. Forced-choice accuracy measures compliance with a teacher-supplied constraint and cannot
stand in for autonomous move selection; free-choice accuracy is the more relevant generalization
measure. Overall accuracy remains descriptive.

`teacher_recovery_marker` currently records only `none` or `bounded_recovery`. It is descriptive
metadata, is not a model feature, and does not encode a typed recovery budget or envelope. It
cannot by itself establish recovery-policy coverage or qualify a recovery learner.

Exact episode, manifest, assignment, schedule, or root-lineage reuse across partitions is hard
leakage and fails the audit. Repeated policy-visible semantic snapshot hashes can occur naturally
under distinct hidden timing/RNG schedules, so their overlap is report-only. Reports must disclose
the visible-overlap count and performance on novel visible states separately; visible semantic
overlap alone is not grounds to discard or replace a preregistered attempt.

Disjoint preregistered lineages are necessary but not sufficient for promotion. Model selection
uses train and validation only; the five test slots remain unopened until the feature schema,
model, thresholds, and analysis rules are frozen. Promotion additionally requires a
registry-authenticated corpus audit and learned battle rollouts with teacher fallback disabled.
The implemented `learn battle fit` command enforces that boundary: it requires all seven learning
outcomes, rejects any consumed test slot before loading a dataset, and publishes only a private
candidate plus aggregate validation evidence. It has not executed while the campaign is pending.

The current uncounted qualification replay also validates conservation across curriculum stages.
After the revised early capture policy passed its former Viridian Forest bottleneck, it retained
15 unused Poké Balls but lacked the cash required by the fixed Rock Tunnel supply contract. The
teacher now sells 14 at the Vermilion Mart, retains one legal capture/capacity token, proves the
corresponding inventory and money deltas, and then proves the full supply-purchase ledger. The later
Snorlax capture remains isolated behind its own Great Ball budget, so this conversion cannot
silently spend a future capture reserve.

That exact replay proved the sale and purchase ledger at checkpoint 103 and reached Rock Tunnel
trainer 5 at checkpoint 109. DUX escaped after becoming paralyzed, but the replacement Wartortle
was also paralyzed and fainted after lost turns. The live battle adapter now distinguishes sleep
from paralysis, spends only the surplus second Parlyz Heal at a verified main-menu gate, proves
the cure and item decrement, and retains one cure for the later tunnel evidence battle. This was
an uncounted failure; the source must repeat the full dry qualification.

The next replay passed that battle and every chapter through checkpoint 271 before exposing a
15-slot Cinnabar bag against the qualified 16–19-slot capacity curriculum. Retaining exactly one
early Poké Ball preserves the later full-bag reward lesson without introducing a new Cinnabar
purchase: it is legal backup for Snorlax, survives the Great Ball cleanup, and is sold by the
existing Indigo normalization. The observed 14-ball sale still funds all required Repels.

Retaining that token shifted later battle timing and exposed Rocket Hideout Giovanni's historical
helper-sacrifice recovery path at checkpoint 136. The teacher now invokes the same reusable
recovery primitive in preservation mode: a living helper absorbs only the item-turn reply, the
lead's exact Super Potion use is proved, the lead is restored immediately, and one attack must
follow before another recovery. This aligns the rehearsal with the balanced-party objective and
keeps the original finite item reserve; the failed replay remains uncounted.

That repair passed Giovanni and Pokémon Tower before the Snorlax restock exposed a ₽100 shortfall.
The earlier Lavender top-up had been adding one Parlyz Heal regardless of whether Rock Tunnel
consumed any. It now restores a fixed two-cure reserve instead: zero consumed means zero repurchased,
one consumed means one repurchased, and the exact cash and inventory ledger is still mandatory.
This saves ₽200 on the observed no-cure schedule while preserving both cures, the capacity token,
and the full later capture/recovery budget. The replay remains uncounted.

The replay still fell ₽403 short of its second Snorlax Super Potion because it bought the older
25-Great-Ball reserve in addition to the retained capacity ball. The purchase now binds the same
25 legal throws as before—24 Great Balls plus that one Poké Ball—saving ₽600 while remaining seven
throws above the historical 18-throw exhaustion. Both recovery items remain mandatory and the
controller's independent thirty-three-throw ceiling is unchanged.

The funded replay caught Snorlax in three throws and reached the Silph rival at checkpoint 243,
where Venusaur fainted the lead after the two-item recovery budget was exhausted. The teacher now
keeps the healing and party-depth bounds separate: it still spends at most two Hyper Potions, then
uses the existing verified forced-switch path for at most four living reserves without reopening
recovery. This is balanced-party continuity, not a larger healing or retry allowance. The failed
replay remains uncounted.

The corrected v4 source subsequently passed all 312 checkpoints, 36 objectives, and the 68-battle
dry-run audit. Its first one-shot training slot then failed at Route 24 trainer 1 after Wartortle
entered the final bridge fight without another Center recovery. That outcome is retained in the
v4 ledger and is never rerun. Because v4 can no longer provide five complete training roots, the
teacher now reuses its verified bounded Center backtrack before the final bridge trainer and must
publish and qualify a fresh registry before collection restarts.

V5 then froze disjoint seeds and its new uncounted schedule reached the Cerulean rival with
Pidgeotto at 6 HP when Wartortle exhausted its protected Potion allowance and fainted. The living
Zubat helper was already part of the qualified party and accuracy-reset curriculum, but had no
post-KO continuation. The teacher now preserves the exact Route 24 Potion reserve, performs at
most one observed forced switch to that helper, and chooses a legal move from the active battler's
live move/PP evidence. The failed qualification is uncounted; v5 must be regenerated and replayed.

That replay proved the helper switch and one legal Zubat attack, but the helper also fainted. The
underlying defect was an unproductive recovery loop: every enemy reply could leave Wartortle below
the same threshold and immediately trigger another Potion without an intervening attack. Rival
recovery now latches one mandatory legal attack after every exact Potion use. No item, healing,
switch, or retry bound is increased; the helper path remains only a final contingency.

With that latch, v5 cleared the rival, all five Route 24 trainers, Misty, and reached the Rocket
thief at checkpoint 62. Drowzee's Sing counter decreased normally but the former single 48-pulse
allowance expired with one sleep turn remaining. The runtime now derives a finite total allowance
from the observed Gen I three-bit sleep counter, giving each represented turn the same transition
budget. Complete PP-vector preservation, monotonic countdown, live-HP, and menu-state checks remain
mandatory, so the change accommodates legitimate multi-turn sleep rather than weakening progress
evidence. This qualification attempt is also uncounted.

The sleep-scaled replay then cleared that failure and progressed through the S.S. Anne and the
capture/trade setup before all thirty Poké Balls were exhausted in the Forest collection lesson
after checkpoint 91. The semantic policy requested weakening to a health threshold, but the Red
adapter performed only one low-level attack before throwing; passive Metapod and Kakuna could
therefore consume five-ball attempts while still near full health. The adapter now replans after
every verified damage action. Passive cocoon targets use a 50% threshold under an eight-attack
maximum, Caterpie retains the lighter 85% lesson, and dangerous Pikachu remains a direct throw
behind the healthy lead. Exact PP loss, target damage, encounter identity, and all finite throw
bounds remain mandatory. This qualification attempt is uncounted as well.

The first deeper-weakening replay reached a passive Kakuna but then exposed MOVE again after a
completed hit. The one-action verifier had treated every non-MAIN phase as dialogue, so confirming
that stale move selection issued additional attacks and correctly violated the exact-one-PP-loss
contract. MOVE now receives CANCEL back to MAIN; only UNKNOWN dialogue receives bounded
confirmation. A subsequent attack can be selected only by the outer policy after it replans from
the newly observed HP ratio. This qualification attempt is private and uncounted.

The cancel-aware replay then observed an ordinary Tackle miss against Kakuna: exactly one PP was
spent, target HP remained 22/22, and stable MAIN returned. The verifier had no terminal miss state,
so it waited for damage until its finite settling bound expired. PP loss plus stable MAIN now proves
that the one selected turn completed; unchanged target HP classifies it as a miss. The adapter
restores the protected lead, flees, and asks the area policy for a fresh encounter without claiming
damage or capture progress. Regression cases separate hit, miss, and pending MOVE states. This
qualification attempt is also private and uncounted.

The miss-aware replay completed every Forest root, defeated Surge, and reached checkpoint 102, but
only five of the original thirty Poké Balls survived. Selling the four-ball surplus plus the Nugget
left ₽591 after protected healing and status supplies, so the four-Repel purchase failed closed.
The route does not reduce those downstream reserves. Pikachu is now a high-risk weaken-and-throw
target instead of a direct throw: only a low-level helper above 75% HP may participate, with the
verified forced-switch/flee contingency protecting the party. Ordinary targets use a 65% threshold
and passive Metapod/Kakuna use 30%, under the same exact PP/damage evidence and eight-attack bound.
This qualification attempt is private and uncounted.

That replay funded the complete Tunnel reserve, cleared Rock Tunnel, Rocket Hideout, and Pokémon
Tower, then reached checkpoint 172. The Snorlax restock bought 24 Great Balls, but the chained
product transition remained on Great Ball and bought a 25th instead of opening the two-Super-Potion
purchase. Even without that extra ball, the live ledger was ₽779 short. The route now sells unused
TM34 Bide for its exact ₽1,000 proceeds and reopens BUY from a verified field boundary between
product stacks. At Cinnabar, one Great Ball replaces Bide's unique capacity slot and is sold after
Blaine, preserving the full-bag delayed-TM38 lesson. The ledger accounts for the replacement's
₽1,300 net difference; the 24-Great-Ball plus retained-Poké-Ball capture depth and both recovery
items are unchanged. This qualification attempt is private and uncounted.

The Bide-funded replay then bought the intended reserve, caught Snorlax in five throws, completed
Safari, Koga, and Erika, and reached Saffron at checkpoint 239. Exact follow-up diagnostics proved
the bag had only fourteen occupied slots and the Helix Fossil was absent: capacity was already
safe, but the cleanup incorrectly required a fixed three-item checklist. The cleanup now proves
the actual sixteen-slot requirement first, performs no PC transaction when already safe, and
otherwise deposits only enough available obsolete route items to reach the bound. Unsupported
over-capacity states still fail closed. This qualification remains private and uncounted.

The next replay passed that boundary, liberated Silph, completed the Fighting Dojo, defeated
Sabrina, and reached the Mansion development block. It was stopped safely after 1,250 of the old
equal-level battles when the active curriculum changed; no declared slot opened. The next v5
candidate instead requires the exact six-species final-form roster, zero faints, and a level-75
Blastoise workhorse. Already-final non-workhorses are not forced to match its level. The reusable
planner can request recruitment, evolution, restoration, workhorse switching, or workhorse
training, while the older equal-level policy remains available for separate experiments. Its first
replay correctly rejected level-20 Diglett after Blastoise reached 75; the Red adapter now executes
a bounded, zero-faint, targeted Mansion lesson until Dugtrio is observed, without grinding the four
already-final non-workhorses.

That revised v5 qualification completed the entire game. The first counted v5 training root later
failed at the S.S. Anne rival with Ivysaur at 23/57 HP after Wartortle fainted. Decision snapshots
showed that Pidgeotto had reduced accuracy twice, Kadabra consumed the retained healing reserve,
and Mega Punch's lower accuracy prolonged the final matchup while Leech Seed restored Ivysaur.
Teaching the already-owned TM11 before boarding now replaces Mega Punch with BubbleBeam: the
teacher uses BubbleBeam against Pidgeotto and Raticate, Bite against Kadabra and Ivysaur, and keeps
Water Gun as a legal fallback. This changes no purchase budget or retry allowance. V5 remains
immutable; the repair belongs exclusively to v6.

The first v6 dry rehearsal learned BubbleBeam and reached the dock, but the dock checkpoint rejected
the otherwise-valid state because its inherited Cascade invariant still required the consumable
TM11 item to remain in the bag. The invariant now accepts either the unspent TM or observed
BubbleBeam in the lead's live moveset. This preserves proof of the lesson instead of confusing item
consumption with lost progress; the failed rehearsal was uncounted and v6 requires a fresh complete
qualification on the corrected exact source.

The corrected replay cleared S.S. Anne and reached the Viridian Forest collection lesson, where a
level-4 passive cocoon maximized Defense and remained at 7/18 HP after eight verified low-level
Tackle hits. The former fixed attack count was insufficient for the policy's 30% capture threshold.
The adapter now derives its finite weakening budget from observed current HP, maximum HP, and the
policy threshold, assuming only the game's minimum one damage per landed hit and retaining a hard
32-attack ceiling. Ordinary targets keep the eight-attack floor; passive Harden users receive only
the additional observed work needed. The failed replay remains uncounted.

The next replay successfully weakened and captured the passive target, then encountered a level-5
Pikachu. Switching the level-3 Pidgey helper into Pikachu's attack caused an immediate faint before
the helper could act. Pikachu is now explicitly restored to the high-risk direct-throw set: the
healthy workhorse remains active and the teacher spends only the existing bounded five-ball
allowance. This is a portable risk decision—avoid a fragile switch against a dangerous target—not
an added retry, healing item, or encounter allowance. The replay was uncounted.

That replay then passed the Forest survey, every prior chapter, and Sabrina before reaching
Cinnabar with nineteen occupied bag slots and a two-Antidote stack. The capacity planner understood
that a slot had to be freed but only supported selling a one-item stack. It now sells the exact
observed one- or two-item Antidote stack, verifies the quantity selector, inventory removal, and
corresponding money delta, then follows the unchanged Mansion item-capacity proof. The failed replay
was uncounted.

The repaired replay completed the level-75 workhorse/final-form curriculum, earned all eight
badges, and defeated the first three Elite Four members before the historical Lance Aerodactyl
pivot fainted a level-25 teammate. That sacrifice was designed for the obsolete single-carry
lineage and is neither necessary nor consistent with the developed-team contract: the healthy
level-79 Blastoise had both Surf and Ice Beam available. Lance now keeps the workhorse active,
chooses the existing type-aware Aerodactyl move policy, and reserves helper switching only for an
actual bounded recovery need. The uncounted rehearsal must restart on this exact source.

The next exact-source rehearsal defeated Lance and reached the Champion's final level-65
Alakazam with a level-80 Blastoise. The first recovery succeeded, but a later valid recovery was
rejected after the opponent's Recover animation and reply outlasted the healing helper's
twenty-four-frame settle window. Healing now uses the shared bounded battle-item settle allowance,
continues to advance text with cancellation-only inputs, and still requires both a verified return
to the trainer MAIN menu and an exact one-item decrement. This is an interaction-timing repair; it
does not add an item, retry, party level, or battle attempt. The rehearsal remains uncounted.

The long-settle replay completed that recovery, then exhausted its item reserve against the final
Alakazam with Blastoise still at 180/262 HP and 42 legal attacks remaining. An inherited
single-carry branch switched to the level-30 Jolteon solely to faint; during that turn Alakazam
healed from 176/189 to full, so the switch lost a developed teammate and erased offensive progress
without protecting a healing action. Champion play now keeps the healthy workhorse active once
recovery is exhausted. Bounded helper pivots remain only when they purchase a verified healing
turn. The failed rehearsal remains private and uncounted, and the exact source must requalify.

Keeping Blastoise active reduced the final Alakazam to 4/189 HP before the workhorse fainted. Three
developed teammates remained alive, including a full-health level-30 Snorlax, but the Champion
adapter treated any active-battler faint as terminal. The adapter now performs an observed,
bounded forced switch to the healthiest living teammate and gives reserve battlers a live-PP,
Disable-aware fallback move policy. At most five forced switches can occur, so this teaches normal
team-battle continuation without adding recovery items, resets, or attempts. The exact source must
again pass the complete uncounted rehearsal.

The forced-switch replay proved the new team action: Snorlax entered and reduced Alakazam from
4/189 to zero. The adapter then rejected the valid final-KO transition because its Champion receipt
still read the fainted party-slot-zero HP/PP fields instead of the active reserve battler fields.
Champion decisions and receipts now use active-battler HP, status, moves, and PP after a switch,
and a verified zero-enemy-HP state advances through a bounded victory-text transition before the
existing Hall-of-Fame terminal proof resumes. No outcome gate is relaxed: the Champion event and
Hall-of-Fame map remain jointly required. The rehearsal remains uncounted.

The active-battler replay again recorded Snorlax at 140 HP using Headbutt and Alakazam at zero, but
the runtime's first exception sample preceded the stable KO observation; the authoritative
diagnostic reread already contained the valid zero-HP evidence. The same strict final-KO handler
now runs on that authoritative reread before a runtime error can be emitted. It still requires an
active trainer battle, enemy HP exactly zero, and at least one living teammate before advancing the
bounded victory text. The rehearsal remains uncounted and must restart from clean power.

The authoritative-reread replay confirmed the missing state explicitly: the final snapshot was
already `scripted_or_blocked` with no active battle after Snorlax's KO, while the enemy-zero bytes
remained available as terminal evidence. The handler now accepts both legal sides of that exact
transition: trainer battle plus zero HP is settled with bounded inputs; post-battle dialogue plus
zero HP immediately returns to the existing outer dialogue controller. Any other battle state still
fails closed. The rehearsal remains uncounted.

That replay then passed all **312/312 gameplay checkpoints**, set the Champion event, and entered
the Hall of Fame. Its offline schedule gate rejected the artifact even though all **68/68**
`battle_start_offset_applied` events were present: the manual reserve-battler victory path had
proved the physical Champion exit but had not closed the schedule controller's active Champion
intent. The same proven external-exit hook already used by other bounded team-battle continuations
now closes both the schedule lifecycle and recorder lifecycle after the final KO. No schedule event
is synthesized or backfilled; the exact source must replay and independently attest all 68 battles.

The revised level-60 curriculum subsequently passed a clean-power unscheduled diagnostic in
**87,020 actions**, then began its required source-frozen v8 rehearsal. That uncounted run reached
checkpoint 75 before Vermilion's left/right harbor sailor deadlocked immediately west of the
player at `(21, 27)`: repeated left inputs and waits could not create a free patrol tile. The
teacher now applies a strictly local, bounded maneuver only at that exact harbor gate. It steps
north off row 27, waits for the return tile, restores the approach, and verifies the leftward move
to `(20, 27)`. Any map change, battle, unexpected coordinate, or failure to restore still rejects
the run. No counted v8 slot was consumed; the repaired exact source requires another complete
312-checkpoint and 68-battle rehearsal before collection opens.

That repaired replay crossed the harbor, boarded the ship, obtained HM01, and reached the Route 11
capture lesson at checkpoint 86. It then knocked out twelve valid level-17 Spearow with Water Gun.
The move had been safely qualified for a level-24 Wartortle, but staged development now reaches the
lesson at level 30–31 and makes every available damaging move lethal from full HP. The teacher no
longer applies a historically safe move after its damage assumptions become false. At the proven
level-30 floor it instead allows at most five direct Poké Ball throws on the same target. Each
failed throw must consume exactly one Ball, retain a living level-17 Spearow and workhorse, and
return to the wild-battle main menu; success proves the exact aggregate decrement and party
addition. This second source-frozen failure was also uncounted, and v8 remains unopened pending a
complete replay.

The direct-capture replay then caught Spearow on its fourth Ball, completed the Diglett/DUX/Cut
lesson and Lt. Surge, and reached the Rock Tunnel purchase at checkpoint 102. The first three
failed throws were legal under the new five-throw policy but reduced the later Ball-sale proceeds
by ₽300; the fixed supply plan consequently lacked ₽259 for its fourth Repel. The Mart contract now
computes its funding gap after the observed Nugget and early-Ball sales and sells only the exact
number of obsolete 20-HP Potions required to cover that gap. It proves both the Potion decrement
and cash proceeds, rejects a gap larger than the live obsolete reserve, and leaves the fixed ten
Super Potions, status items, and four Repels unchanged. This rehearsal was uncounted and all twelve
v8 roots remain pending.

The funded replay then passed every earlier boundary through the Safari Zone and obtained HM03 at
checkpoint 194. Surf correctly replaced slot-four Water Gun, but the helper rejected the lesson
because it also required Bite and BubbleBeam to be at maximum PP immediately afterward. The live
pre-lesson vector was `(16, 30, 16, 25)`; Gen I correctly preserved the first three slots and set
Surf to 15 PP. Teaching evidence now binds that observed vector, requires exact preservation of
slots one through three, and requires slot four to become Surf with 15 PP. The later Fuchsia nurse
boundary independently requires the fully restored `(25, 30, 20, 15)` vector. The artifact remains
uncounted because the stale evidence contract rejected it, and v8 still requires a complete replay.

The next replay passed the immediate teaching gate at checkpoint 195 and exited the Safari Zone,
but the final chapter report still observed `(16, 30, 16, 15)` PP. The Fuchsia nurse loop had
stopped after one confirmation because HP and status were already clean, so it opened the dialogue
without completing the heal. That boundary now requires HP, status, and the fully restored
`(25, 30, 20, 15)` post-Surf PP vector before it can exit. The report therefore binds two distinct
facts: teaching preserves unrelated current PP, and the later completed nurse interaction restores
all four moves. This failure was also uncounted.

The fully restored replay passed all prior repairs, completed the six-member roster and level-60
training, and defeated Lorelei, Bruno, and Agatha before a Lance recovery pivot stalled at
checkpoint 308. Two earlier weak helpers in party slots 1 and 2 fainted and returned to Blastoise
correctly. The third helper occupied slot 4, while the shared forced-switch gate still accepted
cursor values only through 2 from the historical three-member route. It now validates the cursor
against the observed live party size and still requires the actual party-menu cursor tile before
selection. This generalizes ordinary forced switching to all six roster positions without adding
items, retries, or battle attempts. The late-game failure remained uncounted.

The generalized switch replay completed that slot-4 return and defeated Lance, but post-battle
recovery then found three fainted helpers against the fixed two-Revive reserve. With Surf as the
only remaining attack, the full-health safety rule had requested recovery after three Aerodactyl
exchanges. The first two helper sacrifices matched the declared revival capacity; before the third,
Blastoise still held 165/205 HP and could safely consume the selected healing item itself. Lance
now caps helper pivots at two and performs any later recovery directly on the active workhorse.
This carries the revival budget into the tactical decision, preserves a third teammate for the
Champion, and adds no item, retry, or battle attempt. The rehearsal remained uncounted.

The resulting source then completed its full v8 qualification: **312/312 checkpoints**, **36/36
objectives**, **68/68 scheduled battles**, Champion, and Hall of Fame. The first immutable counted
root, seed `18001`, reached checkpoint 90 after catching Spearow, teaching Cut, and returning to the
Dig lesson. Variable capture spending had changed the bag layout, leaving TM28 above the current
absolute cursor; the historical helper searched only downward and rejected the present item. That
failed root remains preserved, v8 is retired, and its eleven pending slots will never be opened.

The current v9 registry uses exposed v8 seed `18001` only as its uncounted schedule rehearsal. Its
counted seeds are fresh and disjoint: `19001`–`19005` for training, `29001`–`29002` for validation,
and `39001`–`39005` for sealed test. Bag selection now proves that the requested item exists, finds
its live absolute index, and moves either upward or downward to that index. V9 must reproduce the
complete 312-checkpoint, 36-objective, 68-battle Hall-of-Fame qualification before slot 01 opens.

The first v9 rehearsal confirmed that repair through TM28 and checkpoint 91, then a third legal
Rock Tunnel paralysis exhausted the two-cure travel allowance before checkpoint 110. DUX remained
paralyzed after the final role pivot and the field gate correctly rejected a cure with no item.
Tunnel preparation now carries and Lavender restores a three-cure reserve. The dynamic
obsolete-Potion sale funds the added ₽200 contingency, and the larger quantity stays in the same
existing bag stack rather than consuming another capacity slot. The failed rehearsal was uncounted.

The three-cure replay bought one additional unit through the Mart quantity menu. Its nominal
120-frame cursor pulse advances 144 emulator frames after the bounded press/release overhead.
Leaving the old 191-frame wait
in place shifted the later Tunnel battle lineage and fainted the protected lead at trainer 5. The
first correction subtracted only the nominal 120 frames, leaving a measured 24-frame surplus; that
replay exhausted its Antidote allowance later in the same chapter. The explicit alignment wait is
now 47 frames, preserving the same 335-emulator-frame quantity-plus-alignment budget as the
qualified two-cure route. This is a measured timing correction, not an additional battle attempt
or recovery allowance; both rehearsals were uncounted.

The exact-frame replay cleared all nine Tunnel trainers and reached Rocket Hideout checkpoint 136.
There, the final door guard poisoned the workhorse after Rock Tunnel had consumed the carried
Antidote, so the pre-Giovanni field gate rejected an unavailable cure. Lavender now restores one
Antidote only when the live post-Tunnel inventory lacks it, proving the exact ₽100 purchase and
one-item reserve. The same item is consumed on this observed poison branch; if it survives another
schedule, the existing late-game obsolete-status-item cleanup already handles its stack. This
failure remained uncounted and v9 still requires a complete replay.

The restored-Antidote source then qualified v9 end to end: **312/312 checkpoints**, **36/36
objectives**, **68/68 scheduled battles**, Champion, and Hall of Fame. Fresh counted seed `19001`
subsequently reached checkpoint 75 before a high-level wild Dugtrio entered the pre-ship training
loop. The controller treated every cave encounter as training material; Dugtrio moved first and
fainted the workhorse before it spent attack PP, leaving the opponent at full HP. That immutable
root is preserved, v9 is retired, and its eleven pending slots will never run.

The current v10 registry uses exposed v9 seed `19001` only for its uncounted rehearsal and assigns
fresh counted seeds `20001`–`20005`, `30001`–`30002`, and `40001`–`40005`. Pre-ship training now
distinguishes the safe Diglett curriculum from the cave's evolved ambush: Dugtrio triggers a
bounded, menu-normalized flee that must preserve the party and attack PP and leave the workhorse
alive. Successful escapes are reported separately from training wins. V10 must pass its complete
qualification before any counted slot opens.

The first v10 rehearsal crossed the Dugtrio branch and completed pre-ship training, but the later
Viridian Forest survey stopped when a passive cocoon required exactly the declared number of
one-damage weakening attacks. The loop treated exhaustion of the attack iterator as failure before
replanning the now-weakened target. It now permits one terminal policy observation after the last
budgeted attack: a throw or flee may proceed, while another weakening request still fails at the
same cap. The attack allowance itself is unchanged, and this rehearsal was uncounted.

The terminal-replan replay completed the Forest survey and reached scheduled Route 9 trainer 0.
The level-17 DUX helper spent its required Peck evidence, then Wrap trapped and fainted it with the
opponent at 10 HP. The shared Lavender battle controller now recognizes only an observed zero-HP
active member, selects the first living teammate through the verified forced-party menu, and
continues under a party-size-minus-one bound. It adds no healing item or retry and still requires
the chapter's later Center recovery. This rehearsal was uncounted.

The continuation replay reached the same faint but the generic switch helper first tried to open
PARTY from a normal battle MAIN menu. Wrap's KO had instead left faint dialogue leading directly to
the forced-party screen, so the helper rejected the transition. The shared switch primitive now
has an explicit zero-HP branch: it advances at least one bounded dialogue pulse, proves a live
party cursor, selects the declared living slot, and succeeds only after the battle returns to MAIN
with that member active. Ordinary voluntary switching is unchanged. The failure was uncounted.

The forced-switch replay selected the living teammate and reduced the wrapped opponent from 10 HP
to zero. During the terminal transition, the adapter still exposed the fainted party lead's field
HP, so the generic presence gate rejected the state before its existing enemy-KO dialogue handler
could run. Presence validation now treats enemy HP exactly zero as authoritative only while the
battle is active or in its immediate field exit; every nonterminal zero-HP battler still fails, and
map/readiness checks still reject blackout. This rehearsal remained uncounted.

V10 subsequently qualified **312/312 checkpoints**, **36/36 objectives**, Hall of Fame, and all
**68/68** scheduled battles on exposed rehearsal seed `19001`. Its first fresh, one-shot training
root at seed `20001` stopped at Misty: the single-member party's Wartortle fainted with Starmie at
10/59 HP. The outcome is sealed, v10 is retired, and its pending slots will not run. V11 uses that
exposed seed only for the uncounted rehearsal and assigns fresh counted seeds `21001`–`21005`,
`31001`–`31002`, and `41001`–`41005`. Misty may spend only the live Potion surplus above the
four-Potion Rocket reserve, at a stable low-HP MAIN gate, with exact heal and quantity proof.

V11 passed the complete uncounted qualification, but its first immutable training root at seed
`21001` stopped when a moving Cerulean Mart customer blocked the repeat-clerk approach. That
one-shot outcome is sealed and v11 is retired. V12 promotes `21001` only to its uncounted rehearsal
and assigns disjoint counted seeds `22001`–`22005`, `32001`–`32002`, and `42001`–`42005`.

The first v12 rehearsal cleared that Mart boundary and reached checkpoint 86, where the Spearow
capture loop changed the Ball stack from 30 to 28 inside one requested throw. Repeated A input had
crossed an unobserved MAIN-menu boundary and issued a second item command. Post-throw dialogue now
uses B, which advances text without selecting a battle command. This artifact is uncounted, every
v12 slot remains pending, and the repaired exact source must complete the full qualification before
collection opens.

The capture-safe replay proved checkpoints 87–91 before Route 1's horizontal youngster occupied
the northbound tile above `(14, 14)` during the collection survey. The adapter now yields one safe
tile east, waits under a 24-attempt bound, restores the exact approach, and retries north. It does
not consume the pending route direction while blocked, and every incidental encounter retains the
same flee and Ball-preservation proof. This failure was also uncounted.

The next replay cleared that walker and reached checkpoint 102, where early capture variance left a
₽2,109 Rock Tunnel shortfall while only five obsolete Potions remained. The teacher now earns the
source-exact ₽1,260 payout from Route 11 Gambler set 1 and sells unused TM24 for ₽1,000 before the
fixed supply purchase. This adds one real adaptive battle to the frozen roster, so v12 schedules
contain 69 identities and 69 offsets. The battle event, trainer identity, payout, reversible route,
zero battle-item use, and restored Vermilion boundary are all required evidence.

V12 subsequently qualified all **312/312 checkpoints**, **36/36 objectives**, and **69/69**
scheduled battles. Its first immutable training root stopped after boarding the S.S. Anne when the
source-defined first-floor waiter occupied the westbound corridor tile at `(8, 6)`. That outcome is
sealed and v12 is retired. The teacher now yields the exact corridor from `(9, 6)` to `(9, 7)`,
waits under a finite source-pinned bound, restores the approach, and completes the requested step.
V13 assigns disjoint rehearsal seed `21002` and counted seeds `23001`–`23005`, `33001`–`33002`, and
`43001`–`43005`; none of its slots may open before its clean 69-battle rehearsal qualifies.
Its first rehearsal observed the same Vermilion sailor one tile earlier at `(22, 27)`. The bounded
yield now derives its step-aside and clear tiles from either source-observed gate, `(21, 27)` or
`(22, 27)`, while rejecting every other coordinate.
That replay continued to checkpoint 239 before Celadon Mart 5F's vertical gentleman occupied
`(14, 2)` during the X Special approach. The teacher may now step from the exact blocked stance
`(15, 2)` to `(15, 3)`, wait within a fixed 16-attempt bound, restore the approach, and prove the
westward crossing. No other shop collision receives this exception.

The next replay passed that customer and reached the Cinnabar preparation gate at checkpoint 272
with 19 effective bag slots and no Antidote. Earlier capacity logic only knew how to free a slot by
selling that obsolete cure. The teacher now sells the equally unused TM21 in this exact full-bag
variant, accounts for its ₽2,500 proceeds, and preserves Bide for the delayed TM38 capacity lesson.
That repair completed Cinnabar and reached the Indigo shopping sequence at checkpoint 291. Because
TM21 was already gone, the old late planner did not free its expected slot before buying Submission.
The Indigo planner now sells the remaining obsolete Potion stack when TM21 is absent; it preserves
TM14 for Lance/Champion coverage and rejects a lineage with neither legal capacity option.

V13 then qualified **312/312 checkpoints**, **36/36 objectives**, and **69/69** scheduled battles.
Its first immutable training root reached Agatha at checkpoint 305 and defeated her final Gengar,
but finished poisoned after consuming the Full Heal reserve. Post-battle recovery incorrectly chose
the absent Full Heal solely because HP was full. That root is sealed and v13 is retired. V14 uses
fresh rehearsal seed `21003` and counted seeds `24001`–`24005`, `34001`–`34002`, and
`44001`–`44005`. Its recovery selector prefers Full Heal when present and otherwise proves a legal
Full Restore fallback for status, including full-HP poison.

V14's first uncounted rehearsal stopped honestly at checkpoint 112 after clearing Rock Tunnel. Its
held-out battle offsets required three verified Awakening uses instead of the previous maximum of
two, exhausting the three-item reserve before Pokémon Tower. Lavender Mart cannot replace that
item. The teacher now buys a fourth Awakening with the already-proven Vermilion income, carries it
in the existing bag stack, and requires at least one to survive the Tunnel. The extra ₽200 is
included in the exact purchase ledger; no counted slot was opened.

The immediate replay stopped at the same Vermilion shop before entering the Tunnel: the reserve
target and money ledger had been raised to four, but the purchase adapter still requested the old
single-copy quantity. Its live proof rejected the observed three-item stack. The transaction now
derives both the requested quantity and target from the same declared reserve constants, preventing
the plan and menu operation from drifting independently.

The corrected replay passed every earlier gate, defeated Lance, and stopped at checkpoint 309 when
the Champion input correctly required a protected Full Restore. The six-item Full Restore stack had
covered HP recovery, but Lance spent its final copy on status after the two cheaper Full Heals were
gone. The Indigo plan now carries six Full Heals in the same existing stack. This separates status
recovery from the scarcer all-purpose reserve, costs only an additional ₽2,400, and leaves the
Champion's Full Restore gate intact. The diagnostic now reports every input predicate rather than
printing HP beside an unrelated inventory failure.

V14 subsequently qualified the entire game at **312/312 checkpoints**, **36/36 objectives**, and
**69/69** scheduled battles. Its first immutable training root then encountered a level-31 Dugtrio
during the pre-ship Diglett's Cave lesson. Wartortle selected RUN without spending attack PP, but
the faster Dugtrio denied escape and reduced the full-health level-26 lead from 71 HP to zero in one
attack. V14 is sealed and retired. V15 moves only this early development lesson to the already
source-qualified Route 11 grass, where encounters are lower-level and can be fought safely. The
later planned Diglett capture still teaches the cave's progression value. V15 uses fresh rehearsal
seed `21004` and counted seeds `25001`–`25005`, `35001`–`35002`, and `45001`–`45005`.

V15 qualified the complete **312-checkpoint**, **36-objective**, **69-scheduled-battle** route on
its sealed source. Its first immutable training slot then met a Route 11 Venonat whose Disable
targeted Water Gun. The pre-ship selector respected PP but did not exclude the live disabled slot,
so the battle runtime rejected the attempted action. V15 remains sealed with that failed outcome.
V16 adds the missing semantic disabled-slot gate and uses fresh rehearsal seed `21005` plus counted
seeds `26001`–`26005`, `36001`–`36002`, and `46001`–`46005`.

V16 then completed its uncounted qualification at **312/312 checkpoints**, **36/36 objectives**,
and **69/69** schedule attestations. Its first one-shot training root reached the Champion's final
Venusaur but failed after the generic move ranking had spent Blizzard PP on earlier opponents.
The permanent v16 ledger records that failure, so the campaign cannot provide five complete train
roots and its remaining eleven roots stay unopened. V17 promotes exposed seed `26001` to the
uncounted rehearsal and preregisters fresh train seeds `27001`–`27005`, validation seeds
`37001`–`37002`, and sealed test seeds `47001`–`47005`. Its Champion policy reserves Blizzard for
Venusaur, uses Surf against Rhydon and Arcanine, exploits Alakazam's physical Defense, and excludes
the live disabled move from every ranking.

V17 qualified on the exact v16 failure schedule, proving the Champion coverage correction. Its
first immutable training root later reached Saffron at checkpoint 239, where one upward Mart input
was swallowed and the fixed `up, up, left` approach ended at `(2,6)` while facing left. The clerk
gate rejected interaction from the wrong coordinate. That outcome is permanent and v17 is retired
with eleven roots unopened. V18 promotes exposed seed `27001` to rehearsal-only use, assigns fresh
train seeds `28001`–`28005`, validation seeds `38001`–`38002`, and sealed test seeds
`48001`–`48005`. Its clerk approach reuses the shared verified-step primitive so every intended
movement must change the observed coordinate, with bounded retries for a swallowed input.

V18 qualified that exact Saffron schedule and then failed honestly in fresh train root 01 at Lt.
Surge. The Super Potion healed the active Diglett, but HP and inventory effects were not jointly
visible on the first MAIN observation. The settle loop used A, which could reopen ITEM while
waiting and destroy the exact-one-item proof. V18 is retired with one failed and eleven unopened
roots. Recovery now samples one frame at a time with B, which advances battle text but cannot
select ITEM from MAIN, and retains the exact HP, quantity, and living-battle contract.

The next campaign is not frozen immediately. `record --diagnostic-schedule-seed SEED` binds the
same 69-battle offset derivation to a clean-power recording while marking the episode explicitly
uncounted, unassigned, and pre-registration-only. It never publishes a dry-run qualification and
never opens or updates a campaign ledger. A multi-seed battery through this lane is now required
before v19 preregistration, addressing the serial one-rehearsal/one-held-out-failure pattern without
reusing any future counted seed.

The v19 candidate registry uses the exposed v18 seed `28001` only for its mandatory rehearsal and
reserves fresh counted seeds `29001`–`29005`, `39001`–`39002`, and `49001`–`49005`. Those counted
seeds remain unopened while independent diagnostic seeds are exercised through the robustness
lane; passing that battery is an additional engineering gate, not a substitute for the committed
v19 rehearsal.

The first v19 pre-registration diagnostic, seed `60001`, stopped at checkpoint 75 when Route 11
sleep recovery observed the counter move from its final sleeping turn into a fresh sleep duration.
That is a valid Generation I transition when the player wakes and the opponent immediately lands
Hypnosis again before the next observation, not evidence that the route has regressed. V19 was
retired before its mandatory rehearsal and with all twelve counted roots unopened. Recovery now
recognizes at most two immediate sleep reapplications, only at the wake-up boundary, while still
proving unchanged PP, a living battler, and a finite pulse budget.

V20 promotes diagnostic seed `60001` to its rehearsal-only assignment and reserves fresh counted
seeds `30001`–`30005`, `40001`–`40002`, and `50001`–`50005`. Independent seeds
`61001`–`61005` must pass through the uncounted diagnostic lane before the official v20 rehearsal.

The exact v20 diagnostic replay passed the repaired sleep boundary and continued through checkpoint
91. During the Route 1 and Viridian Forest collection detour, a paralyzed lead repeatedly failed
to escape a low-level wild encounter while the opponent applied further Speed drops. The old flee
bound counted every dialogue press as though it were a distinct RUN attempt, so ordinary opponent
text exhausted the bound prematurely. V20 is retired before rehearsal with all counted roots
unopened. Flee recovery now counts sixteen semantic RUN selections separately from 128 bounded
transition pulses, uses non-selecting B presses through dialogue, and preserves party, PP, and a
living lead throughout.

V21 retains exposed seed `60001` for rehearsal only and reserves fresh counted seeds
`31001`–`31005`, `41001`–`41002`, and `51001`–`51005`. The independent diagnostic battery remains
`61001`–`61005` and must pass before that rehearsal.

The v21 replay cleared both earlier transitions, completed the full collection detour, solved the
Vermilion Gym locks, and defeated all three of Lt. Surge's Pokémon using only Dig. Its reward gate
then rejected a valid victory solely because the restored Wartortle lead still carried paralysis
from the collection detour. The next chapter already enters the Vermilion Center and proves full
party HP and zero status for every member. V21 is retired before rehearsal with all counted roots
unopened. The Surge boundary now proves survival, reward, inventory, party, and stable control while
carrying any persistent status into that explicit Center recovery.

V22 again uses exposed seed `60001` only for rehearsal and reserves fresh counted seeds
`32001`–`32005`, `42001`–`42002`, and `52001`–`52005`; diagnostics `61001`–`61005` remain unopened.

V22 passed all repaired Vermilion transitions, healed the complete party, cleared every mandatory
Rock Tunnel trainer, and reached a stable Lavender Center at checkpoint 112. Its report correctly
rejected the run because four observed sleep cures exhausted the four-item Awakening reserve,
leaving none for the later Pokémon Tower curriculum; Lavender Mart cannot replace it. V22 is
retired before rehearsal with every counted root unopened. Vermilion now purchases three
Awakenings on top of the two-item opening reserve, producing five without another bag slot and
retaining one after the exposed four-use schedule.

V23 retains seed `60001` for rehearsal only and reserves fresh counted seeds `33001`–`33005`,
`43001`–`43002`, and `53001`–`53005`; the five independent diagnostics remain the next gate.

V23 retained the Rock Tunnel cure, completed Pokémon Tower, caught Snorlax, earned Surf, Strength,
Soul and Rainbow Badges, and reached checkpoint 230. A fourth-floor Celadon Mart pedestrian then
blocked the single return step from the teacher's yield tile, and the old recovery rejected that
still-bounded position instead of continuing to wait. V23 is retired before rehearsal with every
counted root unopened. The walker skill now retries the return from its exact yield tile under a
second finite bound and still rejects any map, battle, or coordinate escape.

V24 uses exposed seed `60001` only for rehearsal and reserves fresh counted seeds `34001`–`34005`,
`44001`–`44002`, and `54001`–`54005`; independent diagnostics remain required first.

The v24 replay cleared the entire repaired route through checkpoint 306, defeated Agatha, healed the
party, and entered Lance's room. Its receipt rejected that valid victory because Agatha switched her
Golbat into an attack selected against Gengar; Golbat fainted before the teacher received another
decision boundary, so the policy-visible roster omitted position one even though the victory event
proved that the full trainer party was defeated. V24 is retired before rehearsal with every counted
root unopened. Agatha evidence now publishes both the source roster and the policy-visible subset,
validates each observed position against the source roster, and requires the opening and terminal
opponents plus the canonical victory event.

V25 retains exposed seed `60001` for rehearsal only and reserves fresh counted seeds
`35001`–`35005`, `45001`–`45002`, and `55001`–`55005`; diagnostics `61001`–`61005` remain unopened.

The v25 exact replay and diagnostic seed `61001` completed the Hall of Fame. Diagnostic seed
`61002` then defeated Agatha but ended with a damaged, cured lead: the field recovery selector used
a Full Heal whenever one remained, even when the same lead also needed HP recovery. The receipt
correctly stopped at checkpoint 306 rather than entering Lance underprepared. V25 is retired before
rehearsal with every counted root unopened. Post-Agatha recovery now prefers a Full Restore whenever
both damage and status are present, satisfying both Lance-entry invariants with one bounded item.

V26 retains exposed seed `60001` for rehearsal only and reserves fresh counted seeds
`36001`–`36005`, `46001`–`46002`, and `56001`–`56005`; all five diagnostics must be replayed.

V26 diagnostic seeds `61002` and `61001` completed the Hall of Fame and verified the combined
post-Agatha recovery. Seed `61003` then reached checkpoint 85 but searched 97 Route 11 encounters
without finding the required level-17 Spearow, exceeding the 96-encounter/1,800-step bound. The
route, party, and emulator remained healthy. V26 is retired before rehearsal with every counted
root unopened. The Spearow lesson now has its own finite 3,600-step/192-encounter budget instead of
sharing the general wild-search step budget; other capture lessons retain their existing limits.

V27 retains exposed seed `60001` for rehearsal only and reserves fresh counted seeds
`37001`–`37005`, `47001`–`47002`, and `57001`–`57005`; all five diagnostics must be replayed.

The v27 replay of seed `61003` proved the wider encounter search by finding the required Spearow
beyond the former bound. Five consecutive direct throws then failed to capture it, and the teacher
stopped with party and remaining inventory intact. V27 is retired before rehearsal with every
counted root unopened. The staged-development direct-capture lesson now permits at most fifteen of
the thirty purchased Poké Balls, preserving at least fifteen for the following Diglett lesson while
substantially reducing ordinary capture-RNG rejection.

V28 retains exposed seed `60001` for rehearsal only and reserves fresh counted seeds
`38001`–`38005`, `48001`–`48002`, and `58001`–`58005`; all five diagnostics must be replayed.

The v28 replay of seed `61003` passed both repaired Spearow gates, completed the Diglett capture and
trade, and preserved later inventory through checkpoint 239. A moving second-floor Celadon Mart
customer then occupied the only scripted north step on the approach to the third-floor stairs. V28 is
retired before rehearsal with every counted root unopened. The verified Mart movement now detects
that exact source-pinned gate, yields into the open side tile, waits under a finite 32-attempt bound,
returns, and proves the originally requested north step before continuing the canonical route.

V29 retains exposed seed `60001` for rehearsal only and reserves fresh counted seeds
`39001`–`39005`, `49001`–`49002`, and `59001`–`59005`; all five diagnostics must be replayed.

The v29 replay again passed the complete capture sequence and reached checkpoint 239. The first
customer-yield repair did not engage because it trusted the destination label ("Mart 3F") as the
current map, while terminal evidence proved the blocked coordinate was still on map 123, Mart 2F;
Mart 3F is map 124. V29 is retired before rehearsal with every counted root unopened. The recovery
contract now binds to the physical Mart 2F ascent coordinate and its test simulates that exact map.

V30 retains exposed seed `60001` for rehearsal only and reserves fresh counted seeds
`70001`–`70005`, `80001`–`80002`, and `90001`–`90005`; all five diagnostics must be replayed.

V30 diagnostic seeds `61003`, `61001`, and `61002` completed the Hall of Fame and independently
verified the capture, Mart-ascent, and Agatha repairs. Seed `61004` then purchased the required
Potion and Awakening top-up but a moving Cerulean Mart customer swallowed the right step from
`(2,7)` to the exit tile. The unverified route continued inside the Mart and the persistent return
gate correctly stopped at checkpoint 45. V30 is retired before rehearsal with every counted root
unopened. The repeat-clerk return now proves both south steps, retries the customer-blocked right
step under a finite 32-attempt bound, and only resumes the city route after observing `(3,7)`.

V31 retains exposed seed `60001` for rehearsal only and reserves fresh counted seeds
`100001`–`100005`, `110001`–`110002`, and `120001`–`120005`; all five diagnostics must be replayed.

V31 diagnostic seed `61004` passed the Cerulean Mart exit repair and reached the Forest collection
lesson after checkpoint 91. It then exhausted the thirty-ball route reserve: the contract allowed
fifteen bounded Spearow throws, eight bounded Diglett throws, and five throws for each of six
Forest specimens, but never replenished the inventory after Route 1. V31 is retired before
rehearsal with every counted root unopened. The teacher now sells the retained Route 24 Nugget at
the live Viridian Mart, proves the exact ₽5,000 sale and variable Ball-purchase ledger, restores a
thirty-ball Forest reserve, and returns to the same south-city boundary before collection.

V32 retains exposed seed `60001` for rehearsal only and reserves fresh counted seeds
`130001`–`130005`, `140001`–`140002`, and `150001`–`150005`; all five diagnostics must be replayed.

The v32 replay reached the new Viridian restock gate after checkpoint 91 and correctly rejected its
funding premise: the Route 24 Nugget had already been sold by the earlier Cerulean status-supply
lesson. Trace-level evidence from the original failure identified the exact budget: ten Spearow,
two Diglett, five Pidgey, one Rattata, one Caterpie, six Metapod, two Kakuna, and three failed
Pikachu throws consumed all thirty Balls. V32 is retired before rehearsal with every counted root
unopened. The corrected gate spends ₽1,000 of live earned cash to restore five Balls on that
observed lineage, establishes a seventeen-Ball Forest reserve, and preserves TM34 for its declared
later sale.

V33 retains exposed seed `60001` for rehearsal only and reserves fresh counted seeds
`160001`–`160005`, `170001`–`170002`, and `180001`–`180005`; all five diagnostics must be replayed.

The v33 replay proved the earned-cash restock, completed the Forest, and preserved the later supply
ledger through checkpoint 241. The Silph 3F Rocket then used Disable on slot four; that chapter's
fixed-slot wrapper ignored live Disable evidence even though the shared runtime correctly rejected
the illegal choice. V33 is retired before rehearsal with every counted root unopened. Fixed Silph
lessons now preserve their preferred move when usable and otherwise select the first live,
non-disabled move with PP.

V34 retains exposed seed `60001` for rehearsal only and reserves fresh counted seeds
`190001`–`190005`, `200001`–`200002`, and `210001`–`210005`; all five diagnostics must be replayed.

V34 diagnostic seed `61004` completed all 312 checkpoints and entered the Hall of Fame, proving
both the Forest restock and Silph Disable fallback. Seeds `61001` and `61002` then reached the same
checkpoint-91 reserve gate with 23 and 24 Balls already available. The minimum-reserve helper
incorrectly rejected those healthy surpluses instead of skipping the purchase. V34 is retired
before rehearsal with every counted root unopened. The gate now accepts every legal zero-to-thirty
input, returns immediately at or above seventeen, and visits the Mart only for an actual shortfall.

V35 retains exposed seed `60001` for rehearsal only and reserves fresh counted seeds
`220001`–`220005`, `230001`–`230002`, and `240001`–`240005`; all five diagnostics must be replayed.

V35 diagnostic seeds `61001`, `61002`, and `61003` completed all 312 checkpoints and entered the
Hall of Fame. Seed `61005` then cleared Route 24 trainers 5 and 4, but a moving Cerulean pedestrian
swallowed three eastbound inputs during the required Center backtrack; the fixed trace ended at
`(16,17)` instead of entering the Center. V35 is retired before rehearsal with every counted root
unopened. The recovery route now proves each east-corridor step, tolerates the stationary NPC under
the same finite retry policy as the westbound bridge approach, and only resumes the Center entry
after observing `(17,16)`.

V36 retains exposed seed `60001` for rehearsal only and reserves fresh counted seeds
`250001`–`250005`, `260001`–`260002`, and `270001`–`270005`; all five diagnostics must be replayed.

All five V36 diagnostics and its official 69-battle rehearsal completed 312/312 checkpoints and
entered the Hall of Fame. Its first counted training seed then reached Route 10 with only four
Super Potions: the held-out Route 9 timings had consumed six, one more than every qualifying run,
and the teacher correctly stopped before opening Rock Tunnel. V36 is retired with that immutable
failure and eleven unopened slots. The exposed seed becomes diagnostic-only. V37 exposes only the
live surplus above six to both Route 9 recovery controllers; once that shared budget is exhausted,
the balanced party continues with living teammates instead of spending Rock Tunnel's reserve. The
eleventh purchase input is paired with a modulo-256 alignment wait that restores the previously
qualified battle RNG phase.

V37 retains exposed seed `60001` for rehearsal only and reserves fresh counted seeds
`280001`–`280005`, `290001`–`290002`, and `300001`–`300005`. The exposed V36 training seed
`250001` must pass as an uncounted diagnostic before the new rehearsal.

The first complete replay of that exposed schedule proved the Route 9 and Rock Tunnel budgets and
continued to checkpoint 244. One post-rival elevator doorway input was then swallowed, so the floor
selector refused to run from the hallway. All Silph elevator entries now retry only an unchanged
doorway state and require the elevator map before opening the panel; the diagnostic remains
uncounted and must restart from clean power-on.

The next replay proved the post-rival exit but showed the later first-floor return still embedded
its final doorway input inside a long trace. That final step is now split out as well, so every
Silph elevator entry shares the same verified transition.

That doorway proof then localized the lost progress to the preceding first-floor corridor: the
return arrived at `(6,6)` rather than the elevator stance. Both outbound and return corridor traces
now prove every requested coordinate change before advancing, then delegate the doorway transition
to the shared elevator helper.

The verified corridor then proved its starting state was wrong: the fixed Center-to-Silph city
trace had re-entered the building from a displaced approach. Center returns now use the existing
collision-discovering Saffron planner to reach the Silph exterior at `(18,22)`, prove the entrance
warp to 1F `(10,17)`, and only then begin the verified elevator corridor.

That replay crossed Silph, all eight badges, Victory Road, Lorelei, and Bruno. Bruno immediately
reapplied a valid status after recovery; the teacher continued legally, won, and entered Agatha's
room with all six members fully healed and status-free, but the receipt rejected the intermediate
status byte. Bruno's decision evidence now accepts any valid low-seven-bit Gen-I status value while
retaining positive-HP, legal-move, terminal event, full-heal, and clean-status requirements.

The next clean diagnostic reached the final Champion Venusaur at checkpoint 311. The level-67
workhorse had preserved five Blizzard PP and dealt 130 of 189 HP, but the one-item Champion
Full Restore reserve had already been consumed; the remaining developed team stopped 28 HP short.
V37 therefore increases the Indigo Full Restore purchase from six to seven and makes two items a
cross-chapter protected reserve. Lance may use only inventory above that floor, including for
status fallback, and the Champion input rejects any handoff below two. The failed diagnostic stays
uncounted and must restart from clean power-on under the new source identity.

That corrected source completed the exposed schedule at 312/312. The subsequent official fixed
rehearsal reached checkpoint 230 before the Celadon Mart fourth-floor customer deadlocked the
stair-return corridor: the player at `(5,2)` and customer at `(6,2)` could not pass while the
controller continued pressing right. The failed rehearsal is retained and is not a qualification.
The bounded recovery now retreats to `(1,2)`, yields the corridor, and proves each eastbound tile
through `(6,2)` before the fixed route resumes. A fresh source-bound rehearsal is required.

The next fixed rehearsal cleared `(6,2)` but the same moving customer caused another head-on block
at `(9,2)`. That failed rehearsal is also retained and does not qualify the source. The recovery is
now defined over the complete bounded `y=2` aisle rather than one coordinate: any blocked eastbound
step from `x=1` through `x=11` retreats to `(1,2)`, yields, and proves movement only through the
original step target. Qualification restarts again with the generalized source.

The generalized source then completed its official rehearsal at **312/312 checkpoints**,
**36/36 objectives**, and all **69/69** scheduled battle attestations. V37's first immutable train
slot nevertheless stopped after checkpoint 85 when a wild encounter began during the twelve-step
Route 11 grass approach. The approach used the ordinary deterministic corridor primitive, which
correctly rejected battle state but could not dismiss an incidental encounter before the explicit
Spearow search began. That root is sealed, the other eleven v37 slots remain unopened, and v37 is
retired. V38 uses the existing encounter-aware corridor primitive for those twelve grass steps: it
retries the unconsumed movement after a bounded RUN, proves that party, PP, HP, and Poké Ball state
remain protected, and then begins the same species-filtered search. Exposed seed `280001` is now
diagnostic-only. V38 reserves fresh counted seeds `310001`–`310005`, `320001`–`320002`, and
`330001`–`330005`; its fixed rehearsal seed remains `60001`.

The first v38 exposed-seed replay passed Route 11 and entered Rock Tunnel, then stopped before the
eighth tunnel battle when a second poison cure was required and no Antidote remained. One of the
two Cerulean purchases may be consumed before the dungeon, leaving only one for multiple protected
lead/helper roles. The Cerulean purchase contract now carries three Antidotes and accepts every
observed zero-to-three remainder at immediate field-cure gates. The replay remains uncounted and
must restart from clean power under the resulting source identity.

The additional Cerulean quantity input then shifted a moving pedestrian and exposed the blind
Center-to-rival staging trace: several swallowed inputs left the player at `(16,16)` rather than
the required `(20,7)`. The run stopped at checkpoint 36 and remains uncounted. That staging route
now requires every direction to change map or coordinate within eight bounded retries and rejects
battle or a fainted lead before continuing. The exposed seed must restart under this source.

The replay showed unchanged-input retries alone cannot break the head-on pedestrian deadlock at
`(16,16)`. The route now proves its approach to that existing east gate, delegates the crossing to
the already bounded Route 24 NPC controller until `(8,16)`, and verifies the remaining northbound
segment separately. The failed diagnostic stays uncounted; another clean restart is required.

That restart cleared Cerulean but reached the S.S. Anne first-floor waiter at `(5,6)`, outside the
old recovery's single `(9,6)` source gate. The waiter recovery now supports the complete bounded
`y=6`, `x=2..9` corridor and derives its downward yield and westward clear tiles from the live
meeting coordinate. Regression evidence covers the new position. The uncounted diagnostic must
restart under the updated source.

The next restart passed those repaired branches, Route 11, and checkpoint 91 before the expanded
Viridian Forest survey exhausted its remaining Poké Balls on the final required Pikachu. The trace
entered the Forest with 22 Balls, but Pidgey and Rattata still carried their post-capture Route 1
HP/PP state; repeated cocoon lessons therefore depleted the safe low-power weakening capacity and
forced expensive full-health throws. The source now performs a free, bounded Viridian Center
recovery between the two surveys, verifies every party member at full HP and healthy status, proves
both Tackle/Gust helpers at 35 PP, and returns to the exact `(21,35)` source boundary before any
restock or Forest action. This changes neither the money ledger nor any throw/encounter bound. The
failed run remains uncounted and the fresh v38 partitions remain untouched.

The repaired replay did complete all six Forest captures. Its subsequent field Dig returned to the
newly visited Viridian Center rather than the obsolete Vermilion anchor, and the exact destination
gate stopped the run. The source now treats the changed anchor as real world state: it proves the
Viridian return, walks the bounded Route 2 approach again, traverses Diglett's Cave toward Route 11
by reversing the exact successful outbound path with the same encounter/inventory protections,
normalizes the Vermilion east boundary, and reaches the existing Center-storage coordinate. The
first inverse attempt instead launched a new DFS from the opposite entrance; its backtracking stack
was not valid for that orientation and stopped safely. Recording the proven path and replaying its
mathematical inverse removes that false rediscovery problem. Neither the field move nor a hidden
warp assumption is removed. Both failures are uncounted.

The exact inverse-path replay passed that handoff and all downstream gates through Champion
checkpoint 311. At the first attack, the boosted workhorse held 90 HP and all five Blizzard PP;
accurate Strength reduced Pidgeot from 182 to 57, but the reply knocked out the workhorse. The
remaining developed party reached Alakazam but could not overcome Recover, while five Full Restores
remained unusable on the fainted lead. The source now ranks boosted, X-Accuracy-backed Blizzard
first against Pidgeot. Four uses remain after that attack, against an observed two-use requirement
for Venusaur, so the repair spends existing surplus coverage rather than changing level, inventory,
healing, retry, or party-survival contracts. The failed diagnostic remains uncounted.

The Blizzard-first replay proved the opener and swept Pidgeot, Alakazam, Rhydon, Gyarados, and
Arcanine. At Venusaur, however, the inherited late helper-recovery tactic switched the workhorse
out twice. Gen I clears stat stages on switching, so six X Special stages disappeared; Blizzard
then dealt only 64–65 damage, Venusaur repeatedly used Recover, and both helpers fainted. Champion
recovery now uses the existing bounded direct Full Restore action. It preserves the boosted active
battler and every developed teammate, consumes no new item, and retains the one-attack progress
latch between heals. The failure remains an uncounted diagnostic.

That source completed the next exposed replay and the official clean-power rehearsal at 312/312
checkpoints, 36/36 objectives, and all 69 battle attestations. V38 train slot 01 then reached
checkpoint 239 before the moving fifth-floor Celadon customer occupied `(14,2)` while the player
returned from the X Special clerk at `(13,2)`. The existing customer controller covered the same
aisle only from the east. The failed root remains sealed and v38 is retired. V39 introduces the
symmetric west-side bounded yield, map/coordinate proof, and recross; it assigns fresh counted
seeds `340001`–`340005`, `350001`–`350002`, and `360001`–`360005`. Exposed seed `310001` is now
diagnostic-only and must pass before the fixed rehearsal can qualify v39.
The first v39 reproductions reached the same obstruction and selected the new west-side branch, but
proved the proposed downward yield tile `(13,3)` was not traversable. The controller now retreats
west along the known-open top aisle to `(12,2)`, requires observed west/east coordinate changes with
bounded retries, and then attempts the recross. Those diagnostics remain uncounted and source-bound
qualification restarts.
The next reproduction crossed the repaired customer and exited the Mart, then the fixed Celadon
return lost its vertical alignment and ended at `(19,14)` instead of Route 7. That failed diagnostic
remains uncounted. The complete city crossing now uses bounded observed-state movement rather than
accepting an unverified 38-input trace before the Route 7 terminal gate.
The next replay localized the obstruction to the initial eastbound staging leg, where a pedestrian
held the player at `(13,14)`. A bounded westward yield to `(12,14)`, observed reentry, and proven
crossing to `(14,14)` now precede the verified north/east Route 7 segment. The failure remains an
uncounted diagnostic and qualification restarts.
That route passed and the replay reached Sabrina, where Alakazam used Recover and then landed a
measured 94-HP critical hit against the 94-HP lead. The Alakazam-specific recovery floor is now 95
HP, while the generic 70-HP floor and seven-Hyper-Potion chapter cap remain unchanged. The failure
is uncounted; the exposed schedule must prove this stronger floor terminates before qualification.

That source then passed both the exposed diagnostic and the v39 clean-power rehearsal at 312/312
checkpoints, 36/36 objectives, and 69/69 battle attestations. V39 train slot 01 reached checkpoint
230 before the fourth-floor Celadon customer occupied `(1,2)` and blocked the westbound approach
from `(2,2)`. The immutable failed root remains sealed and v39 is retired. V40 generalizes the
existing bounded eastward yield to both observed corridor gates, preserves the map and coordinate
proofs, and reserves fresh counted seeds `370001`–`370005`, `380001`–`380002`, and
`390001`–`390005`. Exposed v39 seed `340001` is diagnostic-only and must complete before v40's
fixed rehearsal can qualify collection.
The exact `340001` diagnostic subsequently completed 312/312 checkpoints, all 36 objectives, and
the Hall of Fame. It remains uncounted; v40 still requires its separately scheduled clean-power
rehearsal and 69/69 attestation before slot 01 may open.

V40 passed that rehearsal and opened train slot 01. Its Snorlax capture consumed 19 Poké Balls,
leaving a 19-slot Cinnabar bag with three Antidotes. The capacity plan was already able to sell the
entire obsolete stack and prove the resulting money, but an outdated input predicate admitted only
quantities zero through two. The immutable failure remains sealed and v40 is retired. V41 validates
the legal 0–99 stack range while retaining the full-stack sale, slot, pickup, and economy proofs;
it reserves fresh counted seeds `430001`–`430005`, `440001`–`440002`, and `450001`–`450005`.
Retired v40 schedules may be used only as uncounted stress diagnostics before v41 qualification.
The first retired schedule completed the game. The second reached Lt. Surge with Diglett at 12/32
HP after the preceding knockout; the former one-third recovery floor did not heal, and the next
faster opponent dealt an observed 20 damage. V41 now spends the same single bounded Super Potion at
or below two-thirds HP. No extra item, retry, alternate move, or teammate sacrifice is introduced;
the exact stress schedule must restart under the updated source identity.
That replay selected the recovery at the intended gate and restored HP, but the opponent's reply
arrived before the delayed bag count became visible. The old verifier required full HP and the
decrement on the same sampled frame. V41 now latches the observed heal and the exactly-one-item
decrement independently, still requires a living MAIN-menu return, and fails on any second item.
That exact Surge schedule then completed the game. The next retired schedule reached the
fourth-floor evolution-stone return with the customer occupying the eastbound corridor. The former
recovery waited at `(1,2)`, which itself prevented the customer from crossing. V41 now steps into
the proven `(1,3)` alcove, observes the reentry to `(1,2)`, and only then retries east with the same
finite coordinate and map bounds.
That return recovery passed, and the same schedule reached Bruno. Unboosted Mega Punch left his
level-55 Machoke at 8 HP before an observed critical Submission knocked out the workhorse. V41 now
prefers STAB Surf throughout Bruno while PP exceeds the existing one-use Lance reserve, then falls
back through the prior move order. It adds no grinding, item, retry, or party sacrifice.
Retired seed `370004` next exposed a legal one-Super-Potion lineage whose capture spending left the
Rock Tunnel Mart ₽749 short with no obsolete Potions. Natural Dig had left TM28 unused, and the
post-Tunnel plan already treated its ₽1,000 sale as optional. V41 now moves that same sale earlier
only when live cash plus the complete obsolete-Potion stack cannot fund the fixed supplies. The
same trace legitimately consumed three Parlyz Heals before the final DUX role preparation, so the
tunnel carries a fourth contingency while Lavender restores only the established three-cure
downstream reserve. The adjusted quantity input retains the measured modulo-256 timing budget.
The exact seed then completed 312/312 checkpoints and Hall of Fame.

Retired seed `370005` repeatedly reapplied sleep during safe Route 11 training. The generic runtime
keeps its two-episode default, while this sleep-producing curriculum explicitly allows four finite
reapplications and retains HP, PP, menu, and fifth-episode rejection gates. Its Lavender replay
also proved the top-up must verify the three-cure downstream target rather than the four-cure
tunnel purchase. The exact seed subsequently completed the game.

Retired validation seed `380001` produced Koga's genuine terminal Selfdestruct exchange after the
battle-exit observation had already won the sampling race. V41 recognizes that result only when
Koga's event is complete, the lead alone is at zero, and every reserve remains alive; ordinary
faints still fail. Seed `380002` spent 15 Bite PP under Route 13 accuracy pressure while preserving
the declared ten-PP budget for the following trainer, then missed a Celadon Department Store door
transition. The per-battle PP contract now records that measured budget and the Ice Beam errand
verifies each city step and both doorway transitions. Both validation seeds then completed 312/312,
36/36, all 69 scheduled battles, Champion, and Hall of Fame. These artifacts remain stress-only;
v41's fresh counted roots stay sealed pending the exact-source official rehearsal.

V41 subsequently passed its official 312/312, 36/36, 69/69 rehearsal and completed train slots
`400001` through `400003`. Immutable slot `400004` exhausted its 24 Great Balls plus retained Poké
Ball while attempting the one-time Route 12 Snorlax capture, so v41 is preserved with three
complete and one failed counted outcomes and is ineligible for fitting. V42 keeps the same frozen
33-throw capture ceiling but funds 32 Great Balls by selling only the live obsolete-cure shortfall.
The exact exposed seed completed the shop proof, capture proof, all downstream inventory gates,
Champion, and Hall of Fame as an uncounted diagnostic. V42 uses fresh assignment identities and
must pass its own committed clean-power rehearsal before any counted slot opens.

V44 later completed all five training lineages and both validation lineages and produced the first
frozen battle candidate, with 85.8% held-out validation accuracy and its five test slots still
sealed. Test schedule `420002` then exposed two teacher-route defects before model evaluation: an
unconditional full-HP recovery and insufficient Snorlax-route liquidity. Those defects were
repaired without opening another test slot. Before a replacement campaign, the teacher moved to a
multi-schedule uncounted stress gate. Seed `61001` required a 25-Ball Forest capture reserve and
then completed the game. Seed `61002` caught Snorlax on throw 24, legitimately carried seven Super
Potions, and proved the final Indigo purchase was roughly ₽3,200 underfunded.

V48 addresses that systemic economy weakness by intentionally answering Cinnabar quizzes 1 and 3
incorrectly and defeating the adjacent source-pinned Burglar sets 4 and 5. Their exact ₽3,240 and
₽3,690 rewards create a ₽6,930 income buffer while adding four appropriate Fire-type opponents to
the battle curriculum. The two battles have stable public IDs, exact trainer identity, party,
Surf-policy, event, and payout receipts, expanding the schedule from 69 to 71 battles. The exact
formerly failing diagnostic, private episode
`red-schedule-diagnostic-a2bedeaf2d9041839955e2ab9a89904a`, subsequently completed 312/312
checkpoints, 36/36 objectives, 71/71 schedule attestations, Champion, and Hall of Fame. This is
uncounted stress evidence, not collection qualification. V48 reserves fresh train seeds
`460001`–`460005`, validation seeds `470001`–`470002`, test seeds `480001`–`480005`, and dry-run
seed `62001`; no counted slot opened.

Diagnostic seed `61003` then exposed an invalid exact-outcome assumption: Wartortle legally left
Route 24 at full HP, so the teacher had no reason to consume the reserved Potion. Recovery and
the subsequent Mart top-up now depend on live HP and carried quantity. Seeds `61003` and `61004`
then completed 312/312 checkpoints, 36/36 objectives, 71/71 schedule attestations, Champion, and
Hall of Fame. Seed `61005` exposed a second schedule alias at the Celadon Mart fourth-floor moving
Youngster. The return controller now reads that source-pinned object's live coordinates before
leaving its yield alcove; the exact seed subsequently completed the same full terminal. Because
v48 was already published, it remains historical. V49 reserves fresh train seeds
`490001`–`490005`, validation seeds `500001`–`500002`, test seeds `510001`–`510005`, and dry-run
seed `62001`. V49's rehearsal reached checkpoint 230 before proving that “walker east of the next
tile” becomes impossible near the staircase. V49 is retired with all counted slots unopened. The
controller now waits only for the x=1 alcove entrance to clear, follows behind the walker, and
retreats again only after observed blockage. An uncounted replay of the exact seed `62001`
subsequently completed 312/312 checkpoints, 36/36 objectives, 71/71 schedule attestations,
Champion, and Hall of Fame. V50 reserves train seeds `520001`–`520005`, validation seeds
`530001`–`530002`, test seeds `540001`–`540005`, and dry-run seed `62001`. All twelve v50 counted
slots were initially unopened. Its committed-source rehearsal completed the full terminal, but
counted train slot 01 then exposed a lower-level-Diglett lineage that had consumed TM28 before
Surge. With that ₽1,000 sale unavailable, live cash plus all three obsolete Potions was ₽299 short
of the fixed Rock Tunnel safety reserve. The failed slot is immutable and v50 is retired. The
teacher now conditionally sells the already-supported TM34 Bide capacity token only when observable
cash plus the complete obsolete-Potion stack cannot fund the reserve; Cinnabar's qualified
replacement preserves the later delayed-TM38 capacity lesson. V51 reserves train seeds
`550001`–`550005`, validation seeds `560001`–`560002`, test seeds `570001`–`570005`, and dry-run
seed `62001`. Its diagnostic moved the early ₽1,000 shortfall downstream to the Snorlax Great Ball
purchase, so v51 is retained as failed evidence rather than being retried indefinitely.

V52 freezes the model-assisted deployment bridge and the repaired S.S. Anne return route. It
reserves train seeds `580001`–`580005`, validation seeds `590001`–`590002`, test seeds
`600001`–`600005`, and dry-run seed `62001`. The registry remains a deterministic-teacher
collection contract; the separate model-assisted Hall-of-Fame receipt measures learner coverage
and teacher intervention without relabeling that run as autonomous model completion.

V53 freezes the private correction writer, its independent authenticated reader, and the iterative
refit lane. It reserves train seeds `610001`–`610005`, validation seeds `620001`–`620002`, test
seeds `630001`–`630005`, and dry-run seed `62001`. Corrections are training-only additions; the
historical validation roots remain unchanged, and every corrected model still requires a fresh
live rollout before any deployment claim.

V54 adds counterfactual teacher labeling during learner-controlled battles. The shadow teacher may
observe and label a disagreement but cannot replace the model's action. Failed learner rollouts are
retained as explicitly failed, integrity-checked correction corpora so the first causal failure
states can enter training. V54 reserves train seeds `640001`–`640005`, validation seeds
`650001`–`650002`, test seeds `660001`–`660005`, and dry-run seed `62001`.

V55 preserves routed non-move teacher control signals during learner move evaluation. This keeps
healing, volatile-condition recovery, and forced-switch control synchronized while the model owns
every move selection. The resulting rollout passed the former Cerulean boundary and produced 69
disagreement labels across seven battle groups before a Rock Tunnel supply shortfall. V55 reserves
train seeds `670001`–`670005`, validation seeds `680001`–`680002`, test seeds
`690001`–`690005`, and dry-run seed `62001`.

V56 adds a shared nonlinear move scorer so the learned policy can represent context-dependent
choices that the earlier linear ranker could not reconcile. The model keeps the same transferable
candidate features, legality mask, deterministic fitting, authenticated serialization, and live
deployment boundary. V56 reserves train seeds `700001`–`700005`, validation seeds
`710001`–`710002`, test seeds `720001`–`720005`, and dry-run seed `62001`.

V57 separates teacher-specific PP evidence from learned-policy battle evidence. Deterministic
teacher runs still require the routed move to spend PP; when a deployed model owns move selection,
the chapter accepts and records the actual legal move whose PP was spent. This prevents a valid
learned victory from failing merely because it did not copy the teacher's exact move. V57 reserves
train seeds `730001`–`730005`, validation seeds `740001`–`740002`, test seeds `750001`–`750005`,
and dry-run seed `62001`.

V58 introduces the game-neutral full-battle action vocabulary and a separate authenticated label
artifact for recovery, stat-boost, and switch decisions. Elite Four and Champion policy boundaries
now emit typed control requests without changing their existing execution behavior, allowing those
actions to become training examples instead of opaque exceptions. V58 reserves train seeds
`760001`–`760005`, validation seeds `770001`–`770002`, test seeds `780001`–`780005`, and dry-run
seed `62001`.

V59 expands each semantic observation with every party member's level, HP, maximum HP, and status,
plus transferable counts for healing, status recovery, revival, and battle-boost resources. Its
full-battle label stream records ordinary move selections as well as typed recovery, boost, and
switch decisions, so a high-level controller can be trained without a control-only class imbalance.
V59 reserves train seeds `790001`–`790005`, validation seeds `800001`–`800002`, test seeds
`810001`–`810005`, and dry-run seed `62001`.

V60 adds the live Special stat stage required to distinguish repeated setup actions from ordinary
attacks, types every remaining named trainer-battle recovery and switch boundary, and introduces a
game-neutral capture/flee action vocabulary. It also preregisters a class-balanced nonlinear battle
controller and battle-group-held-out evaluation path; no candidate may be deployed on training fit
alone. V60 reserves train seeds `820001`–`820005`, validation seeds `830001`–`830002`, test seeds
`840001`–`840005`, and dry-run seed `62001`.

V61 publishes the authenticated command-line fitting path for full-battle control candidates and
keeps the resulting model explicitly ineligible for promotion until it completes a fresh learned
rollout. V61 reserves train seeds `850001`–`850005`, validation seeds `860001`–`860002`, test seeds
`870001`–`870005`, and dry-run seed `62001`.

V62 adds reproducible uncounted timing perturbations to full-action collection, enriches the
controller with game-neutral type and move-mechanics aggregates, authenticates saved control-model
artifacts, and supports disjoint rollout-lineage evaluation. V62 reserves train seeds
`880001`–`880005`, validation seeds `890001`–`890002`, test seeds `900001`–`900005`, and dry-run
seed `62001`.
