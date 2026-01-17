# UX Audit Synthesis & Prioritized Action Plan

**Project:** Music Listening Stats Dashboard  
**Date:** January 2026  
**Status:** Final Synthesis

---

## Executive Summary

1. **Ad-hoc component growth** — Four stat components, three modal implementations, and numerous bespoke card treatments duplicate logic instead of composing from shared primitives
2. **Missing accessibility layer** — Color-only encoding in charts, no `prefers-reduced-motion` support, interactive charts lack keyboard navigation, custom visualizations missing ARIA labels
3. **Fragmented information architecture** — `/timeline` and `/story` serve overlapping purposes; `/albums/[id]` is an orphan route; Home acts as a junk drawer with redundant entry points
4. **Token sprawl** — 14 spacing values in use vs. 7 defined; typography drifts across Display/Heading/Body without formal role mapping; gradients reference Tailwind colors instead of semantic tokens
5. **Inconsistent state handling** — 6 of 10 views lack empty states; loading treatments vary from full-screen blockers to silent waits; no skeleton loaders
6. **Button hierarchy collapse** — Only primary/secondary variants actually used; raw `<button>` elements bypass the system in critical flows; no destructive/tertiary tiers
7. **Motion timing drift** — Stagger intervals range from 20ms to 120ms; FloatingNav has a 300ms entrance delay; no global `prefers-reduced-motion` fallback
8. **Data viz inconsistency** — Bar charts use three different color schemes; peak highlighting varies by chart; Y-axis widths differ between pages
9. **Tooltip & modal duplication** — Three nearly-identical Recharts tooltips; Timeline and Discoveries rebuild the `Modal` component from scratch
10. **No shared chart component library** — Mix of Recharts (area) and custom motion divs (bars) creates maintenance burden and visual inconsistency

---

## Pattern Recognition

### Root Cause 1: Feature-First, System-Second
> "The inconsistent cards, fragmented IA, and missing states all stem from features being shipped without updating the shared component library."

Features (Story mode, Discoveries, Patterns) each invented their own stat displays, modals, and card treatments. No one circled back to extract reusable patterns.

### Root Cause 2: Token Under-Specification
> "Spacing, typography, and color tokens exist but aren't enforced."

`globals.css` defines 7 spacing values; pages use 14. Typography tokens describe sizes but not roles (when to use Display vs. Heading). Gradients reference `violet-600/20` instead of semantic variables.

### Root Cause 3: Accessibility as Afterthought
> "Charts, modals, and interactive elements were built for sighted mouse users."

Custom bar charts lack ARIA. Color is the sole differentiator for peaks and trends. Keyboard navigation is absent on timeline modals and discovery bars.

### Root Cause 4: Dual-Mode Design Debt
> "Explorer vs. Story mode have different motion systems, but shared components don't adapt."

Story mode's 800ms dramatic animations bleed into components used elsewhere. No `prefers-reduced-motion` guard exists at all.

---

## Prioritized Action Plan

### Tier 1 — Do Immediately
*High impact, reasonable effort. Unlocks downstream work.*

| # | Action | Files | Size |
|---|--------|-------|------|
| 1.1 | **Add `prefers-reduced-motion` global fallback** — CSS media query + Framer Motion wrapper | `globals.css`, `lib/motion.ts` | S |
| 1.2 | **Standardize stagger timing** to 40ms across all lists; cap total delay at 200ms | `lib/motion.ts`, page files | S |
| 1.3 | **Remove FloatingNav entrance delay** (300ms → 0) | `components/layout/FloatingNav.tsx` | S |
| 1.4 | **Add ARIA labels to custom charts** — `role="img"`, `aria-label`, `aria-describedby` | `app/page.tsx`, `app/patterns/page.tsx`, `app/discoveries/page.tsx` | S |
| 1.5 | **Add non-color peak indicators** — icon or label badge alongside color | `app/patterns/page.tsx` | S |
| 1.6 | **Create `ChartTooltip` shared component** to replace 3 duplicates | New: `components/charts/ChartTooltip.tsx`; update `app/timeline/page.tsx` | S |
| 1.7 | **Standardize Y-axis width** to 50px on all Recharts charts | `app/timeline/page.tsx`, `app/artists/[id]/client.tsx` | S |
| 1.8 | **Wire `Dot` status indicators to semantic tokens** (`--color-success/warning/error`) | `components/ui/Badge.tsx` | S |

### Tier 2 — Do Next
*High impact + higher effort, OR lower impact + low effort.*

