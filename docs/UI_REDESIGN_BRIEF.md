# UI Redesign Brief — triage-first, thumb-zone, onboarding (Impeccable shape)

Audience (PRODUCT.md): ops officer scanning on projector + driver one-hand in sunlight + BEL jury 60s.
Mode: Operate. Scanability > expression. No new deps, no purple/glass/neon, no left-rail side-tabs, system type.

## Problems (critique)
1. Overview shows KPIs + fleet + hero + map equally — no answer to "what needs me now?".
2. EventDetail actions sit in header; on mobile they scroll away just when needed.
3. LiveMap side panel always visible; on 360px it buries the map.
4. BridgeHealth stacks KPIs + chart + visual + map + events — long scroll, no orientation.
5. EdgeConsole START is mid-scroll, not in thumb zone; driver must hunt while bus idles.
6. Zero-state (fresh DB) shows "No events" with no path to value.

## Decisions
- R1 Overview: new "Needs attention" card at TOP (5 worst: CRITICAL/HIGH + UNVERIFIED first, each row: severity badge + code + type + age + Open link). KPIs stay below. Jury sees triage in 5s.
- R2 EventDetail: sticky action bar (position:sticky bottom on mobile / top under topbar on desktop) with Confirm/Reject/Create WO + Back. Investigation flow: Summary → Evidence → Fusion → Timeline order kept.
- R3a LiveMap: side panel becomes collapsible (details/summary native, no JS lib) default open on desktop, closed on ≤760px. Map keeps full height.
- R3b BridgeHealth: tab bar (Overview | History | Visual | Events) reusing chip + aria-pressed pattern; content swaps, map stays in Overview tab only (perf: fewer Leaflet instances in DOM).
- R4 EdgeConsole: sticky bottom action bar (START/STOP 56px + SYNC) via Scaffold bottomNavigationBar-equivalent (Column + Expanded log + fixed bar); status grid stays top; log shrinks. One-hand reachable.
- R5 Onboarding: Empty states get path-to-value CTA (Start edge / Emit demo / Open map). No new routes.

## Non-goals
No new routes, no new npm/pub packages, no Leaflet plugin, no chart lib change, no auth change, no backend change.
