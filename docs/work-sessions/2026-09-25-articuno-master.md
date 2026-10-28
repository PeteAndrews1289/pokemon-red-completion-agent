# September25: Articuno captured on the authorized Master Ball copy

**Both requested native captures are verified on development copies.** Moltres
remains captured on its earlier continuous branch. Pete approved a separate copy
for Articuno using the legitimately held Master Ball. The failed16-Great-Ball
encounter remains untouched. [Evidence](../evidence/red-articuno-master-2026-09-25.json).

## Scope and mission check

This is mechanical qualification,not newly learned strategy. It closes Articuno
capture/event/specimen settlement to unblock acquisition/preparation alternatives
for the goal model. Transfer is a changed five-member source and ball configuration,
not an independent origin. The cheapest falsifier was source/ball/target admission
without input. The branch had a two-hour reassessment limit and bounded packets;
lost target,unsupported transition or new authority would stop it. No full replay,
TRAIN relabeling,save edit or final-run promotion was authorized.

## Native result

Protected actual471 was copied,never overwritten. Native travel reached Seafoam
after one Route20trainer:3frozen battle choices,2opponent KOs,2PP,zero own HP loss,
155cash earned. The old episode outcome discrepancy remains recorded;trainer
event1281,payout and field readiness independently establish the win.

The existing guarded planner/executor completed all eight boulder drops anew.
No puzzle flags or objects were edited. The routed acquisition reached Articuno,
used exactly one held Master Ball and settled the native capture. Articuno joined
party slot6;event2522 was set and object3 disappeared. All original five members'
HP/status/PP survived the capture unchanged. All six are healthy at the terminal.

Branch result:13packets,1467actions,103188frames;17to18owned,15specimens,
30775cash and20GreatBalls. Terminalb4fea3b4. Main471 still has17owned and its
Master Ball;the separate109/124collection ledger is untouched. These figures
are different saves and must not be added into a fictional combined run.

## Ultra Balls: viable, but preparation matters

The supported cartridge gives Articuno catch rate3. Its failed encounter was
still at162/162HP and paralyzed. The primary [Red capture algorithm](https://raw.githubusercontent.com/pret/pokered/master/engine/items/item_effects.asm)
uses different random ranges and HP factors for Great and Ultra Balls,with a
larger status allowance for sleep/freeze than paralysis. For this case,uniform
random-draw calculations give:

| Condition | Per-ball calculated capture chance |
| --- | ---: |
| Full HP,paralyzed,Great Ball | 6.981% |
| Full HP,paralyzed,Ultra Ball | 8.847% |
| 1HP,paralyzed,Ultra Ball | 10.596% |
| 1HP,asleep,Ultra Ball | 19.205% |

For reproducibility,X=min(255,floor(floor(162*255/ballFactor)/max(floor(HP/4),1))).
Here ballFactor=8Great or12Ultra. Probability=(statusBonus+4*(X+1)/256)/range,
where statusBonus=12paralysis or25sleep and range=201Great or151Ultra.
These are theoretical probabilities,not observed win rates or a qualified sleep
strategy. Sixteen full-HP/paralyzed Great Ball failures have roughly31.4%probability
under independent uniform draws:the result is not evidence Ultra Balls are broken
or capture is impossible. Native timing/RNG correlations are not tested by this calculation.

Only one legitimate Master Ball is available in a normal Red run. The separate
Mewtwo and Articuno Master Ball tests do not demonstrate catching both with that
one ball. The final player must allocate it once and handle other one-offs with
ordinary balls,appropriate status,nonlethal preparation and sufficient supplies.

## Verification and next work

Combined audit:42packets,192states,50capture receipts,4528actions and333000native
frames across both branches. Zero-input reload audit and an additional exact
source-chain/specimen/bag/event proof pass. Both earlier failed terminal hashes,
actual471/envelope and frozen models are unchanged;stage472is absent.

New result:3combat choices,0goal queries,0fits/newTRAIN. No production code changed
in this continuation. The prior508focused tests remain the access-code result;
174documentation tests,active-focus/docs checks and unchanged-registry verification
pass now. These checks are not new learning. All gameplay stopped;no publication
or external agents. The [updated roadmap](../model-first-roadmap.md) closes packetA
and moves to explicit pre-encounter readiness and model-owned preparation,then
remaining acquisition methods,strategic ownership,sustained play and fresh Red.