| # | Action | Files | Size |
|---|--------|-------|------|
| 2.1 | **Expand `StatCard`** — add `compact`, `horizontal`, `gradient` variants to absorb Home hero stats, Timeline metrics, Artist detail stats | `components/ui/StatCard.tsx`, then migrate call sites | M |
| 2.2 | **Decompose `Modal`** into `Modal.Header`, `Modal.Body`, `Modal.Footer` slots; add size/accent props so Timeline/Discoveries modals adopt it | `components/ui/Modal.tsx` | M |
| 2.3 | **Create `LoadingState`, `EmptyState`, `ErrorState` components** with consistent typography and icons | New: `components/ui/States.tsx` | M |
| 2.4 | **Introduce 5-tier Button hierarchy** — Primary, Secondary, Tertiary/Text, Ghost, Destructive; migrate raw `<button>` usages | `components/ui/Button.tsx`, page files | M |
| 2.5 | **Codify expanded spacing scale** in `globals.css` and Tailwind config (0–6rem, 13 steps) | `globals.css`, `tailwind.config.ts` | S |
| 2.6 | **Define role-based typography tokens** (Display XL/L/M, H1–H4, Body L/M/S, Label, Caption) with explicit line-height and letter-spacing | `globals.css` | S |
| 2.7 | **Standardize bar chart color palette** — violet-only for standard, gradient for emphasis only | `app/patterns/page.tsx`, `app/discoveries/page.tsx`, `app/page.tsx` | S |
| 2.8 | **Add skeleton loaders per section** to replace full-screen "Loading…" | New: `components/ui/Skeleton.tsx`; update page files | M |
| 2.9 | **Add page transition wrapper** using `AnimatePresence` in root layout | `app/layout.tsx` | M |

### Tier 3 — Do Eventually
*Lower priority or larger refactors.*

| # | Action | Files | Size |
|---|--------|-------|------|
| 3.1 | **Consolidate `/timeline` + `/story` into `/years`** with story-mode toggle | Route restructure: delete `app/timeline`, `app/story`; create `app/years` | L |
| 3.2 | **Merge `/albums/[id]` into artist detail tabs** | Delete `app/albums/[id]`; extend `app/artists/[id]/client.tsx` | M |
| 3.3 | **Rename `/patterns` → `/habits`**; add Taste Evolution module | Route rename + new module | M |
| 3.4 | **Restructure Home** — remove junk-drawer pattern; limit to hero + 3 quick-link cards + featured artist | `app/page.tsx` | M |
| 3.5 | **Build `FeatureCard`** (gradient hero with overlay, icon, CTA) to replace bespoke Explore cards | New: `components/ui/FeatureCard.tsx` | M |
| 3.6 | **Add Loyalty view to Library** (`/library?view=loyalty`) | `app/artists/page.tsx` (or future `/library`) | M |
| 3.7 | **Keyboard navigation for discovery timeline bars** — focusable + Enter/Space handlers | `app/discoveries/page.tsx` | S |
| 3.8 | **Add data-table alternative** for screen-reader chart access | `components/charts/DataTable.tsx` | M |
| 3.9 | **Add number count-up animation** for hero/stat numbers | `components/ui/AnimatedNumber.tsx` | S |
| 3.10 | **Collapse radii to 5-step scale** (4, 8, 12, 20, full px) and remap all components | `globals.css`, component files | M |

---

## Dependencies

