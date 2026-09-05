# UrbanSense — DESIGN.md (Stitch format, Impeccable)

## 01 Overview
Operate-mode admin: scanability over expression. Brand lives in precise details (accent bar under 4px, tabular numbers, honest SIM/REAL tags). No purple gradients, no glassmorphism, no neon glow, no hero metrics theater.

## 02 Colors (tokens only — no literals outside styles.css)
--bg #f4f6f8, --surface #fff, --surface-2 #f8fafb, --line #e7ecf1, --line-strong #d9e2eb
--text #0f1b2d, --muted #5a6d85 (AA-fixed), --muted-2 #6b7f98
--accent #0bb98a, --accent-700 #0a9e77, --accent-soft #e8f7f1
--warn #b7790f / soft #fff6e0, --danger #e5484d / soft #fdecec, --info #2f7fe0 / soft #ecf3ff, --violet #6a4fd0 / soft #efe9fb
Dark: [data-theme="dark"] overrides only. Charts use var(--accent/info/warn), never hex.

## 03 Typography
Body: system stack first (no webfont render-block; Inter only as fallback if installed). Mono: ui-monospace stack for codes/coords/numbers (.mono, .mono-sm, .table-num tabular-nums).
Scale: h2 22/800 -.02em, section-title 11/800 +.09em uppercase muted, card h4 11/700 +.09em, body 13-13.5, small 11-12. Min functional text 11px. No all-caps paragraphs.

## 04 Elevation
--shadow-sm (1px + 8px @6%), --shadow-md (4px 18px @8%). Cards: EITHER hairline border OR soft shadow — current uses both; migrate to border-only default, shadow on hover only. Radius: xl 18 (shell), lg 14 (cards), md 10 (inputs), pill 999 (tags/chips). No 24px+ card blobs.

## 05 Components (point at real code)
- .btn / .btn-lg/.btn-sm/.btn-danger/.btn.ghost (App.jsx top-actions, EventDetail actions)
- .chip + .chip.active (filters, aria-pressed), .tag real/rule/sim/info, .badge severity
- .kpi-card + .kpi-top + .kpi-ico (Overview, BridgeHealth) — accent is 3px top inset bar (anti side-tab rule enforced; left rail removed). Role/user/WO cards use borderTop accent + status-dot, never left rail.
- .card + .card-pad-sm, .grid-2/3/4, .kpis/.kpis-3 (responsive 1280/760/480)
- .table-wrap + .table-toolbar + .table-num (all list pages) + Empty.jsx + Skeleton.jsx + Toast.jsx (role=status/alert)
- .notif-dropdown/.notif-badge, .search + kbd, .status-dot (STATIC by default; pulse only with [data-live="true"] + reduced-motion off)
- .cluster-bubble crit/high/med/low (LiveMap DivIcon, no extra dep)
- .login-split brand/form (Login.jsx), .timeline/.tl-item, .legend, .maprail

## 06 Do's & Don'ts
DO: page contract (crumbs + h2.page-title + p.page-sub with role=status counts + .filters), tabular numbers, aria-pressed chips, aria-label icon buttons, Copy buttons with title, honest SIM tags, ~1KB honesty, thumb-zone bottom bar on field console, collapsible side panels, tabs reusing chip pattern.
DON'T: purple/blue gradients, glass blur cards, neon glow, side-tab rails on rounded cards (top-bar accent only), pulse-always dots, webfont @import, literal palette hex (vars only; Leaflet severity map is the single JS exception), Inter-only flat hierarchy, nested cards >2 deep, gradient text, marquee/bounce/elastic, width/height animation (transform/opacity only).

## 07 V4 Command Ink (redesign lock)
Spec: docs/UI_REDESIGN_V4.md. Every app page follows crumbs/title/sub/count/filters. Shell: sidebar groups + topbar search (Ctrl+K) + theme + notif + New work order. Overview triage card on top. EventDetail sticky action bar. LiveMap cluster + heat + collapsible panel. BridgeHealth tabs with single map instance. Field console: status grid + bottom START/SYNC bar + color logs + mapping expander. Verified: impeccable detect 0, vite 712 green.
