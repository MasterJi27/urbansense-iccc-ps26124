# UI Redesign V4 — "Command Ink" (full pass, Impeccable shape)

Contract for all squads. Visuals only: keep every API call, route path, state name, WS logic, Leaflet/Recharts usage. No new npm/pub deps. Detector must stay 0. Build must stay green.

## Language
Operate-mode console. Ink-on-paper hierarchy: strong titles, quiet meta, tabular numbers. Accent used sparingly (actions, critical states, live dot). Dark mode via existing [data-theme="dark"] tokens only.

## Page contract (every page)
```
<div>
  <div className="page-header">
    <div>
      <div className="crumbs">SECTION • SUBSECTION</div>   (use existing .crumbs)
      <h2 className="page-title">Title</h2>                  (single h2, no inline fontSize)
      <p className="page-sub muted">What this view answers + result count with role="status"</p>
    </div>
    <div className="filters">…chips/selects/buttons…</div>  (chips need aria-pressed)
  </div>
  ...content...
</div>
```
- Result counts: "{n} of {m}" + role="status". Numbers in .table-num.
- Section blocks: .card with <h4> eyebrow title (existing pattern).
- Tables: .table-wrap > .table-toolbar (search/selects with aria-label) > table (.table-num on numerics, ellipsis + title on long codes).
- Empty: Empty.jsx with hint path-to-value CTA. Loading: Skeleton (role=status). Feedback: useToast (success/error), no inline msg cards.
- No left-rail accent on rounded cards (anti side-tab). Status = .status-dot + .tag/.badge, never color alone.
- Radius: cards lg 14, inputs md 10, tags/chips pill. No new radii.
- Motion: transform/opacity only; reduced-motion respected (already in CSS).

## Mobile (EdgeConsole + SensorHome)
Dark field console intentional. Thumb-zone bottom bar. Tiles ≥48px, text ≥11px, maxLines+ellipsis, Semantics on toggles/chips, withValues only, ≤80 logs, ListView.builder.

## Forbidden (detector)
No webfont @import, no literal palette hex in CSS/JSX (use vars; Leaflet severity colors map stays as the single JS exception already present), no borderLeft rails, no pulse-always animation, no glass blur, no gradient text, no nested cards >2.