```
┌─────────────────────────────────────────────────────────────────┐
│  FOUNDATION (do first)                                          │
├─────────────────────────────────────────────────────────────────┤
│  1.5 Tokens: spacing, typography, color                         │
│  2.6 ──────────────────────────────────┐                        │
│                                        ▼                        │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  COMPONENT CONSOLIDATION                                 │   │
│  │  2.1 StatCard variants ◄── must exist before ──► 3.4    │   │
│  │  2.2 Modal decomposition ◄── must exist before ──► 3.1  │   │
│  │  2.4 Button hierarchy ◄── must exist before ──► 3.1/3.4 │   │
│  │  2.3 State components ◄── must exist before ──► 2.8     │   │
│  └──────────────────────────────────────────────────────────┘   │
│                        │                                        │
│                        ▼                                        │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  IA REFACTOR                                             │   │
│  │  3.1 Consolidate /timeline + /story → /years             │   │
│  │  3.2 Merge albums into artist tabs                       │   │
│  │  3.3 Rename /patterns → /habits                          │   │
│  │  3.4 Restructure Home                                    │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

**Key blockers:**
- Token formalization (2.5, 2.6) should happen before component sweeps to avoid double-work
- `StatCard` expansion (2.1) must land before Home restructure (3.4)
- `Modal` decomposition (2.2) must land before `/years` consolidation (3.1)
- Button hierarchy (2.4) should land before any page rewrite to prevent new raw `<button>` instances

---

## Design System Extraction

### Tokens to Formalize

| Category | Current State | Proposed |
|----------|---------------|----------|
| **Spacing** | 7 defined, 14 in use | 13-step scale (0–6rem, 4px base) |
| **Typography** | 6 size tokens, no role mapping | 12 role tokens (Display XL/L/M, H1–4, Body L/M/S, Label, Caption, Mono) |
| **Color** | Core palette + ad-hoc Tailwind references | Add `--color-data-*` family; replace raw Tailwind with semantic vars |
| **Radii** | 5 values loosely applied | Collapse to 5 named tokens (`radius-xs` through `radius-pill`) |
| **Shadows** | 4 defined, `shadow-lg` also used | Expose as utility classes (`shadow-surface`, `shadow-glow`) |
| **Motion** | 3 durations + Story variants | 5-step duration scale + 2 spring presets + stagger tokens |

### Components to Standardize

| Component | Action |
|-----------|--------|
| **StatCard** | Add `compact`, `horizontal`, `gradient` variants; alias `MetricTile` |
| **Button** | Add Tertiary, Destructive variants; create `MotionButton` wrapper |
| **Card** | Add `FeatureCard` (gradient hero) and `InteractiveCard` (clickable Link wrapper) |
| **Modal** | Slot-based API (`Modal.Header/Body/Footer`) + size tokens |
| **ChartTooltip** | Single source of truth for Recharts tooltip styling |
| **LoadingState / EmptyState / ErrorState** | Shared messaging components with icons |
| **Skeleton** | Animated placeholder for section-level loading |

### Patterns to Document

| Pattern | Scope |
|---------|-------|
| **Page entrance** | Fade 200ms; exit 150ms |
| **Staggered list** | 40ms interval, 100ms initial delay, max 200ms total |
| **Modal open/close** | Scale 0.96→1, fade, 200ms in / 150ms out |
| **Card hover** | Scale 1.02, Y -2px, 150ms |
| **Data bar reveal** | Height 0→100%, 400ms + stagger capped at 200ms |
| **Peak highlight** | Color change + icon badge (never color alone) |

---

## Effort Estimates

| ID | Action | Size | Notes |
|----|--------|------|-------|
| 1.1 | `prefers-reduced-motion` fallback | **S** | ~20 lines CSS + motion wrapper |
| 1.2 | Standardize stagger timing | **S** | Search-replace in `motion.ts` + pages |
| 1.3 | Remove FloatingNav delay | **S** | One-liner |
| 1.4 | ARIA labels on charts | **S** | Add attributes to 3 pages |
| 1.5 | Non-color peak indicators | **S** | Badge component already exists |
| 1.6 | `ChartTooltip` component | **S** | Extract + replace 3 instances |
| 1.7 | Y-axis width standardization | **S** | Two-file change |
| 1.8 | Dot semantic tokens | **S** | Variable swap in Badge.tsx |
| 2.1 | Expand `StatCard` | **M** | New props + migrate ~6 call sites |
| 2.2 | Modal slot API | **M** | Refactor + migrate 2 custom modals |
| 2.3 | State components | **M** | New file + integrate across 6 pages |
| 2.4 | Button hierarchy | **M** | Extend component + audit ~15 raw buttons |
| 2.5 | Spacing scale | **S** | Token definition + Tailwind config |
| 2.6 | Typography roles | **S** | Token definition + utility classes |
| 2.7 | Bar chart colors | **S** | 3-page sweep |
| 2.8 | Skeleton loaders | **M** | New component + per-page integration |
| 2.9 | Page transitions | **M** | Layout wrapper + AnimatePresence |
| 3.1 | `/years` consolidation | **L** | ⚠️ **Deceptively complex** — merges 2 routes, requires story-mode toggle, affects navigation |
| 3.2 | Albums → artist tabs | **M** | Route deletion + tab UI in artist detail |
| 3.3 | `/habits` rename | **M** | Route rename + new module |
| 3.4 | Home restructure | **M** | Content reduction; depends on StatCard work |
| 3.5 | `FeatureCard` | **M** | New component + replace 2 bespoke sections |
| 3.6 | Loyalty view | **M** | Filter logic + new UI section |
| 3.7 | Keyboard nav for discoveries | **S** | Focus management + handlers |
| 3.8 | Data table alt | **M** | New component for a11y |
| 3.9 | Animated numbers | **S** | Small utility component |
| 3.10 | Radii collapse | **M** | Token change + component sweep |

### ⚠️ Complexity Flags

| Item | Why It's Deceptive |
|------|--------------------|
| **3.1 `/years` consolidation** | Touches navigation, 2 data flows, and the immersive Story experience. Test thoroughly for regressions. |
| **2.4 Button hierarchy** | Easy to define variants; hard to audit every raw `<button>` and decide which tier it belongs to. Budget extra QA. |
| **2.2 Modal slot API** | Existing modals have custom animations and header treatments. Generalizing without losing fidelity takes iteration. |
| **3.4 Home restructure** | Politically sensitive — stakeholders may resist removing sections. Prototype before committing. |

---

## Recommended Sprint Plan

| Sprint | Focus | Items |
|--------|-------|-------|
| **1** | Accessibility & Quick Wins | 1.1–1.8 |
| **2** | Token Formalization | 2.5, 2.6, 3.10 |
| **3** | Component Consolidation | 2.1, 2.2, 2.3, 2.4 |
| **4** | Motion & Loading Polish | 2.7, 2.8, 2.9, 3.9 |
| **5** | IA Refactor | 3.1, 3.2, 3.3, 3.4 |
| **6** | Enhancements | 3.5, 3.6, 3.7, 3.8 |

---

*Synthesis complete. Proceed with Tier 1 items to establish foundation before larger refactors.*
