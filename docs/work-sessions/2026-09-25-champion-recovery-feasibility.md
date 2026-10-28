# Champion recovery: locked in now, affordable resupply after an exit

[Evidence](../evidence/red-champion-recovery-feasibility-2026-09-25.json).
Read-only maintenance unblocking the next learned story attempt. Zero inputs,
frames,model calls,interventions,purchases or fits. Actual463 and all464stage
hashes remain unchanged;stage464absent. This is planning,not model improvement.

## What is actually possible

The live Lance-room lock flag is set. Current-block-aware routing finds no
path to Agatha,the Indigo lobby or outdoors;the Champion entry is reachable.
The room uses DOJO tileset5,excluded from Dig/Escape Rope. Fly/Teleport require
an outdoor origin;the party also lacks Teleport. There is no nurse or PC here.
These are game restrictions,not a missing backtracking patch. The local source
revision a1a22aaf was checked against committed bytes;prices additionally match
the exact cartridge's complete price table.

Bag:one Revive,no HP medicine,no PP medicine. The existing field planner can
revive Farfetch'd to72/144HP,but cannot restore the party. Seven Potions exist
in the PC;they are inaccessible until leaving the League. No PP items are stored.
The current PC withdrawal primitive admits only singleton stacks,so retrieving
all seven Potions is game-legal but not yet executable through that primitive.

An ordinary Champion loss would cost11922cash,leaving11921,and recover outside
Indigo. The retained previous copy already demonstrates that native blackout;
this session did not repeat it. Entering the lobby resets the Elite Four prefix,
so recovery is not a free trip back to the Champion. Four bosses must be beaten
again. No deliberate loss,reset,save edit or item sale is recommended here.

## Affordable fallback,not a guarantee

| Supply | Quantity | Unit cost | Total |
| --- | ---: | ---: | ---: |
| Hyper Potion | 3 | 1500 | 4500 |
| Revive | 4 | 1500 | 6000 |
| Full Heal | 1 | 600 | 600 |
| Total | | | 11100 |

After a hypothetical blackout this leaves821cash. Saffron and Cinnabar stock
these items;Indigo stocks Full Restores/Max Potions but not Hyper Potions.
Hyper Potions restore up to200HP;three plus seven stored Potions provide up to
740HP of healing before per-use waste,plus the Revives' separate restoration.
Past actual League progression consumed3Revives,2Super Potions and2Full Restores
before Champion;the losing Champion copy consumed another Revive. A cheaper
two-Revive basket would undersupply that observed faint pattern. Four is not
a guarantee against worse randomness. Full recovery before entry is essential.

Indigo's nurse restores HP/status/PP;PP medicines are not sold by these marts.
Existing Center support has an explicit Indigo opt-in/full-PP verifier. Corrected
cartridge-derived projected routes reach Indigo's nurse boundary in5steps,
its clerk in12,and Saffron's clerk in62from their respective Fly/blackout landings.
These are planning steps,not executed action/frame costs or door-to-door totals.
The first read-only cost draft accidentally targeted Saffron's Center and the
wrong Indigo nurse coordinate;the separate OPTIONS receipt corrects those
route claims without rewriting the retained draft. No gameplay occurred.

Conditional payouts: Lorelei5544,Bruno5742,Agatha5940,Lance6138,Champion6435;
29799gross only if all five wins occur. This is not qualified renewable profit.

## PP is not proven to require a new supply hunt

Every individual move used in the successful assisted trace had enough PP
already at actual463:Ice Beam3used/8available,Surf4/9,Dig1/3,Body Slam3/3,
ThunderShock3/23,Sand Attack2/15,Scratch1/35. Total17PP. Restoring HP and PP
together did not isolate their effects,and different visible PP may change the
policy's decisions. Therefore this is quantity coverage,not proof of an HP-only
win or permission to substitute the successful action sequence for model choices.
It supports prioritizing survival and HP preparation before a new fit or PP hunt.

## Next bounded implementation

1. Extend exact PC withdrawal to a declared quantity/stack,retaining bag/PC/party
   verification;test singleton compatibility and quantity/capacity errors.
2. Qualify recovery/resupply on the retained native-blackout copy,not by replaying
   Champion. Keep that copy DEVELOPMENT. No state edits,new fight,or campaign import.
   Verify lobby reset,actual full recovery,owned Potions,purchases and money.
3. Only then bind an earned Champion attempt with conditional loss recovery.
   Let the battler genuinely try to win;never script a loss or reset its costs.
   Recovery choices remain explicitly attributed until the goal model owns them.

Suggested recovery-only test cap:2000actions,200000frames,120seconds,11100cash,
zero battles,fits or save-memory edits;stop on one result/error/budget. Execution
is prospective,not performed or admitted by this read-only report.

201existing recovery/route/PC/goal regression tests pass;not new learning or a full
suite. No production code changed. Current story34/36,shared collection109/124,
freshRed0/5,TRAIN135unchanged. No GitHub publication;all gameplay stopped.
Next implementation/qualification estimate60–120minutes,AstraHigh,Fastoff.

Mechanics references: [Lance lock](https://github.com/pret/pokered/blob/a1a22aaf84d1675bcdbaeb194592379d586d838e/scripts/LancesRoom.asm),
[lobby reset](https://github.com/pret/pokered/blob/a1a22aaf84d1675bcdbaeb194592379d586d838e/scripts/IndigoPlateauLobby.asm),
[shop stock](https://github.com/pret/pokered/blob/a1a22aaf84d1675bcdbaeb194592379d586d838e/data/items/marts.asm).
