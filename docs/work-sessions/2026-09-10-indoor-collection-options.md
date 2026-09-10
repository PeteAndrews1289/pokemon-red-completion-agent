# Indoor collection choices — bounded overnight continuation

## Mission check

- Capability: recognize ordinary indoor land encounters, not just outdoor grass,
  when choosing useful missing registrations.
- Learned authority: restore genuine alternative capture sources for the current
  goal/source learner; deterministic mechanics still control navigation and battle.
- Transfer test: changed indoor maps, tilesets, water halves, block positions and
  obstacle/warp locations in ROM-free tests, then the current authenticated save.
- Cheapest falsifier: an indoor cave with a land encounter table but no literal
  grass gains a safe reversible lane; forest/outdoor pavement/water/warp tiles do not.
- Time box: one bounded two-hour integration/learning session inside the overnight
  window ending12:41UTC. Prefer new alternatives and outcomes over ancillary cleanup.
- Stop condition: no authenticated encounter rule, unsafe traversal, missing
  retained outcome or only forced singleton choices. No reset or full replay.

## Current evidence and hypothesis

After batchG,47 species are registered and model21 has21 examples. Zero-input
inspection of the actual Fearow terminal found no capture sources.21 admitted
outdoor-source observations reported no legal target; Route16 andRoute21 reported
missing capability.18 capture items remain, all six party members have positive
HP, and capture-support planning raised no errors. Four owned level evolutions
remain. The late singleton evolutions were not fitted.

The existing corridor builder demands `Terrain.grass` on both endpoints. That
excludes ordinary indoor land-encounter floors. Red's encounter routine permits
indoor land encounters outside the forest tileset, while excluding doors/warps
and handling water separately. Source:
[pret/pokered wild encounter routine](https://github.com/pret/pokered/blob/master/engine/battle/wild_encounters.asm),
[map constants](https://github.com/pret/pokered/blob/master/constants/map_constants.asm),
[tileset constants](https://github.com/pret/pokered/blob/master/constants/tileset_constants.asm).

Flash drafts an isolated, cartridge-backed indoor mask and discriminating tests.
Codex owns integration and actual run verification. Do not call every walkable
indoor square an encounter tile: require the actual land table, reject both water
halves, forest/Safari behavior, automatic doors/warps and blocked/directed routes.
Keep legacy no-cartridge corridor behavior unchanged. No indoor play is claimed yet.

## Engineering qualification

Ordinary indoor land encounters now qualify through cartridge tiles and actual land tables; 187 targeted tests, 465-file type check and lint passed. Real-ROM inspection found 1141 eligible static cells in Mt. Moon1F and1078 in Rock Tunnel1F despite zero literal grass. These counts do not establish accessible routes or successful capture. Model21 and47 registered species are unchanged.

Flash draft took253.6seconds. Review caught an incorrect Safari range (DD omitted, E2 wrongly included), a ROM truncation fixture that enlarged itself, and missing block-byte validation. All corrected before publication or gameplay.

Next: Verify current saved-state indoor capture choices with zero controller input, then run a fresh bounded model21 learning cycle from the actual batchG terminal. Retain outcomes and costs; do not count forced singleton mechanics as learned choices. No consumed retry, resource reset, sealed evaluation, full replay or Crystal.
