# Restored resources let the unchanged battler finish the Champion

[Evidence](../evidence/red-champion-resource-diagnostic-2026-09-25.json).
One explicitly assisted DEVELOPMENT diagnostic defeated all six opponents and
reached the native Hall of Fame with the live Champion flag. All37choices were
independently reconstructed. This is not earned progress or a qualified final run.
Actual463 remains34/36story,23843cash,17registrations;stage464 is absent.

## Controlled setup and comparison

The immediate parent is the retained failed copy's post-Revive boundary,
bc674e59. Its audited ancestry is actual463/e40e37ce. Using that boundary
preserves the starting emulator timing,RNG,party order and inventory,including
the already-consumed copy Revive. That inherited cost is not erased or repeated.
Only current HP/PP changed:13written bytes,320HP and38PP restored,zero frames
or inputs. Full CPU-visible memory comparison,including WRAM aliases,passed.
Levels,moves,stats,statuses,PP Ups,bag,money,flags and specimens were unchanged.
Setup is external intervention;the actor never receives its writable interface.
All artifacts remain DEVELOPMENT,excluded from TRAIN and economy qualification.

| Measurement | Retained depleted copy | Restored-resource copy |
| --- | ---: | ---: |
| Native result | Lost | Champion + Hall of Fame |
| Model choices | 63 | 37 |
| Opponents defeated | 5 | 6 |
| Party faints | 5 | 4 |
| PP spent in combat | 38 | 17 |
| Actions after matched parent | 1076 | 806 |
| Frames after matched parent | 97968 | 71820 |
| Cash change | -11922 | +6435,assisted only |

Both inherit the baseline's56Revive actions/4752frames/one item. The new test
uses zero additional items. Native execution took3.985seconds;policy median
2.676ms,total96.596ms. Nineteen attack/status selections,nine voluntary
switches,four forced replacements,five switch prompts. Zero invalid actions
or combat teacher interventions. Two moves were suppressed/failed;713cumulative
HP lost. Blastoise63survived with147HP;all four reserves fainted.

Blastoise stayed alive through Alakazam this time and later used Ice Beam to
defeat Venusaur. Four low-HP switch flags and nine voluntary switches remain;
the win does not establish optimal conservation or reliable multi-run success.
HP and PP were restored jointly;their separate effects are not isolated.
The matched starting RNG does not require identical later random events once
state-dependent decisions and native input timing diverge. One known lineage
cannot establish a population win rate or overwrite the failed29/72vs30/72screen.

## Native victory was initially rejected by a verifier

The native Champion escort had already reached Hall of Fame before the generic
battle lifecycle found a ready field. Its old check required the original battle
map and coordinates,so it raised a field-handoff verification error after victory.
That exception and missing runtime completion receipt remain in the record.
An independent zero-input audit verified native result,Champion flag,HoF,exact
6435payout,party/bag/boxes/registrations,envelope and protected campaign hashes.
The audit does not fabricate a successful original runtime receipt.

The correction permits only the exact admitted Champion story encounter to
finish at HoF. Ordinary battles,live target,event,payout,inventory,party and
blackout checks remain strict. The outer Champion skill now accepts an already
completed escort while retaining its concurrent completion referee.
571focused ROM-free tests pass. The corrected lifecycle also accepted the
retained native initial/final states with0inputs/frames/model calls,substituting
the authenticated outcome solely to test verification. No battle was replayed;
a fresh post-fix end-to-end native run is not claimed.

The original audit helper also stopped on an overly narrow memory-read API;
a separately retained read-only audit revision used the backend address-space
view. Neither frozen helper nor original trial was rewritten.
Closeout adds174documentation/focus/roadmap checks:745targeted tests total,
not a full-suite claim. Documentation links,active state and visual roadmap pass.

## Next decision

Prioritize legitimate recovery and supply planning before another fit. First
inspect actual463's legal exits,inventory and recovery/re-entry costs without
playing. No HP-healers are present;this diagnostic invents no legal supply or
free recovery route. If recovery requires a paid blackout/re-entry,expose that
cost before spending the save. Preserve the earlier loss and both copy outcomes.

No new weights,TRAIN labels,registrations,earned progress,promotion or publication.
All gameplay stopped. Next bounded feasibility pass:45–90minutes,AstraHigh,
Fastoff;resource planning and final-boundary integration need careful reasoning.
