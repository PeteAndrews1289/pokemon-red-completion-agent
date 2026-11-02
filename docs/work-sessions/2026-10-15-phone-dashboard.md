# Phone access during the frozen Red run

Pete requests phone viewing of the current run. The default initial scope is
the same Wi-Fi network; remote access is a separate connection choice. The
existing frozen actor and its loopback frame publisher were not changed.

## Mission check

1. Capability: observe the existing real dashboard from a phone during this run.
2. Authority: presentation only; no controller, save, model or gameplay access.
3. Reuse: existing responsive HTML, status projection and PNG frame endpoints.
   Keep the established local viewer and frozen package intact.
4. Cheapest falsifier: unauthenticated access succeeds, a write request reaches
   the viewer, another run is shown, or the phone relay cannot serve live frames.
5. Allowance: up to 30 minutes for a small LAN bridge, targeted checks and setup.
6. Reassess at 15 minutes or two equivalent failures. No actor restart, runtime
   modification, router changes, account changes or unrequested public sharing.

## Work

Add a separate GET-only bridge bound to the Mac's private IPv4 address. A private
link establishes an HttpOnly browser cookie and redirects to the clean viewer
URL. The bridge forwards only the existing public page/status/frame endpoints,
pins the selected run, rejects writes and keeps tokens out of request logs.
The existing dashboard remains bound to loopback. No game data is copied or fit.

## Verified result

The separate phone bridge is running on a specific private interface, port8767,
forwarding the existing loopback viewer8768. It is pinned to the selected run,
has no controller endpoint, rejects writes and anonymous requests, and expires
at October16 13:07:50UTC (09:07 Eastern). Tokens are held only in a0600 private
ACCESS.json and the private viewing link; no token is stored in repository docs.

61 targeted phone/spectator/dashboard tests pass. After adjusting cookie handling
for links opened from another app, all22 phone tests pass again; scoped lint passes.
The actual LAN interface serves the authenticated page, exact run status and PNG,
with a clean redirect/cookie; anonymous403, writes405 and unknown endpoints404.
`VERIFIED.json` in the private phone-dashboard-20261015-v1 folder retains checks.
The physical phone is not yet verified. This is trusted same-Wi-Fi HTTP, not
encrypted remote access; no router, firewall, account or public tunnel changed.

During this work, the unchanged player stopped independently at21:17:11UTC,
before the phone bridge was launched. It defeated Brock and retained13entries,
but failed `PC facing did not preserve its bound position` during story advancement.
The [terminal record](../evidence/red-frozen-escape-loan-terminal-2026-10-15.json)
authenticates exit/released buttons, all protected pins and exact costs. The
existing heartbeat is PAUSED. No repair/restart or successor was dispatched.
The viewer now honestly shows the stopped result and last real frame. Reusing
the phone bridge for another run requires selecting that run explicitly; it
fails closed if the upstream viewer silently changes run identity.

Phone work adds0TRAIN/fits/weights and0registrations. The independent frozen run
adds12entries beyond its starter, not because of viewing. The completed124save
and previous failures stay unchanged. No fresh completion claim follows.
