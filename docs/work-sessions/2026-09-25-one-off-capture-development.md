# One-off capture: implementation and native-copy checks

Pete clarified that current play is development, not the final fresh-save exam.
Use isolated experiments to build capability; do not turn final acceptance into
a prerequisite for development. No current-save completion or learning claim.

## Implemented

- Cartridge-decoded static identity/event binding for all four legendary species.
  Object text points to its actual event header; Articuno object3/eventoffset2
  is handled without a species-specific event patch. Unknown/truncated data fails.
- Read-only live availability and pre-interaction resource/storage admission.
  A clear event is distinct from a visible, adjacent, input-ready object.
- Opt-in one-off execution through the shared capture entry. Ball identity and
  budget are explicit; ordinary capture behavior is unchanged. No automatic Run,
  attack, Master Ball substitution or save reset exists in this mode.
- Per-throw logs, strict ball/inventory accounting and exact target registration
  plus physical specimen checks. Budget/faint/unsupported states pause in place.
- Existing nondamaging status support can prepare throws; Master Ball skips it.
  The runtime handles caught-party append before Red clears its battle flag.

## Native results — assisted DEVELOPMENT copies only

Every copy originated from unchanged actual471. Teacher setup wrote two battle
trigger bytes decoded from the cartridge's native Snorlax scripts; the game
initialized target level/stats/moves. Ordinary-status copies additionally supplied
Spore/15PP in active/party move1 through four disclosed writes. Actor writes0.
No route, actual legendary object or consumed-event lifecycle was exercised.

| Check | Result |
|---|---|
| Master Ball, four species | All4 caught in separate copies; one ball each |
| One Great Ball allowance | One failed throw, live encounter retained, no Run |
| Selected Ultra Ball missing | Zero capture inputs, live encounter retained |
| Articuno + supplied sleep | Caught with2GreatBalls |
| Zapdos + supplied sleep | Paused after8throws at catcher faint |
| Moltres + supplied sleep | Paused after20throws; encounter retained |
| Mewtwo + supplied sleep | Caught with4GreatBalls |

The first Master Ball checks stopped falsely when native capture appended a sixth
PP row before battle=0. Those4failures remain retained. V2 verified the corrected
original-party-prefix check; it is a same-source regression replay, not independent
evidence. Overall16copies,1592actions/134412frames;6completed diagnostic captures.
These are mechanical tests, not a win-rate/transfer/model-quality comparison.

Independent zero-input audit reloaded all32battle-before/final states, checked
actions/frames, exact target, bag, money, original party, registrations and specimens.
Actual471/models unchanged;stage472absent;all gameplay stopped.
[Evidence](../evidence/red-one-off-capture-development-2026-09-25.json).
225targeted tests,lint and focused typing pass;not the full suite.

## What the failures teach us / next

1. Add bounded capture-time forced replacement/healing using existing mechanics,
   with no teacher attack fallback. Keep throw totals and source identity across
   interruption; pausing is diagnostic support, not autonomous recovery.
2. Test capture preparation that preserves useful sleep. Existing status support
   switches to its healthiest catcher; the first Zapdos sleep had already expired
   by its first throw. Do not mistake a successful status move for a statused throw.
   Voluntary preparation switches occurred; only automatic faint replacement is absent.
3. Qualify adequate supplies and safe weakening, then prepare a legitimate helper.
   The supplied Spore is scaffolding, not a move earned by the current party.
4. Verify one actual static-object interaction/consumed-event lifecycle on a copy,
   then connect a source-bound acquisition goal to the goal model and actual play.

Budget the next recovery/status packet at1–2hours; reassess using retained outcomes,
not a demand for perfect RNG results. No need to catch every species in every
development copy. Final fresh-save requirements are unchanged but are not this test.
Learning/fits/actual registrations0;both collection ledgers unchanged.
No publication/external reviewers. Next recommendation:AstraHigh,Fastoff.
