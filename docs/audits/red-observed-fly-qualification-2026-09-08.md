# Observed Fly component — 2026-09-08

## Outcome and limits

The transport observation and controller component is implemented, not live-qualified.
The authenticated retained state exposes all eleven visited Fly towns, including Indigo.
No controller input or emulator frames occurred; checkpoint21445916/state34949deb/model76
are unchanged. Stored Farfetch'd55 remains boxed. No new outcome, fit or story success.

[Path-free evidence](../evidence/red-observed-fly-qualification-2026-09-08.json).

## Engineering review

- The observation adapter owns revision-specific visited bits and screen decoding.
  Town names are checked in full, including blank padding, with the Fly header and arrows.
  The ordinary menu cursor is not used to infer a destination.
- The field executor selects a living holder from its observed moves and menu order.
  Unknown/unvisited targets fail before opening menus. Each destination change must be
  acknowledged before continuing. Available towns must remain identical.
- A final re-observation precedes the sole flight confirmation. Landing checks wait
  within a fixed bound and never repeat the flight. Party, HP, PP, species, level,
  status, bag, money, badges and story flags remain protected.
- Arrival needs the declared map, complete coordinates, started game, walking mode,
  closed Fly menu, input readiness, no battle/dialogue/pending trainer.
- Existing field-move and PC behavior is unchanged; this new macro is not yet bound
  to a story option or live route. Tests do not establish live timing.
- 311 targeted tests pass: Fly, field moves, observation, capture-party and PC storage.
  Fixtures cover all eleven town labels, changed party/submenu positions, different
  visit sets, multiple cursor steps, zero-step selection and failed/partial landings.
  This is targeted testing, not the complete repository suite or scored mutation audit.
- A further153 dashboard/product/roadmap tests pass, preserving the last positive
  fit/episode identity while showing this session separately as zero-label engineering.
  Full-source lint and typing (425 source files), documentation, public-artifact and
  prospective registry freshness checks pass. No new hosted CI rerun is required.

## Cartridge evidence

Implementation was checked against pinned primary
[Fly menu source](https://raw.githubusercontent.com/pret/pokered/1e96034092686d006e863cace09e87273051a3d8/engine/items/town_map.asm).
The destination is held in the Fly-list traversal, and UP/DOWN move through visited
towns. The displayed name is observed rather than assuming the normal menu cursor.

The visit-flag addresses follow the pinned
[working-RAM layout](https://raw.githubusercontent.com/pret/pokered/1e96034092686d006e863cace09e87273051a3d8/ram/wram.asm).
A unique matching cartridge instruction sequence independently confirmed the two
visit-flag reads in the user's private ROM. Neither ROM bytes nor machine paths are
published. The inspection's audit actions and frames were zero; its historical
78 actions/7,513 frames belong to the previous retained income episode, not this audit.

## Reorientation and next work

The no-learning alarm remains active after another support-only slice. Do not open
another catalog/audit lane. Integrate collection-preserving PC retrieval using the
already verified operators and the observed box inventory. Preserve unique field
capabilities and useful capture roles; do not simply deposit the lowest level.

Then perform one bounded retained-state transport attempt with exact failure retention.
Live destination decoding is the first flight falsifier. Generic boss execution and
truthful readiness must follow before exposing ADVANCE_STORY alongside preparation.
The legacy Lorelei script's party/stock restrictions are not a preparation curriculum.

The income-to-story checklist remains 1/3. Goal-value model76 is already fitted,
but it is not a fully trained Pokémon player. A low-confidence estimate of 2–4 focused
sessions / 4–12 active engineering hours applies only to attempting the first story
learning run, not Phase4 completion or a broad neural-player training launch.
After that lesson, refit incrementally and test continuation rather than waiting for
all Phase4 capabilities to exist. The Champion milestone, unfamiliar Red modification,
living collection and eventual Crystal transfer retain their existing exit criteria.

No external audit or quota check ran this session. The next model recommendation is
Astra High, Fast off: use bounded implementation and verification, not maximum-effort
expansion. OpenAI Docs guidance was consulted for the recommendation; no comparative
token savings or account usage multiplier was measured.
