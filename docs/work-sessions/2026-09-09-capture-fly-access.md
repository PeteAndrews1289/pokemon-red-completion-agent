# Capture travel and location knowledge

## Mission check

- Capability: reach useful wild encounter areas through observed Fly travel and cartridge-derived walking, without per-species routes.
- Learned authority: make more real capture destinations available to the existing goal/source policy. Travel and encounter-table lookup remain disclosed deterministic support.
- Transfer test: vary destination coordinates, visited towns, capture prerequisites, profile transition order and empty local menus in ROM-free tests.
- Cheapest falsifier: action-free enumeration from the retained model111 Route11 checkpoint, then a short bounded collection continuation only if useful destinations exist.
- Time box: one session, two hours; reuse the existing flight/composition controller rather than design another planner.
- Stop condition: unsupported travel, unsafe capture resources, changed landing, lost specimens, or no useful menu. Preserve failures; do not replay consumed trials or open sealed/Crystal contexts.

## Location knowledge boundary

The current system enumerates wild sources and reads cartridge encounter tables
to identify useful missing specimens. That is supplied world knowledge, not a
model discovering an unseen species' habitat. The learned value policy sees
semantic effort, risk and search-history features rather than private source IDs.
Observed searches affect future choices; a failed bounded search is not proof of
absence. A future discovery mode should distinguish confirmed observations,
disclosed reference knowledge and uncertain hypotheses, and test those separately.
This session broadens executable capture access, not learned habitat inference.

## Implementation qualification

Capture profiles may now explicitly opt into the existing guarded Fly transport.
It uses each source's declared cartridge-derived grass boundary, preserves search
identity and rebinds the capture skill after verified travel. Escort preparation
remains supported. Walking stays preferred and historical profiles stay unchanged.
The capture flag survives future source retargeting, without enabling flight for
other mechanics. No new species-specific route or combat policy was added.

An empty old local menu no longer hides independently inventoried executable
regional choices. The selected destination still receives its own preflight
before input; unrelated errors propagate and truly empty menus stop normally.
367 targeted tests passed. Changed modules passed targeted typing; full-suite
and live-game success are not implied by these tests.
